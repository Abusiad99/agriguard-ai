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


class _FakeInferenceService:
    """Deterministic stand-in for ai.inference.inference_service.InferenceService,
    so API-level tests don't require trained model weights (which don't exist in a
    fresh checkout — that's the whole point of `python train.py`)."""

    def diagnose(self, image, top_k=3, save_heatmap_to=None):
        from dataclasses import dataclass

        @dataclass
        class _Result:
            unrecognized_plant: bool = False
            plant: str = "tomato"
            condition: str = "early_blight"
            canonical_label: str = "tomato___early_blight"
            confidence_score: float = 91.5
            low_confidence_flag: bool = False
            severity_level: str = "moderate"
            affected_area_pct: float = 28.0
            healthy_area_pct: float = 72.0
            bounding_box: dict = None
            top_k: list = None
            heatmap_overlay_path: str = None

        if save_heatmap_to is not None:
            Path(save_heatmap_to).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), color=(120, 40, 40)).save(save_heatmap_to)

        return _Result(bounding_box={"x_min": 5, "y_min": 5, "x_max": 20, "y_max": 20}, top_k=[])


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
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(80, 140, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def make_auth_header(client, email="farmer@example.com", password="Str0ngPass!", full_name="Test Farmer") -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": full_name})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
