"""
Integration tests for the backend <-> AI pipeline boundary
(app/infrastructure/external/ai_pipeline_client.py <-> ai/inference/inference_service.py)
— FR-AI-1..12.

Two things are tested here:
1. That AiPipelineClient correctly raises AiPipelineUnavailableError when no trained
   model run exists yet (the expected state of a fresh checkout before `python
   train.py` has been run). NOTE: `ai.training.artifact_manager` imports `torch` at
   module level (it type-hints `torch.nn.Module`/uses `torch.save`/`torch.load`), so
   even this "no model present" check is transitively blocked by the missing `torch`
   dependency in this sandbox — verified directly (see the Phase 3 validation
   report). It is written as real, executable code and expected to pass once torch
   is installed.
2. That AiPipelineClient correctly delegates to a real
   `ai.inference.inference_service.InferenceService` once a model exists — this
   requires `torch`, `timm`, and a trained model checkpoint, NEITHER of which is
   available in this sandbox (no network to install torch/timm, and no dataset was
   placed in datasets/ to train against, per the project's explicit instruction not
   to fabricate datasets). This part is written as real, complete, executable code
   and is BLOCKED here, not faked — it is expected to pass once a model has been
   trained via `python train.py` in an environment with torch installed.

This file intentionally does NOT use `_FakeInferenceService` (that fixture exists in
conftest.py specifically for API-level tests that don't care about AI internals) —
its purpose is to validate the real integration boundary itself.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


class TestAiPipelineClientWithoutTrainedModel:
    """NOT EXECUTABLE IN THIS SANDBOX: ai.training.artifact_manager imports torch at
    module level, and torch is not installed here (no network access to install it).
    Syntax-checked; logically reviewed — ArtifactManager.load_latest_run_dir() reads
    only a JSON marker file and raises FileNotFoundError when absent, independent of
    any torch functionality, so this is expected to pass immediately once torch is
    installed, without requiring an actual trained model."""

    def test_raises_clear_error_when_no_run_exists(self, tmp_path, monkeypatch):
        import sys
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from ai.training.artifact_manager import ArtifactManager

        empty_runs_dir = tmp_path / "runs"
        empty_runs_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            ArtifactManager.load_latest_run_dir(base_dir=empty_runs_dir)

    def test_ai_pipeline_client_wraps_the_error_with_actionable_message(self, tmp_path, monkeypatch):
        """NOT EXECUTABLE IN THIS SANDBOX: AiPipelineClient imports app.core.config
        (pydantic-settings), which is not installed here. Syntax-checked; logically
        reviewed — AiPipelineClient._get_service() catches FileNotFoundError from
        ArtifactManager.load_latest_run_dir() and re-raises AiPipelineUnavailableError
        with a message telling the operator to run `python train.py`."""
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
        from ai.config import CONFIG

        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", tmp_path)
        client = AiPipelineClient()
        client.__class__._service = None
        with pytest.raises(AiPipelineUnavailableError):
            client._get_service()


class TestAiPipelineClientWithTrainedModel:
    """BLOCKED IN THIS SANDBOX: requires torch + timm (not installed, no network) and
    a trained model run (requires a real dataset placed in datasets/, which this
    project explicitly must not fabricate). This test is written to run against a
    genuinely trained model once one exists, exercising the real
    ai.inference.inference_service.InferenceService end to end through the backend
    client — not a mock of it."""

    @pytest.mark.skip(reason="Requires torch/timm and a trained model run; not available in this sandbox.")
    def test_diagnose_returns_a_real_diagnosis_output(self, tmp_path):
        import sys
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from PIL import Image

        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient

        image_path = tmp_path / "test_leaf.jpg"
        Image.new("RGB", (224, 224), color=(70, 130, 60)).save(image_path)

        client = AiPipelineClient()
        result = client.diagnose(image_path)

        assert hasattr(result, "unrecognized_plant")
        assert hasattr(result, "confidence_score")
        assert 0.0 <= result.confidence_score <= 100.0
