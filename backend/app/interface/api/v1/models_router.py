"""AI model registry routes: name, version, architecture, dataset version, training
status, evaluation metrics and readiness of each AI model. Checkpoint paths and
dataset files are never exposed."""
from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.domain.entities.user import User
from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (repo-root `ai` on sys.path)
from app.infrastructure.external.model_clients import OutbreakModelClient, SegmentationClient
from app.interface.api.v1.dependencies import get_current_user, get_outbreak_client, get_segmentation_client
from app.interface.schemas.ai_features_schemas import ModelCardSchema

from ai import registry

router = APIRouter(prefix="/models", tags=["AI Models"])


def _cards(segmentation: SegmentationClient, outbreak: OutbreakModelClient):
    # Clients overlay load failures (UNAVAILABLE) on top of the registry's view.
    # The classifier may be pinned to a run with AI_ARTIFACTS_RUN_DIR; describe the run actually served.
    run_dir = get_settings().ai_artifacts_run_dir
    pinned = Path(run_dir) if run_dir else None
    return {"classification": registry.describe("classification", pinned), "segmentation": segmentation.status(),
            "outbreak": outbreak.status()}


def _schema(card) -> ModelCardSchema:
    data = card.public_dict()
    return ModelCardSchema(**{k: data[k] for k in ModelCardSchema.model_fields if k in data})


@router.get("", response_model=List[ModelCardSchema])
def list_models(current_user: User = Depends(get_current_user),
                segmentation: SegmentationClient = Depends(get_segmentation_client),
                outbreak: OutbreakModelClient = Depends(get_outbreak_client)):
    return [_schema(c) for c in _cards(segmentation, outbreak).values()]


@router.get("/{task}", response_model=ModelCardSchema)
def get_model(task: str, current_user: User = Depends(get_current_user),
              segmentation: SegmentationClient = Depends(get_segmentation_client),
              outbreak: OutbreakModelClient = Depends(get_outbreak_client)):
    cards = _cards(segmentation, outbreak)
    if task not in cards:
        raise NotFoundError("Unknown AI task.")
    return _schema(cards[task])
