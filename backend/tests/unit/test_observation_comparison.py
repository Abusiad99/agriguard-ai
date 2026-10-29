"""Comparison never infers a health change from differing predictions alone."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.application.services.observation_comparison import compare_observations
from app.domain.entities.diagnosis import Diagnosis

PLANT = uuid.uuid4()


def _obs(days: int, label: str, affected=None, method=None, seg_version="seg:1", status="confident",
         quality="ok", plant=PLANT, model="m:1"):
    return Diagnosis(
        id=uuid.uuid4(), user_id=uuid.uuid4(), plant_id=None, disease_id=None, confidence_score=90.0,
        severity_level=None, affected_area_pct=affected, healthy_area_pct=None, original_image_ref="scans/x.jpg",
        diagnosed_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days), plant_profile_id=plant,
        decision_status=status, predicted_label=label, image_quality={"status": quality},
        segmentation={"model_version": seg_version} if method else {}, severity_method=method, model_version=model,
    )


def test_different_predictions_without_measurements_do_not_establish_change():
    r = compare_observations(_obs(0, "tomato___early_blight"), _obs(7, "tomato___late_blight"))
    assert r["prediction_change"] == "different_prediction"
    assert r["summary"] == "change_cannot_be_established"
    assert r["measurement"]["reason"] == "no_segmentation_measurement"
    assert r["days_between"] == 7.0


def test_measured_increase_beyond_tolerance():
    a = _obs(0, "tomato___early_blight", 10.0, "unet_semantic_segmentation")
    b = _obs(10, "tomato___early_blight", 30.0, "unet_semantic_segmentation")
    r = compare_observations(b, a, measurement_tolerance_pct_points=5.0)  # argument order must not matter
    assert r["earlier_id"] == str(a.id)
    assert r["measurement"]["delta_pct_points"] == 20.0
    assert r["summary"] == "visible_area_increased"


def test_within_tolerance_and_unvalidated_tolerance():
    a = _obs(0, "x___y", 10.0, "unet_semantic_segmentation")
    b = _obs(5, "x___y", 12.0, "unet_semantic_segmentation")
    assert compare_observations(a, b, 5.0)["summary"] == "no_clear_change_in_measurement"
    r = compare_observations(a, b, None)
    assert r["measurement"]["status"] == "change_not_established"
    assert r["summary"] == "change_cannot_be_established"


def test_legacy_estimates_and_mixed_methods_are_not_compared():
    a = _obs(0, "x___y", 10.0, "legacy_gradcam_threshold", status="legacy")
    b = _obs(5, "x___y", 40.0, "unet_semantic_segmentation")
    r = compare_observations(a, b, 5.0)
    assert r["measurement"]["status"] == "unavailable"
    assert "legacy_observation" in r["comparability_issues"]

    c = _obs(0, "x___y", 10.0, "unet_semantic_segmentation", seg_version="seg:1")
    d = _obs(5, "x___y", 40.0, "unet_semantic_segmentation", seg_version="seg:2")
    assert compare_observations(c, d, 5.0)["measurement"]["reason"] == "different_measurement_methods"


def test_different_plants_and_quality_warnings_are_flagged():
    a = _obs(0, "x___y", 10.0, "unet_semantic_segmentation")
    b = _obs(5, "x___y", 40.0, "unet_semantic_segmentation", plant=uuid.uuid4())
    r = compare_observations(a, b, 5.0)
    assert not r["same_plant"]
    assert r["summary"] == "change_cannot_be_established"

    e = _obs(0, "x___y", 10.0, "unet_semantic_segmentation")
    f = _obs(5, "x___y", 40.0, "unet_semantic_segmentation", quality="warning")
    r2 = compare_observations(e, f, 5.0)
    assert "photo_quality_warnings" in r2["comparability_issues"]
    assert r2["summary"] == "change_cannot_be_established"
