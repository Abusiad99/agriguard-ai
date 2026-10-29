"""
Careful comparison of two observations (diagnoses) of the same plant.

Principles:
  * A change in the model's predicted label is NOT evidence that the plant improved
    or deteriorated — two photos can differ in lighting, angle, framing, and the
    model is uncertain. Differing predictions are reported as such.
  * Only affected-area MEASUREMENTS (from the leaf/lesion segmentation model) are
    compared numerically, and only when both come from the same method and model
    version, on photos without quality warnings. Legacy Grad-CAM-threshold numbers
    are never compared.
  * A numeric change is called "increase"/"decrease" only when it exceeds the
    measurement tolerance. If no validated tolerance exists (no segmentation
    evaluation yet), the change is reported but labelled as not established.

The output uses stable codes that the frontend localizes (AR/EN).
"""
from __future__ import annotations

from typing import List, Optional

from app.domain.entities.diagnosis import Diagnosis


def _quality_ok(d: Diagnosis) -> bool:
    return (d.image_quality or {}).get("status", "ok") == "ok"


def compare_observations(a: Diagnosis, b: Diagnosis,
                         measurement_tolerance_pct_points: Optional[float] = None) -> dict:
    def _ts(d: Diagnosis) -> float:
        return d.diagnosed_at.timestamp() if d.diagnosed_at else 0.0

    earlier, later = (a, b) if _ts(a) <= _ts(b) else (b, a)
    issues: List[str] = []

    same_plant = earlier.plant_profile_id is not None and earlier.plant_profile_id == later.plant_profile_id
    if not same_plant:
        issues.append("different_or_unassigned_plants")
    if earlier.is_legacy or later.is_legacy:
        issues.append("legacy_observation")
    if earlier.model_version and later.model_version and earlier.model_version != later.model_version:
        issues.append("different_model_versions")
    if not (_quality_ok(earlier) and _quality_ok(later)):
        issues.append("photo_quality_warnings")
    if earlier.decision_status != "confident" or later.decision_status != "confident":
        issues.append("not_both_confident")

    days_between = None
    if earlier.diagnosed_at and later.diagnosed_at:
        days_between = round((later.diagnosed_at - earlier.diagnosed_at).total_seconds() / 86400, 1)

    # --- Predicted condition ---
    if earlier.predicted_label and later.predicted_label:
        prediction_change = "same_prediction" if earlier.predicted_label == later.predicted_label else "different_prediction"
    else:
        prediction_change = "prediction_unavailable"

    # --- Affected-area measurement ---
    measurement = {"status": "unavailable", "reason": None, "earlier_pct": None, "later_pct": None,
                   "delta_pct_points": None, "tolerance_pct_points": measurement_tolerance_pct_points}
    if not (earlier.has_segmentation_measurement and later.has_segmentation_measurement):
        measurement["reason"] = "no_segmentation_measurement"
    elif earlier.severity_method != later.severity_method or (
            (earlier.segmentation or {}).get("model_version") != (later.segmentation or {}).get("model_version")):
        measurement["reason"] = "different_measurement_methods"
    elif not same_plant:
        measurement["reason"] = "different_or_unassigned_plants"
    else:
        delta = round(later.affected_area_pct - earlier.affected_area_pct, 2)
        measurement.update(earlier_pct=earlier.affected_area_pct, later_pct=later.affected_area_pct,
                           delta_pct_points=delta)
        if measurement_tolerance_pct_points is None:
            measurement["status"] = "change_not_established"
            measurement["reason"] = "measurement_error_not_validated"
        elif abs(delta) <= measurement_tolerance_pct_points:
            measurement["status"] = "within_measurement_uncertainty"
        elif not _quality_ok(earlier) or not _quality_ok(later):
            measurement["status"] = "change_not_established"
            measurement["reason"] = "photo_quality_warnings"
        else:
            measurement["status"] = "visible_area_increased" if delta > 0 else "visible_area_decreased"

    if measurement["status"] in ("visible_area_increased", "visible_area_decreased"):
        summary = measurement["status"]
    elif measurement["status"] == "within_measurement_uncertainty":
        summary = "no_clear_change_in_measurement"
    else:
        summary = "change_cannot_be_established"

    return {
        "earlier_id": str(earlier.id),
        "later_id": str(later.id),
        "same_plant": same_plant,
        "days_between": days_between,
        "prediction_change": prediction_change,
        "earlier_prediction": earlier.predicted_label,
        "later_prediction": later.predicted_label,
        "measurement": measurement,
        "comparability_issues": issues,
        "summary": summary,
        "caution": ("Differences between two photos can come from lighting, angle, framing and model "
                    "uncertainty. Do not treat a different prediction as proof that the plant improved or "
                    "deteriorated."),
    }
