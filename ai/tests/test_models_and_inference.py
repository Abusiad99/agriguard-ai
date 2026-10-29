"""Torch-dependent tests: Grad-CAM hook hygiene, U-Net shapes, dedup equivalence and an
end-to-end InferenceService run on a tiny randomly initialized model (pipeline
mechanics only — says nothing about diagnostic accuracy)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
pytest.importorskip("timm")


def _hook_count(model):
    return sum(len(m._forward_hooks) + len(m._backward_hooks) for m in model.modules())


def test_gradcam_removes_its_hooks_and_returns_normalized_map():
    from ai.explainability.gradcam import GradCAM

    model = torch.nn.Sequential(torch.nn.Conv2d(3, 4, 3, padding=1), torch.nn.ReLU(),
                                torch.nn.AdaptiveAvgPool2d(1), torch.nn.Flatten(), torch.nn.Linear(4, 2))
    x = torch.randn(1, 3, 32, 32)
    before = _hook_count(model)
    cam = GradCAM()
    for _ in range(3):
        heat = cam.explain(model, x, 1)
    assert _hook_count(model) == before
    assert heat.shape == (32, 32) and heat.min() >= 0 and heat.max() <= 1


def test_vit_rollout_reports_unavailability_instead_of_fake_map():
    from ai.explainability.attention_rollout import AttentionRolloutExplainer
    from ai.explainability.base import ExplanationUnavailableError

    model = torch.nn.Sequential(torch.nn.Flatten(), torch.nn.Linear(3 * 8 * 8, 2))
    with pytest.raises(ExplanationUnavailableError):
        AttentionRolloutExplainer().explain(model, torch.randn(1, 3, 8, 8), 0)


def test_unet_output_shape():
    from ai.segmentation.model import UNet

    out = UNet(base_channels=4, depth=3)(torch.randn(2, 3, 64, 64))
    assert out.shape == (2, 3, 64, 64)


def test_vectorized_dedup_matches_pairwise_imagehash(tmp_path):
    import imagehash

    from ai.data.dedup import DuplicateDetector

    rng = np.random.default_rng(0)
    paths = []
    for i in range(12):
        arr = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
        p = tmp_path / f"{i}.png"
        Image.fromarray(arr).save(p)
        paths.append(p)
    Image.open(paths[0]).save(tmp_path / "dup_exact.png")
    Image.open(paths[1]).resize((33, 33)).save(tmp_path / "dup_near.png")
    paths += [tmp_path / "dup_exact.png", tmp_path / "dup_near.png"]
    kept, dups = DuplicateDetector(hamming_threshold=4).deduplicate(paths)
    assert tmp_path / "dup_exact.png" in dups
    # reference implementation
    ref_hashes, ref_kept = [], []
    for p in paths:
        h = imagehash.average_hash(Image.open(p).convert("L"))
        if any(h - r <= 4 for r in ref_hashes):
            continue
        ref_hashes.append(h)
        ref_kept.append(p)
    assert kept == ref_kept


@pytest.fixture()
def tiny_run(tmp_path):
    from ai.data.label_encoder import LabelEncoder
    from ai.data.preprocessing import PreprocessingConfig
    from ai.models.architectures import build_classifier

    classes = ["tomato___early_blight", "tomato___late_blight", "potato___early_blight"]
    run = tmp_path / "run"
    run.mkdir()
    torch.manual_seed(0)
    model = build_classifier("mobilenetv4", num_classes=3, pretrained=False)
    torch.save(model.state_dict(), run / "model.pt")
    (run / "model_meta.json").write_text(json.dumps({"architecture": "mobilenetv4", "num_classes": 3, "image_size": 96}))
    LabelEncoder(classes).save(run / "label_encoder.json")
    PreprocessingConfig(96, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)).save(run / "preprocessing_config.json")
    return run


def test_inference_service_end_to_end(tiny_run, tmp_path):
    from ai.inference.inference_service import InferenceService

    class NoSeg:
        available = False

        def measure(self, *a, **k):
            from ai.segmentation.service import SegmentationResult
            return SegmentationResult(status="unavailable", reason="no_segmentation_model")

    svc = InferenceService(run_dir=tiny_run, segmentation_service=NoSeg())
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:256, 0:256]
    arr = np.clip(np.stack([60 + 0 * xx, 140 + 0 * xx, 50 + 0 * xx], -1) + (40 * np.sin(xx / 5))[..., None]
                  + rng.normal(0, 15, (256, 256, 1)), 0, 255).astype("uint8")
    out = svc.diagnose(Image.fromarray(arr), top_k=3, save_heatmap_to=tmp_path / "h.png")
    assert out.status == "completed"
    assert out.decision_status in {"confident", "uncertain", "inconclusive"}
    assert out.thresholds["source"] == "unvalidated_default" and out.thresholds["calibrated"] is False
    assert len(out.top_k) == 3 and abs(sum(c["confidence"] for c in out.top_k) - 100) < 0.5
    assert out.severity_level is None and out.affected_area_pct is None  # never derived from Grad-CAM
    assert out.model_version.startswith("run:")
    if out.decision_status != "inconclusive":
        assert out.explanation["available"] and (tmp_path / "h.png").exists()

    dark = svc.diagnose(Image.new("RGB", (300, 300), (2, 2, 2)))
    assert dark.status == "rejected_quality" and dark.decision_status is None
