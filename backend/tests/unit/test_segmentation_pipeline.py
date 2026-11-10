"""
Disease localization pipeline on SYNTHETIC data (tests/synthetic_fixtures.py):
adapters, validator, preprocessing (incl. leakage-safe splitting), area maths,
training/resume/evaluation and inference. Says nothing about real accuracy.
"""
from __future__ import annotations

import json
import shutil

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("torch")
pytest.importorskip("scipy")

from ai.segmentation.adapters import iter_samples, render_mask  # noqa: E402
from ai.segmentation.classes import ClassMapping  # noqa: E402
from ai.segmentation.config import SegmentationConfig  # noqa: E402
from ai.segmentation.inference import compute_area_stats, extract_regions  # noqa: E402
from ai.segmentation.preprocess import preprocess  # noqa: E402
from ai.segmentation.validate import validate_dataset  # noqa: E402
from tests.synthetic_fixtures import SEG_MAPPING, make_segmentation_dataset  # noqa: E402

TINY = dict(encoder="resnet10t", encoder_pretrained=False, image_size=64, batch_size=8, num_workers=0,
            min_train_images=1, min_leaf_pixels=20, mixed_precision=False, device="cpu")


def _codes(report, severity=None):
    return {i["code"] for i in report["issues"] if severity is None or i["severity"] == severity}


class TestAffectedArea:
    mapping = ClassMapping.from_dict(SEG_MAPPING)

    def test_percentage_uses_plant_pixels_not_the_whole_image(self):
        mask = np.zeros((40, 50), dtype=np.uint8)      # 2000 px, mostly background
        mask[:10, :60] = 1                              # 500 leaf px
        mask[10:12, :50] = 2                            # 100 lesion px
        stats = compute_area_stats(mask, self.mapping, min_plant_pixels=10)
        assert stats["affected_pixels"] == 100
        assert stats["plant_pixels"] == 600
        assert stats["affected_area_pct"] == pytest.approx(100 * 100 / 600, abs=0.01)
        assert stats["area_basis"] == "plant_pixels"

    def test_no_percentage_without_leaf_annotation(self):
        binary = ClassMapping.from_dict({"classes": [
            {"id": 0, "name": "background", "kind": "background", "color": [0, 0, 0], "source_values": [0]},
            {"id": 1, "name": "lesion", "kind": "disease", "color": [255, 0, 0], "source_values": [255]}]})
        mask = np.zeros((10, 10), dtype=np.uint8)
        mask[:2] = 1
        stats = compute_area_stats(mask, binary, min_plant_pixels=1)
        assert stats["affected_pixels"] == 20
        assert stats["affected_area_pct"] is None
        assert stats["area_unavailable_reason"] == "model_does_not_segment_leaf_tissue"

    def test_no_percentage_when_too_little_plant_is_found(self):
        mask = np.zeros((10, 10), dtype=np.uint8)
        mask[0, :3] = 2
        stats = compute_area_stats(mask, self.mapping, min_plant_pixels=50)
        assert stats["affected_area_pct"] is None
        assert stats["area_unavailable_reason"] == "too_little_plant_tissue_detected"

    def test_regions_have_bounding_boxes(self):
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[2:7, 3:9] = 2
        mask[12:18, 12:18] = 2
        regions = extract_regions(mask, np.full((20, 20), 0.9, dtype=np.float32), self.mapping)
        assert [r["pixels"] for r in regions] == [36, 30]
        assert regions[1]["bbox"] == {"x_min": 3, "y_min": 2, "x_max": 8, "y_max": 6}
        assert regions[0]["mean_confidence"] == pytest.approx(0.9)


class TestAdapters:
    @pytest.mark.parametrize("fmt", ["masks", "coco", "yolo"])
    def test_every_format_renders_leaf_and_lesion_pixels(self, tmp_path, fmt):
        root = make_segmentation_dataset(tmp_path / fmt, n=4, fmt=fmt)
        mapping = ClassMapping.load(root / "manifests" / "class_mapping.json")
        samples = list(iter_samples(root / "raw", fmt))
        assert len(samples) == 4
        mask = render_mask(samples[0], mapping, (64, 64))
        values = set(np.unique(mask).tolist())
        assert {0, 1, 2} <= values  # background, leaf, lesion all present

    def test_lesions_are_drawn_over_leaf_in_polygon_formats(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "coco", n=2, fmt="coco")
        mapping = ClassMapping.load(root / "manifests" / "class_mapping.json")
        mask = render_mask(next(iter_samples(root / "raw", "coco")), mapping, (64, 64))
        assert (mask == 2).sum() > 0


class TestValidator:
    def test_clean_dataset_is_ready(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=6)
        report = validate_dataset(root)
        assert report["summary"]["ready_for_preprocessing"] is True
        assert (root / "reports" / "validation_report.json").is_file()
        assert (root / "reports" / "validation_summary.md").is_file()

    def test_reports_each_problem_with_its_file(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=8)
        raw = root / "raw"
        (raw / "masks" / "img_000.png").unlink()                                   # missing mask
        Image.new("L", (32, 32)).save(raw / "masks" / "img_001.png")               # dimension mismatch
        Image.fromarray(np.full((64, 64), 7, dtype=np.uint8)).save(raw / "masks" / "img_002.png")  # unexpected id
        (raw / "images" / "img_003.png").write_bytes(b"not an image")            # corrupt
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(raw / "masks" / "img_004.png")   # empty mask
        shutil.copy(raw / "images" / "img_005.png", raw / "images" / "img_099.png")              # duplicate
        shutil.copy(raw / "masks" / "img_005.png", raw / "masks" / "img_099.png")
        Image.new("L", (64, 64)).save(raw / "masks" / "orphan.png")                # mask without image
        report = validate_dataset(root)
        errors = {i["code"]: i["file"] for i in report["issues"] if i["severity"] == "error"}
        assert errors["missing_mask"] == "img_000.png"
        assert errors["dimension_mismatch"] == "img_001.png"
        assert errors["unexpected_class_id"] == "img_002.png"
        assert errors["corrupt_image"] == "img_003.png"
        assert "missing_image" in errors
        assert {"empty_mask", "duplicate_image"} <= _codes(report, "warning")
        assert report["summary"]["ready_for_preprocessing"] is False

    def test_invalid_polygons_are_errors(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=3, fmt="yolo")
        (root / "raw" / "annotations" / "img_000.txt").write_text("2 0.1 0.1 0.2 0.2\n9 0.1 0.1 0.5 0.1 0.5 0.5\n")
        report = validate_dataset(root)
        assert {"invalid_polygon", "unexpected_class_id"} <= _codes(report, "error")

    def test_missing_class_mapping_is_reported(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=2)
        (root / "manifests" / "class_mapping.json").unlink()
        assert "missing_class_mapping" in _codes(validate_dataset(root), "error")


class TestPreprocess:
    def test_refuses_invalid_data_unless_told_to_exclude_it(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=8)
        (root / "raw" / "masks" / "img_000.png").unlink()
        with pytest.raises(SystemExit):
            preprocess(root, SegmentationConfig(**TINY))
        manifest = preprocess(root, SegmentationConfig(**TINY), exclude_invalid=True)
        assert manifest["num_samples"] == 7
        assert manifest["excluded"][0]["file"] == "img_000.png"

    def test_group_and_duplicate_aware_split(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=24)
        raw = root / "raw"
        shutil.copy(raw / "images" / "img_000.png", raw / "images" / "img_dup.png")
        shutil.copy(raw / "masks" / "img_000.png", raw / "masks" / "img_dup.png")
        manifest = preprocess(root, SegmentationConfig(**TINY))
        split_of = {s["source"]: s["split"] for s in manifest["samples"]}
        for i in range(0, 24, 2):  # photos of the same synthetic plant never straddle splits
            assert split_of[f"img_{i:03d}.png"] == split_of[f"img_{i + 1:03d}.png"]
        assert split_of["img_dup.png"] == split_of["img_000.png"]
        assert sum(manifest["splits"].values()) == 25 and all(manifest["splits"].values())
        # masks keep exact class ids (nearest-neighbour), and the manifest is reproducible
        mask_file = next((root / "processed" / "masks").glob("*.png"))
        assert set(np.unique(np.asarray(Image.open(mask_file))).tolist()) <= {0, 1, 2}
        assert preprocess(root, SegmentationConfig(**TINY))["dataset_version"] == manifest["dataset_version"]

    def test_resizing_never_interpolates_mask_values(self, tmp_path):
        root = make_segmentation_dataset(tmp_path / "ds", n=4, size=96)
        preprocess(root, SegmentationConfig(**{**TINY, "max_side": 50}))
        for mask_file in (root / "processed" / "masks").glob("*.png"):
            arr = np.asarray(Image.open(mask_file))
            assert max(arr.shape) <= 50
            assert set(np.unique(arr).tolist()) <= {0, 1, 2}


class TestTrainingEvaluationInference:
    def test_train_resume_evaluate_and_segment(self, tmp_path):
        from ai import registry
        from ai.segmentation.evaluate import evaluate
        from ai.segmentation.inference import SegmentationService
        from ai.segmentation.train import DatasetNotReady, train
        from ai.segmentation.visualize import save_artifacts

        root = make_segmentation_dataset(tmp_path / "ds", n=16)
        with pytest.raises(DatasetNotReady):
            train(root, SegmentationConfig(**TINY))  # not preprocessed yet
        preprocess(root, SegmentationConfig(**TINY))
        run_dir = train(root, SegmentationConfig(**{**TINY, "epochs": 2}), allow_small=True)
        for name in ("best.pt", "last.pt", "config.json", "class_mapping.json", "history.json", "model_card.json",
                     "manifest_ref.json", "train.log"):
            assert (run_dir / name).is_file(), name
        assert registry.latest_run_dir("segmentation") == run_dir
        card = registry.describe("segmentation")
        assert card.is_ready and card.dataset_version and card.classes == ["background", "leaf", "lesion"]

        resumed = train(root, SegmentationConfig(**{**TINY, "epochs": 3}), resume=run_dir, allow_small=True)
        assert resumed == run_dir
        assert len(json.loads((run_dir / "history.json").read_text())) == 3

        metrics = evaluate(root, run_dir, split="test", examples=2)
        assert set(metrics["per_class"]) == {"background", "leaf", "lesion"}
        assert (run_dir / "evaluation" / "test" / "confusion_matrix.png").is_file()
        assert list((run_dir / "evaluation" / "test" / "failures").glob("*.png"))

        service = SegmentationService(run_dir, device="cpu")
        image = Image.open(next((root / "processed" / "images").glob("*.png")))
        result = service.segment(image)
        assert result.status == "ok" and result.mask.shape == (image.height, image.width)
        if result.affected_area_pct is not None:  # only with a valid denominator
            assert 0 <= result.affected_area_pct <= 100 and result.plant_pixels > 0
        files = save_artifacts(result.mask, service.mapping, tmp_path / "out")
        for name in files.values():
            assert (tmp_path / "out" / name).is_file()
        assert Image.open(tmp_path / "out" / files["overlay"]).mode == "RGBA"

    def test_too_small_dataset_is_refused_by_default(self, tmp_path):
        from ai.segmentation.train import DatasetNotReady, train

        root = make_segmentation_dataset(tmp_path / "ds", n=6)
        preprocess(root, SegmentationConfig(**TINY))
        with pytest.raises(DatasetNotReady):
            train(root, SegmentationConfig(**{**TINY, "min_train_images": 20}))


class TestOrientationAndLeakageGuards:
    def test_exif_rotated_photo_is_validated_and_used_upright(self, tmp_path):
        from PIL import Image, ImageDraw

        from ai.segmentation.config import SegmentationConfig
        from ai.segmentation.preprocess import preprocess
        from ai.segmentation.validate import validate_dataset

        root = make_segmentation_dataset(tmp_path / "seg", n=6, size=48)
        up = Image.new("RGB", (80, 48), (180, 180, 180))
        mask = Image.new("L", (80, 48), 0)
        ImageDraw.Draw(up).ellipse([5, 5, 75, 43], fill=(50, 140, 60))
        ImageDraw.Draw(mask).ellipse([5, 5, 75, 43], fill=1)
        exif = Image.Exif()
        exif[0x0112] = 6
        up.transpose(Image.ROTATE_90).save(root / "raw" / "images" / "phone.jpg", exif=exif.tobytes())
        mask.save(root / "raw" / "masks" / "phone.png")

        report = validate_dataset(root)
        codes = {(i["code"], i["file"]) for i in report["issues"]}
        assert ("exif_orientation", "phone.jpg") in codes and ("dimension_mismatch", "phone.jpg") not in codes
        preprocess(root, SegmentationConfig(min_train_images=1))
        processed = next((root / "processed" / "images").glob("phone*.png"))
        assert Image.open(processed).size == (80, 48)

    def test_resplitting_changes_the_dataset_version(self, tmp_path):
        from ai.segmentation.config import SegmentationConfig
        from ai.segmentation.preprocess import preprocess

        root = make_segmentation_dataset(tmp_path / "seg", n=24, size=32)
        first = preprocess(root, SegmentationConfig(min_train_images=1, seed=1))["dataset_version"]
        again = preprocess(root, SegmentationConfig(min_train_images=1, seed=1))["dataset_version"]
        other = preprocess(root, SegmentationConfig(min_train_images=1, seed=2))["dataset_version"]
        assert first == again and first != other

    def test_evaluate_refuses_a_dataset_the_model_was_not_trained_on(self, tmp_path, trained_segmentation_artifacts):
        from ai import registry
        from ai.config import CONFIG
        from ai.segmentation.config import SegmentationConfig
        from ai.segmentation.evaluate import evaluate
        from ai.segmentation.preprocess import preprocess

        root = make_segmentation_dataset(tmp_path / "other", n=12, size=32, seed=5)
        preprocess(root, SegmentationConfig(min_train_images=1))
        previous = CONFIG.paths.artifacts_dir
        CONFIG.paths.artifacts_dir = trained_segmentation_artifacts
        try:
            run = registry.latest_run_dir("segmentation")
            with pytest.raises(SystemExit, match="not the one this model was trained on"):
                evaluate(root, run, device="cpu")
            metrics = evaluate(root, run, device="cpu", allow_dataset_mismatch=True, examples=0)
            assert metrics["dataset_mismatch"] is True
        finally:
            CONFIG.paths.artifacts_dir = previous
