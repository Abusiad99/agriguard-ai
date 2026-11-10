"""
Lazy, process-wide clients for the optional AI models (segmentation, outbreak).

Same lifecycle as AiPipelineClient (classification): a model is loaded once per worker
on first use, behind its own lock, and every request reuses it. Each client reports
its readiness from the model registry without loading weights, and a failed load is
remembered as UNAVAILABLE (with the reason) instead of crashing requests. Clients are
independent: classification keeps working when these models are missing.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (puts the repo-root `ai` package on sys.path)

from ai import registry
from ai.registry import ModelCard, Readiness

logger = logging.getLogger("agriguard.model_clients")


class ModelUnavailable(Exception):
    def __init__(self, card: ModelCard):
        super().__init__(card.message)
        self.card = card


class LazyModelClient:
    task: str = ""

    def __init__(self, loader: Optional[Callable] = None):
        self._loader = loader
        self._instance = None
        self._loaded_from = None
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()

    def _load(self, run_dir):
        raise NotImplementedError

    def status(self) -> ModelCard:
        card = registry.describe(self.task)
        if card.is_ready and self._load_error and self._loaded_from == card.run_dir:
            card.readiness, card.message = Readiness.UNAVAILABLE, self._load_error
        return card

    def get(self):
        """The loaded model, or raise ModelUnavailable with the reason."""
        card = registry.describe(self.task)
        if not card.is_ready:
            raise ModelUnavailable(card)
        if self._instance is not None and self._loaded_from == card.run_dir:
            return self._instance
        with self._lock:
            if self._instance is None or self._loaded_from != card.run_dir:
                try:
                    self._instance = (self._loader or self._load)(card.run_dir)
                    self._load_error = None
                except Exception as exc:  # noqa: BLE001 - any load failure = model unavailable, never a crash
                    logger.warning("Loading %s model from %s failed: %s", self.task, card.run_dir, exc)
                    self._instance, self._load_error = None, f"Model files could not be loaded ({exc.__class__.__name__})."
                    self._loaded_from = card.run_dir
                    card.readiness, card.message = Readiness.UNAVAILABLE, self._load_error
                    raise ModelUnavailable(card) from exc
                self._loaded_from = card.run_dir
        return self._instance

    def call(self, fn: Callable):
        """Run fn(model) while holding the lock: these models keep per-call state and
        are not safe to use from several threads at once."""
        model = self.get()
        with self._lock:
            return fn(model)


class SegmentationClient(LazyModelClient):
    task = "segmentation"

    def _load(self, run_dir):
        from ai.segmentation.inference import SegmentationService
        return SegmentationService(run_dir)


class OutbreakModelClient(LazyModelClient):
    task = "outbreak"

    def _load(self, run_dir):
        from ai.outbreak.model import OutbreakModel
        return OutbreakModel(run_dir)
