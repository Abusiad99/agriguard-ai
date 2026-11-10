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


def _ensure_repo_root_on_path() -> None:
    import sys
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def _tiny_classifier(num_classes: int, favored_class: int):
    """Small conv net whose output always favors `favored_class` (via the head bias),
    so explainability/inference paths can run without trained weights."""
    torch = pytest.importorskip("torch")
    nn = torch.nn
    model = nn.Sequential(
        nn.Conv2d(3, 4, kernel_size=3, padding=1), nn.ReLU(),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(4, num_classes),
    )
    with torch.no_grad():
        model[-1].bias.zero_()
        model[-1].bias[favored_class] = 10.0
    return model.eval()


class TestGradCamHookLifecycle:
    """The inference model is a long-lived per-process singleton, so every Grad-CAM
    call must leave the target layer exactly as it found it."""

    def test_explain_removes_its_hooks_after_each_call(self):
        torch = pytest.importorskip("torch")
        _ensure_repo_root_on_path()
        from ai.explainability.gradcam import GradCAM

        model = _tiny_classifier(num_classes=2, favored_class=1)
        conv = model[0]
        explainer = GradCAM()

        for _ in range(3):
            heatmap = explainer.explain(model, torch.rand(1, 3, 16, 16), target_class=1)
            assert heatmap.shape == (16, 16)
            assert len(conv._forward_hooks) == 0
            assert len(conv._backward_hooks) == 0


class TestAttentionRolloutOnTimmVit:
    """timm ViTs use fused attention by default, which never materializes the
    attention weights; the explainer must still capture real per-image attention
    (not a fixed stand-in pattern) and leave the shared model as it found it."""

    def test_rollout_uses_real_attention_and_restores_the_model(self):
        torch = pytest.importorskip("torch")
        timm = pytest.importorskip("timm")
        _ensure_repo_root_on_path()
        from ai.explainability.attention_rollout import AttentionRolloutExplainer

        torch.manual_seed(0)
        model = timm.create_model("vit_tiny_patch16_224", pretrained=False, num_classes=3).eval()
        attention_modules = [m for m in model.modules() if hasattr(m, "fused_attn")]
        fused_before = [m.fused_attn for m in attention_modules]
        explainer = AttentionRolloutExplainer()

        first = explainer.explain(model, torch.rand(1, 3, 224, 224), target_class=0)
        assert len(explainer._attentions) == len(model.blocks)
        second = explainer.explain(model, torch.rand(1, 3, 224, 224), target_class=0)

        assert first.shape == (224, 224)
        assert not np_allclose(first, second)  # depends on the image, unlike the old fixed prior
        assert [m.fused_attn for m in attention_modules] == fused_before
        assert all(len(m.attn_drop._forward_hooks) == 0 for m in attention_modules)

    def test_model_without_attention_weights_raises_instead_of_inventing_a_heatmap(self):
        torch = pytest.importorskip("torch")
        _ensure_repo_root_on_path()
        from ai.explainability.attention_rollout import AttentionRolloutExplainer

        with pytest.raises(RuntimeError):
            AttentionRolloutExplainer().explain(_tiny_classifier(2, 0), torch.rand(1, 3, 16, 16), target_class=0)


def np_allclose(a, b) -> bool:
    import numpy as np
    return bool(np.allclose(a, b))


class TestHealthyPredictionHasNoSeverity:
    """A healthy prediction must not be graded from the Grad-CAM map of the
    "healthy" class (which always has pixels above the threshold)."""

    def test_healthy_prediction_skips_explainability_and_severity(self, tmp_path):
        pytest.importorskip("torch")
        transforms = pytest.importorskip("torchvision.transforms")
        _ensure_repo_root_on_path()
        from unittest.mock import MagicMock

        from PIL import Image

        from ai.data.label_encoder import LabelEncoder
        from ai.inference.inference_service import InferenceService

        service = InferenceService.__new__(InferenceService)  # skip loading artifacts from disk
        service.label_encoder = LabelEncoder(classes=["tomato___healthy", "tomato___late_blight"])
        service.model = _tiny_classifier(num_classes=2, favored_class=0)
        service.device = "cpu"
        service.eval_transform = transforms.Compose([transforms.Resize((16, 16)), transforms.ToTensor()])
        service.explainer = MagicMock()

        heatmap_path = tmp_path / "heatmap.png"
        result = service.diagnose(Image.new("RGB", (32, 32), color=(70, 130, 60)), save_heatmap_to=heatmap_path)

        assert result.condition == "healthy"
        assert result.severity_level is None
        assert result.affected_area_pct == 0.0
        assert result.healthy_area_pct == 100.0
        assert result.heatmap_overlay_path is None
        assert not heatmap_path.exists()
        service.explainer.explain.assert_not_called()


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
