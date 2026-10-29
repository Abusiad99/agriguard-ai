"""
Shared pytest fixtures.

`db_session` provisions a fresh in-memory SQLite database per test, schema created
via `Base.metadata.create_all()` — the cross-dialect GUID type
(app/infrastructure/db/base.py) is what makes the exact same ORM models used against
PostgreSQL in production work here. `client` wraps the FastAPI app with dependency
overrides pointing at that same SQLite session, and overrides the AI pipeline client
with a deterministic fake so API tests don't require trained model weights.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-" + "x" * 20)
os.environ.setdefault("LOCAL_STORAGE_DIR", "/tmp/agriguard_test_storage")

from app.infrastructure.db.models import Base  # noqa: E402
from app.infrastructure.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.interface.api.v1.dependencies import get_current_user  # noqa: E402


@pytest.fixture()
def db_engine():
    # StaticPool forces every checkout to reuse the one underlying SQLite connection.
    # Without it, SQLAlchemy's default SingletonThreadPool hands a *new* connection to
    # any thread that hasn't touched the engine yet — and for a `:memory:` database a
    # new connection means a brand-new, empty database. FastAPI dispatches sync route
    # handlers to a worker threadpool, so those requests would silently land on a
    # tableless DB ("no such table: users") despite `create_all()` having run here.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_leaf_like_image_bytes(size: int = 320, seed: int = 0, fmt: str = "JPEG") -> bytes:
    """A textured, green, well-exposed synthetic photo that passes the image-quality
    gate. (Flat single-colour squares are — correctly — rejected as having no detail.)"""
    import numpy as np

    rng = np.random.default_rng(seed)
    base = np.zeros((size, size, 3), dtype=np.float64)
    base[..., 0], base[..., 1], base[..., 2] = 70, 140, 55
    yy, xx = np.mgrid[0:size, 0:size]
    veins = 25 * np.sin(xx / 7.0) * np.cos(yy / 11.0)
    noise = rng.normal(0, 18, size=(size, size, 1))
    arr = np.clip(base + veins[..., None] + noise, 0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt)
    return buf.getvalue()


def fake_diagnosis_result(decision_status: str = "confident", **overrides):
    """Shape-compatible stand-in for ai.inference.inference_service.DiagnosisOutput."""
    from types import SimpleNamespace

    confident = decision_status == "confident"
    inconclusive = decision_status == "inconclusive"
    top_k = [
        {"plant": "tomato", "condition": "early_blight", "canonical": "tomato___early_blight", "confidence": 91.5},
        {"plant": "tomato", "condition": "septoria_leaf_spot", "canonical": "tomato___septoria_leaf_spot",
         "confidence": 4.2},
        {"plant": "potato", "condition": "early_blight", "canonical": "potato___early_blight", "confidence": 2.1},
    ]
    values = dict(
        status="completed", unrecognized_plant=False,
        plant=None if inconclusive else "tomato",
        condition=None if inconclusive else "early_blight",
        canonical_label=None if inconclusive else "tomato___early_blight",
        confidence_score=91.5 if confident else (48.0 if decision_status == "uncertain" else 12.0),
        low_confidence_flag=not confident, decision_status=decision_status,
        decision={"status": decision_status, "top1_probability": 0.915 if confident else 0.48, "margin": 0.87,
                  "normalized_entropy": 0.1, "plant_identified": not inconclusive},
        thresholds={"confident": 0.8, "reject": 0.3, "plant_mass": 0.6, "source": "validation",
                    "temperature": 1.4, "calibrated": True},
        plant_probability_mass=0.95, raw_top1_probability=0.97,
        severity_level=None, affected_area_pct=None, healthy_area_pct=None, severity_method=None,
        segmentation={"status": "unavailable", "reason": "no_segmentation_model"},
        top_k=top_k, heatmap_overlay_path=None,
        explanation={"method": "grad_cam", "available": True, "target_label": "tomato___early_blight",
                     "reason": None},
        quality={"status": "ok", "issues": [], "metrics": {}, "version": "1.0.0"},
        model_version="test-run:abc123", pipeline_version="2.0.0", inference_ms=12.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeInferenceService:
    """Deterministic stand-in for ai.inference.inference_service.InferenceService,
    so API-level tests don't require trained model weights (which don't exist in a
    fresh checkout — that's the whole point of `python train.py`)."""

    decision_status = "confident"
    model_version = "test-run:abc123"
    architecture = "efficientnet_b0"
    supported_classes = ["tomato___early_blight", "tomato___septoria_leaf_spot", "potato___early_blight"]
    segmentation = None

    class _Thresholds:
        @staticmethod
        def to_dict():
            return {"confident": 0.8, "reject": 0.3, "plant_mass": 0.6, "source": "validation",
                    "temperature": 1.4, "calibrated": True}

    thresholds = _Thresholds()

    def diagnose(self, image, top_k=3, save_heatmap_to=None, **_kwargs):
        if save_heatmap_to is not None:
            Path(save_heatmap_to).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), color=(120, 40, 40)).save(save_heatmap_to)
        return fake_diagnosis_result(self.decision_status)


@pytest.fixture()
def client(db_session, monkeypatch):
    from fastapi.testclient import TestClient

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # RateLimitMiddleware keeps its sliding-window counters on the middleware instance,
    # which Starlette builds once and caches on `app.middleware_stack` for the process
    # lifetime. Without a reset here, every test shares one counter (TestClient always
    # reports the same client_ip), so auth-heavy tests trip real 429s from unrelated
    # tests' traffic. Forcing a rebuild gives each test a fresh limiter, matching how a
    # real deployment only accumulates hits per-client, not across unrelated clients.
    app.middleware_stack = None

    # Swap the real AI pipeline (requires trained weights) for the deterministic fake.
    from app.infrastructure.external import ai_pipeline_client

    ai_pipeline_client.AiPipelineClient._service = _FakeInferenceService()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    ai_pipeline_client.AiPipelineClient._service = None


@pytest.fixture()
def sample_image_bytes() -> bytes:
    return make_leaf_like_image_bytes()


def make_auth_header(client, email="farmer@example.com", password="Str0ngPass!", full_name="Test Farmer") -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": full_name})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
