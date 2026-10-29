"""
Integration tests for the backend <-> AI pipeline boundary
(app/infrastructure/external/ai_pipeline_client.py <-> ai/inference/inference_service.py).

1. Without a trained run, the client raises AiPipelineUnavailableError with an
   actionable message. Needs torch (ai.training.artifact_manager imports it).
2. With a trained run in artifacts/runs/ (python train.py), the real
   InferenceService is exercised through the client: decision status, threshold
   provenance, no fabricated severity, and the quality gate. Skipped when torch,
   timm or a trained run is missing.

This file intentionally does NOT use `_FakeInferenceService` from conftest.py; its
purpose is to test the real integration boundary.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


class TestAiPipelineClientWithoutTrainedModel:
    """ArtifactManager.load_latest_run_dir() reads only a JSON marker file, but the
    module imports torch, so these tests need torch installed."""

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
        """_get_service() turns a missing run into AiPipelineUnavailableError, whose
        message tells the operator to run `python train.py`."""
        from app.infrastructure.external import ai_pipeline_client as mod
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
        from ai.config import CONFIG

        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", tmp_path)
        monkeypatch.setattr(mod.settings, "ai_artifacts_dir", str(tmp_path))
        monkeypatch.setattr(mod.settings, "ai_artifacts_run_dir", "")
        monkeypatch.setattr(AiPipelineClient, "_service", None)
        client = AiPipelineClient()
        with pytest.raises(AiPipelineUnavailableError):
            client._get_service()


def _trained_run_available() -> bool:
    try:
        import timm  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return (Path(__file__).resolve().parents[3] / "artifacts" / "runs" / "latest.json").exists()


@pytest.mark.skipif(not _trained_run_available(),
                    reason="Needs torch/timm and a trained run (python train.py) in artifacts/runs/.")
class TestAiPipelineClientWithTrainedModel:
    """Runs the real InferenceService through the backend client, against whatever
    model `artifacts/runs/latest.json` points to. Not a mock."""

    @pytest.fixture(autouse=True)
    def _fresh_client(self, monkeypatch):
        import sys
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from app.infrastructure.external import ai_pipeline_client as mod

        monkeypatch.setattr(mod.settings, "ai_artifacts_dir", str(repo_root / "artifacts"))
        monkeypatch.setattr(mod.settings, "ai_artifacts_run_dir", "")
        monkeypatch.setattr(mod.AiPipelineClient, "_service", None)
        yield
        mod.AiPipelineClient._service = None

    @staticmethod
    def _leaf_photo(path: Path) -> Path:
        """A textured green 'leaf' with brown spots on a light background (passes the
        quality gate; the model's answer to it is not asserted)."""
        import numpy as np
        from PIL import Image, ImageDraw, ImageFilter

        rng = np.random.default_rng(0)
        bg = (rng.normal(225, 8, (480, 640, 3))).clip(0, 255).astype("uint8")
        img = Image.fromarray(bg)
        d = ImageDraw.Draw(img)
        d.ellipse((120, 80, 520, 400), fill=(60, 130, 50))
        for _ in range(40):
            x, y = rng.integers(170, 470), rng.integers(120, 360)
            r = int(rng.integers(5, 14))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(110, 75, 35))
        noise = rng.normal(0, 10, (480, 640, 3))
        arr = (np.asarray(img.filter(ImageFilter.GaussianBlur(1))).astype(float) + noise).clip(0, 255)
        Image.fromarray(arr.astype("uint8")).save(path, quality=92)
        return path

    def test_diagnose_returns_a_decision_with_provenance_and_no_fabricated_severity(self, tmp_path):
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient

        client = AiPipelineClient()
        result = client.diagnose(self._leaf_photo(tmp_path / "leaf.jpg"), heatmap_output_path=tmp_path / "hm.png")

        assert result.status == "completed"
        assert result.decision_status in {"confident", "uncertain", "inconclusive"}
        assert 0.0 <= result.confidence_score <= 100.0
        assert result.model_version and result.pipeline_version
        assert result.thresholds["source"] == "validation" and result.thresholds["calibrated"]
        assert result.affected_area_pct is None and result.segmentation["status"] == "unavailable"
        if result.decision_status == "inconclusive":
            assert result.canonical_label is None
        assert (tmp_path / "hm.png").exists() == bool(result.explanation["available"])

    def test_unusable_photo_is_rejected_before_classification(self, tmp_path):
        from PIL import Image

        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient

        Image.new("RGB", (640, 480), color=(70, 130, 60)).save(tmp_path / "flat.jpg")
        result = AiPipelineClient().diagnose(tmp_path / "flat.jpg")
        assert result.status == "rejected_quality"
        assert result.canonical_label is None
        assert "no_detail" in [i["code"] for i in result.quality["issues"]]

    def test_model_info_reports_the_loaded_model(self):
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient

        info = AiPipelineClient().model_info()
        assert info["available"] and info["num_classes"] == len(info["supported_classes"])
        assert "/" not in str(info.get("model_version"))  # no filesystem paths
