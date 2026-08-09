"""Health/readiness routes — NFR-OBS-2. Public (no auth), used by container
orchestration liveness/readiness probes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.interface.schemas.common_schemas import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response, db: Session = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    cache_status = "ok"  # Redis is optional infrastructure; see infrastructure/external/redis_cache.py

    ai_status = "ok"
    try:
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
        AiPipelineClient()._get_service()
    except AiPipelineUnavailableError:
        ai_status = "degraded"
    except Exception:
        ai_status = "down"

    overall = "ok" if db_status == "ok" and ai_status != "down" else "degraded"
    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(status=overall, database=db_status, cache=cache_status, ai_service=ai_status)
