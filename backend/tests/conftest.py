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
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-" + "x" * 20)
os.environ.setdefault("LOCAL_STORAGE_DIR", str(Path(tempfile.gettempdir()) / "agriguard_test_storage"))
# Tests never call the real Gemini API, even if a developer's .env holds a key
# (a real environment variable overrides the .env file).
os.environ["GEMINI_API_KEY"] = ""

# Opt-in: run the DB-backed tests against a real, throwaway PostgreSQL database
# instead of in-memory SQLite, e.g.
#   AGRIGUARD_TEST_DATABASE_URL=postgresql+psycopg2://agriguard:agriguard@127.0.0.1:5432/agriguard_test
# Every table is created and DROPPED per test, so the database name must end in
# "_test" — this refuses to run against a development or production database.
TEST_DATABASE_URL = os.environ.get("AGRIGUARD_TEST_DATABASE_URL", "")
if TEST_DATABASE_URL and not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("AGRIGUARD_TEST_DATABASE_URL must point at a database whose name ends in '_test'.")

from app.infrastructure.db.models import Base  # noqa: E402
from app.infrastructure.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.interface.api.v1.dependencies import get_current_user  # noqa: E402


@pytest.fixture()
def db_engine():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        Base.metadata.drop_all(bind=engine)  # clear leftovers from an interrupted run
        Base.metadata.create_all(bind=engine)
        yield engine
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        return

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

        # SYNTHETIC ranked candidates, shaped like the real pipeline's top_k.
        return _Result(bounding_box={"x_min": 5, "y_min": 5, "x_max": 20, "y_max": 20},
                       top_k=[{"plant": "tomato", "condition": "early_blight", "confidence": 91.5},
                              {"plant": "tomato", "condition": "late_blight", "confidence": 6.0},
                              {"plant": "tomato", "condition": "healthy", "confidence": 2.5}])


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


# ---------------------------------------------------------------------------
# AI features: isolate model artifacts/datasets per test and provide SYNTHETIC
# trained models (tests/synthetic_fixtures.py) where a test needs a ready model.
# Nothing here reads or writes the real artifacts/ or datasets/ folders.
# ---------------------------------------------------------------------------
import sys as _sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))


def _reset_model_clients():
    from app.interface.api.v1 import dependencies

    for client in (dependencies._segmentation_client, dependencies._outbreak_client):
        client._instance, client._loaded_from, client._load_error = None, None, None


@pytest.fixture(autouse=True)
def isolated_ai_paths(tmp_path, monkeypatch):
    from ai.config import CONFIG

    monkeypatch.setattr(CONFIG.paths, "artifacts_dir", tmp_path / "ai_artifacts")
    monkeypatch.setattr(CONFIG.paths, "datasets_dir", tmp_path / "ai_datasets")
    _reset_model_clients()
    yield
    _reset_model_clients()


@pytest.fixture(scope="session")
def trained_segmentation_artifacts(tmp_path_factory):
    """Artifacts dir holding a tiny segmentation model trained on synthetic shapes."""
    pytest.importorskip("torch")
    from ai.config import CONFIG
    from ai.segmentation.config import SegmentationConfig
    from ai.segmentation.preprocess import preprocess
    from ai.segmentation.train import train
    from tests.synthetic_fixtures import make_segmentation_dataset

    base = tmp_path_factory.mktemp("seg_model")
    previous = CONFIG.paths.artifacts_dir
    CONFIG.paths.artifacts_dir = base / "artifacts"
    try:
        dataset = make_segmentation_dataset(base / "dataset", n=24, size=64)
        config = SegmentationConfig(encoder="resnet10t", encoder_pretrained=False, image_size=64, epochs=3,
                                    batch_size=8, num_workers=0, min_train_images=1, min_leaf_pixels=20,
                                    mixed_precision=False, device="cpu")
        preprocess(dataset, config)
        train(dataset, config, allow_small=True)
    finally:
        CONFIG.paths.artifacts_dir = previous
    return base / "artifacts"


@pytest.fixture(scope="session")
def trained_outbreak_artifacts(tmp_path_factory):
    """Artifacts dir holding an outbreak model trained on synthetic observations."""
    pytest.importorskip("sklearn")
    from ai.config import CONFIG
    from ai.outbreak.config import OutbreakConfig
    from ai.outbreak.preprocess import preprocess
    from ai.outbreak.train import train
    from tests.synthetic_fixtures import make_outbreak_dataset

    base = tmp_path_factory.mktemp("outbreak_model")
    previous = CONFIG.paths.artifacts_dir
    CONFIG.paths.artifacts_dir = base / "artifacts"
    try:
        dataset = make_outbreak_dataset(base / "dataset")
        config = OutbreakConfig(min_rows=50, min_positives=10, min_negatives=10, min_span_days=200, max_iter=60)
        preprocess(dataset, config)
        train(dataset, config)
    finally:
        CONFIG.paths.artifacts_dir = previous
    return base / "artifacts"
