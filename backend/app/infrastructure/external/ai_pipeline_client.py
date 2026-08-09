"""
AiPipelineClient — the backend's bridge into the `ai/` package (FR-AI-1..12).

Loads `ai.inference.inference_service.InferenceService` in-process (no network hop,
no subprocess) for lowest latency (NFR-PERF-1). The `ai/` package lives at the repo
root alongside `backend/`; both the Docker image and local development set
PYTHONPATH to the repo root so `import ai...` resolves (see docker/backend.Dockerfile
and README "Running Locally").

The service is loaded lazily and cached at module scope so the (potentially large)
model weights are read from disk only once per process, not per-request.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger("agriguard.ai_client")
settings = get_settings()

# Ensure the repo root (parent of both backend/ and ai/) is importable.
_REPO_ROOT = Path("/app")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class AiPipelineUnavailableError(Exception):
    """Raised when no trained model run is available (operator has not yet run
    `python train.py`). Distinguished from a transient failure so the API layer can
    return a clear 503 rather than a generic 500."""


class AiPipelineClient:
    _service = None  # class-level cache across requests within a process

    def __init__(self):
        self._run_dir = Path(settings.ai_artifacts_run_dir) if settings.ai_artifacts_run_dir else None

    def _get_service(self):
        if AiPipelineClient._service is None:
            try:
                from ai.inference.inference_service import InferenceService
            except ImportError as exc:
                raise AiPipelineUnavailableError(
                    "The 'ai' package could not be imported. Ensure the repository "
                    "root is on PYTHONPATH."
                ) from exc
            try:
                AiPipelineClient._service = InferenceService(run_dir=self._run_dir)
            except FileNotFoundError as exc:
                raise AiPipelineUnavailableError(
                    "No trained model found. Run `python train.py` from the repository "
                    "root before starting the API, or set AI_ARTIFACTS_RUN_DIR."
                ) from exc
        return AiPipelineClient._service

    def diagnose(self, image_path: Path, heatmap_output_path: Optional[Path] = None):
        service = self._get_service()
        with Image.open(image_path) as img:
            return service.diagnose(img, top_k=3, save_heatmap_to=heatmap_output_path)
