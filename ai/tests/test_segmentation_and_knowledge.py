"""Affected-area arithmetic, segmentation metrics, COCO conversion, differential logic."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from ai.knowledge.differential import build_differential, validate_answers
from ai.knowledge.taxonomy import TAXONOMY, describe
from ai.segmentation.masks import IGNORE, measure_from_class_map, measure_from_masks
from ai.segmentation.metrics import SegmentationMeter
from ai.segmentation.severity_scales import categorize_severity, load_scales


def test_affected_area_excludes_background():
    m = np.zeros((100, 100), dtype=np.uint8)
    m[:, :50] = 1           # 5000 leaf pixels
    m[:10, :50] = 2         # 500 of them lesion
    r = measure_from_class_map(m)
    assert r.status == "measured" and r.affected_area_pct == 10.0 and r.leaf_pixels == 5000
    assert r.leaf_regions == 1 and r.lesion_regions == 1


def test_multiple_leaves_and_disconnected_lesions():
    m = np.zeros((100, 100), dtype=np.uint8)
    m[0:40, 0:40] = 1
    m[60:100, 60:100] = 1
    m[0:5, 0:5] = 2
    m[90:100, 90:100] = 2
    r = measure_from_class_map(m)
    assert r.leaf_regions == 2 and r.lesion_regions == 2
    assert r.affected_area_pct == round(100 * 125 / 3200, 2)


def test_ignore_pixels_are_excluded_and_invalid_masks_rejected():
    m = np.full((50, 50), IGNORE, dtype=np.uint8)
    m[:, :25] = 1
    m[:5, :25] = 2
    r = measure_from_class_map(m)
    assert r.affected_area_pct == 10.0 and r.image_pixels == 1250  # 255 pixels excluded entirely
    with pytest.raises(ValueError):
        measure_from_class_map(np.full((10, 10), 7, dtype=np.uint8))


def test_unavailable_when_leaf_missing_or_masks_inconsistent():
    assert measure_from_class_map(np.zeros((50, 50), dtype=np.uint8)).reason == "leaf_not_identified"
    leaf = np.zeros((50, 50), bool)
    leaf[:, :10] = True
    lesion = np.zeros((50, 50), bool)
    lesion[:, 20:30] = True
    r = measure_from_masks(leaf, lesion)
    assert r.status == "unavailable" and r.reason.startswith("inconsistent_masks")


def test_segmentation_metrics_iou_dice_and_area_error():
    gt = np.zeros((10, 10), dtype=np.uint8)
    gt[:, :5] = 1
    gt[:2, :5] = 2
    meter = SegmentationMeter()
    meter.update(gt.copy(), gt, "perfect")
    s = meter.summary()
    assert s["mean_iou"] == pytest.approx(1.0) and s["affected_area_mae_pct_points"] == 0.0
    pred = gt.copy()
    pred[2:4, :5] = 2  # over-segment lesion
    meter2 = SegmentationMeter()
    meter2.update(pred, gt)
    s2 = meter2.summary()
    assert s2["per_class"]["lesion"]["iou"] == pytest.approx(10 / 20)
    assert s2["per_class"]["lesion"]["dice"] == pytest.approx(2 * 10 / 30)
    assert s2["affected_area_mae_pct_points"] == pytest.approx(20.0)


def test_no_severity_category_without_a_configured_scale(tmp_path, monkeypatch):
    load_scales.cache_clear()
    assert categorize_severity(42.0, plant="tomato", condition="early_blight") == {"level": None, "basis": "no_validated_scale"}
    f = tmp_path / "scales.json"
    f.write_text(json.dumps({
        "tomato___early_blight": {"source": "test scale (fixture)", "bands": [{"max_pct": 10, "level": "mild"},
                                                                             {"max_pct": 100, "level": "severe"}]},
        "potato": {"bands": [{"max_pct": 100, "level": "mild"}]},  # no source -> ignored
    }))
    monkeypatch.setenv("AGRIGUARD_SEVERITY_SCALES_FILE", str(f))
    load_scales.cache_clear()
    assert categorize_severity(5, plant="tomato", condition="early_blight")["level"] == "mild"
    assert categorize_severity(5, plant="potato", condition="late_blight")["level"] is None
    load_scales.cache_clear()


def test_coco_conversion(tmp_path):
    from ai.segmentation.convert_coco import convert
    from ai.segmentation.data import discover_samples

    Image.new("RGB", (40, 30), (0, 128, 0)).save(tmp_path / "a.jpg")
    coco = {
        "images": [{"id": 1, "file_name": "a.jpg", "width": 40, "height": 30},
                   {"id": 2, "file_name": "missing.jpg", "width": 10, "height": 10}],
        "categories": [{"id": 1, "name": "leaf"}, {"id": 2, "name": "lesion"}],
        "annotations": [
            {"image_id": 1, "category_id": 1, "segmentation": [[0, 0, 20, 0, 20, 30, 0, 30]]},
            {"image_id": 1, "category_id": 2, "segmentation": [[2, 2, 8, 2, 8, 8, 2, 8]]},
            {"image_id": 1, "category_id": 2, "segmentation": [[30, 2, 35, 2, 35, 8, 30, 8]]},  # outside leaf
        ],
    }
    (tmp_path / "coco.json").write_text(json.dumps(coco))
    out = tmp_path / "seg" / "set1"
    stats = convert(tmp_path / "coco.json", tmp_path, out, {"leaf"}, {"lesion"})
    assert stats["converted"] == 1 and stats["skipped_missing_image"] == 1 and stats["lesion_pixels_outside_leaf"] > 0
    mask = np.asarray(Image.open(out / "masks" / "a.png"))
    assert set(np.unique(mask).tolist()) <= {0, 1, 2, 255} and (mask == 2).any() and (mask == 255).any()
    report = discover_samples(tmp_path / "seg")
    assert len(report.samples) == 1 and not report.invalid


def test_differential_marks_unsupported_categories_and_never_changes_probabilities():
    cands = [{"canonical": "tomato___early_blight", "plant": "tomato", "condition": "early_blight", "confidence": 55.0},
             {"canonical": "tomato___mosaic_virus", "plant": "tomato", "condition": "mosaic_virus", "confidence": 30.0}]
    d = build_differential(cands, "uncertain", {"pests_seen": "yes", "bogus": "x"})
    assert [c["probability_pct"] for c in d["model_candidates"]] == [55.0, 30.0]
    assert d["expert_review_recommended"] and "candidates_differ_in_cause_type" in d["expert_review_reasons"]
    assert "insect_or_mite_damage" in d["also_consider"]
    assert "nutrient_deficiency" in d["not_assessable_by_model"]
    assert d["answers"] == {"pests_seen": "yes"}
    assert any(h["code"] == "pests_seen_check_pest_damage" for h in d["hints"])
    inconclusive = build_differential(cands, "inconclusive", {"recent_weather": "wet_or_humid"})
    assert inconclusive["model_candidates"] == [] and inconclusive["also_consider"] == []
    assert len(inconclusive["follow_up_questions"]) == 8  # nothing hidden steers the questions
    assert not any("foliar" in h["code"] for h in inconclusive["hints"])  # no hint from hidden causes


def test_negligible_candidates_do_not_trigger_expert_review_for_a_confident_result():
    cands = [{"canonical": "eggplant___cercospora_leaf_spot", "confidence": 93.8},
             {"canonical": "zucchini___yellow_mosaic_virus", "confidence": 2.9},
             {"canonical": "citrus___citrus_greening", "confidence": 1.2}]
    d = build_differential(cands, "confident")
    assert not d["expert_review_recommended"] and d["regulated_candidates"] == []
    cands[2]["confidence"] = 6.0  # a regulated pathogen is flagged from 5 %
    assert build_differential(cands, "confident")["expert_review_reasons"] == ["possible_regulated_pathogen"]


def test_answer_validation_and_taxonomy():
    assert validate_answers({"affected_parts": ["leaves", "x"], "duration": "forever", "pests_seen": "no"}) == \
        {"affected_parts": ["leaves"], "pests_seen": "no"}
    assert describe("citrus___citrus_greening")["regulated"] is True
    assert describe("nonexistent___label")["cause_type"] == "unknown"
    assert all(v["cause_type"] in {"fungal", "oomycete", "bacterial", "viral", "physiological"} for v in TAXONOMY.values())
