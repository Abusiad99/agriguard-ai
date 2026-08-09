"""
AgriGuard AI Backend — application entry point.

Assembles: centralized config, structured logging, CORS, security/rate-limit/logging
middleware, exception handlers, versioned API routers, static storage mounting, and
startup/shutdown lifecycle (requirement #14/15/16, API versioning #23, OpenAPI #24).

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # development
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4  # production (behind NGINX)
"""
from __future__ import annotations

import logging
import logging.config
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.infrastructure.db.models import Base
from app.infrastructure.db.session import engine
from app.interface.api.v1.health_router import router as health_router
from app.interface.api.v1.router import api_v1_router
from app.interface.middleware.exception_middleware import register_exception_handlers
from app.interface.middleware.logging_middleware import LoggingMiddleware
from app.interface.middleware.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware

settings = get_settings()


def _configure_logging() -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers = {
        "console": {"class": "logging.StreamHandler", "level": settings.log_level, "formatter": "default",
                     "stream": "ext://sys.stdout"},
        "file": {"class": "logging.FileHandler", "level": settings.log_level, "formatter": "default",
                  "filename": str(log_dir / "backend.log"), "encoding": "utf-8"},
    }
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {"format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"}},
        "handlers": handlers,
        "root": {"level": settings.log_level, "handlers": ["console", "file"]},
    })


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    _configure_logging()
    logger = logging.getLogger("agriguard.startup")
    logger.info("Starting %s (env=%s)", settings.app_name, settings.app_env)

    if settings.database_url.startswith("sqlite"):
        # Test/dev convenience only: production schema is managed exclusively by
        # Alembic migrations (see backend/alembic.ini, requirement #17/18), never
        # by create_all() against Postgres.
        Base.metadata.create_all(bind=engine)
        logger.info("SQLite schema created via metadata.create_all() (dev/test mode).")

    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Storage directory ready: %s", settings.local_storage_dir)

    try:
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
        AiPipelineClient()._get_service()
        logger.info("AI inference service loaded successfully.")
    except AiPipelineUnavailableError as exc:
        logger.warning("AI inference service not available at startup: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI inference service failed to preload (%s); will retry per-request.", exc)

    yield

    # --- Shutdown ---
    logger.info("Shutting down %s.", settings.app_name)
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="AI-Powered Smart Agriculture & Date Palm Disease Detection System — REST API.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Middleware stack (order matters: outermost added last runs first) ---
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoggingMiddleware)

# --- Exception handlers ---
register_exception_handlers(app)

# --- Static file mounting for locally-stored images/heatmaps (dev convenience;
#     production typically serves these via NGINX or an S3-compatible CDN) ---
Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=settings.local_storage_dir), name="storage")

# --- Routers ---
app.include_router(health_router)  # public, unversioned: GET /health
app.include_router(api_v1_router, prefix=settings.api_prefix)


@app.get("/", tags=["System"])
def root():
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/api/docs",
        "api_version": "v1",
        "api_prefix": settings.api_prefix,
    }
