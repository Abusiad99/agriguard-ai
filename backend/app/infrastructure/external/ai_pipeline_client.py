"""
AiPipelineClient — the backend's bridge into the `ai/` package (FR-AI-1..12).

Loads `ai.inference.inference_service.InferenceService` in-process (no network hop,
no subprocess) for lowest latency (NFR-PERF-1). The `ai/` package lives at the repo
root alongside `backend/`; both the Docker image and local development set
PYTHONPATH to the repo root so `import ai...` resolves (see docker/backend.Dockerfile
and README "Running Locally").

The service is loaded lazily and cached at module scope so the (potentially large)
model weights are read from disk only once per process, not per-request. Model
loading is guarded by a lock so concurrent first requests do not load it twice.

Run selection: AI_ARTIFACTS_RUN_DIR (explicit run) > latest run under
AI_ARTIFACTS_DIR/runs (previously AI_ARTIFACTS_DIR was read into settings but never
used, so the backend silently depended on ai/config.py's default path).
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger("agriguard.ai_client")
settings = get_settings()

# Ensure the repo root (parent of both backend/ and ai/) is importable: /app inside
# the Docker image, the checkout root in local development.
for _root in (Path("/app"), Path(__file__).resolve().parents[4]):
    if (_root / "ai").is_dir() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))


class AiPipelineUnavailableError(Exception):
    """Raised when no trained model run is available (operator has not yet run
    `python train.py`). Distinguished from a transient failure so the API layer can
    return a clear 503 rather than a generic 500."""


class AiPipelineClient:
    _service = None  # class-level cache across requests within a process
    _load_lock = threading.Lock()

    def __init__(self):
        self._run_dir = Path(settings.ai_artifacts_run_dir) if settings.ai_artifacts_run_dir else None

    def _resolve_run_dir(self) -> Optional[Path]:
        if self._run_dir is not None:
            return self._run_dir
        from ai.training.artifact_manager import ArtifactManager

        base = Path(settings.ai_artifacts_dir) / "runs"
        if (base / "latest.json").exists():
            return ArtifactManager.load_latest_run_dir(base)
        return None  # fall back to ai/config.py's artifacts dir

    def _get_service(self):
        if AiPipelineClient._service is not None:
            return AiPipelineClient._service
        with AiPipelineClient._load_lock:
            if AiPipelineClient._service is None:
                try:
                    from ai.inference.inference_service import InferenceService
                except ImportError as exc:
                    raise AiPipelineUnavailableError(
                        "The 'ai' package could not be imported. Ensure the repository "
                        "root is on PYTHONPATH."
                    ) from exc
                try:
                    AiPipelineClient._service = InferenceService(run_dir=self._resolve_run_dir())
                except FileNotFoundError as exc:
                    raise AiPipelineUnavailableError(
                        "No trained model found. Run `python train.py` from the repository "
                        "root before starting the API, or set AI_ARTIFACTS_RUN_DIR."
                    ) from exc
        return AiPipelineClient._service

    def diagnose(self, image_path: Path, heatmap_output_path: Optional[Path] = None,
                 seg_mask_output_path: Optional[Path] = None, seg_overlay_output_path: Optional[Path] = None):
        service = self._get_service()
        with Image.open(image_path) as img:
            return service.diagnose(img, top_k=5, save_heatmap_to=heatmap_output_path,
                                    save_seg_mask_to=seg_mask_output_path,
                                    save_seg_overlay_to=seg_overlay_output_path)

    def model_info(self) -> dict:
        """Public, non-sensitive description of the loaded model (supported classes,
        calibration and threshold provenance). Never includes filesystem paths."""
        try:
            service = self._get_service()
        except AiPipelineUnavailableError as exc:
            return {"available": False, "reason": str(exc)}
        seg = getattr(service, "segmentation", None)
        classes = service.supported_classes
        return {
            "available": True,
            "model_version": service.model_version,
            "architecture": service.architecture,
            "num_classes": len(classes),
            "supported_classes": classes,
            "supported_plants": sorted({c.split("___", 1)[0] for c in classes}),
            "has_healthy_class": any(c.endswith("___healthy") for c in classes),
            "thresholds": service.thresholds.to_dict(),
            "segmentation_available": bool(seg is not None and seg.available),
            "segmentation_model_version": seg.model_version if seg is not None else None,
        }
