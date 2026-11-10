"""Recovery assessment rules: only comparable measured area decides the status."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai.recovery.engine import RecoveryRules, ScanSnapshot, assess

T0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
MODEL = "disease-segmentation@run1"


def snap(day, area=None, model=MODEL, condition="late_blight", confidence=90.0, issues=None, i=None):
    return ScanSnapshot(diagnosis_id=f"d{i if i is not None else day}", taken_at=T0 + timedelta(days=day),
                        condition=condition, is_healthy=condition == "healthy", confidence=confidence,
                        area_pct=area, area_model=model if area is not None else None, quality_issues=issues or [])


def test_one_scan_is_insufficient():
    result = assess([snap(0, 30)])
    assert result.status == "insufficient_data" and "needs_two_scans" in result.limitations


def test_no_measurements_is_inconclusive_not_improving():
    result = assess([snap(0), snap(10, condition="healthy", confidence=99)])
    assert result.status == "inconclusive"
    assert {"area_comparison_unavailable", "label_change_alone_insufficient"} <= set(result.limitations)
    codes = {i["code"] for i in result.indicators}
    assert {"classification_changed", "classifier_confidence"} <= codes


def test_improving_worsening_stable():
    assert assess([snap(0, 40), snap(10, 20)]).status == "improving"
    assert assess([snap(0, 20), snap(10, 40)]).status == "worsening"
    stable = assess([snap(0, 20), snap(10, 23)])
    assert stable.status == "stable"
    change = next(i for i in stable.indicators if i["code"] == "affected_area_change_pct_points")
    assert change["value"] == 3.0


def test_measurements_from_different_models_are_not_compared():
    result = assess([snap(0, 40, model="seg@v1"), snap(10, 10, model="seg@v2")])
    assert result.status == "inconclusive"
    assert "incompatible_segmentation_models" in result.limitations


def test_poor_quality_images_are_excluded():
    result = assess([snap(0, 40, issues=["blurry"]), snap(10, 10)])
    assert result.status == "inconclusive"
    assert "some_images_failed_quality_checks" in result.limitations


def test_measurements_too_close_in_time():
    result = assess([snap(0, 40, i=0), snap(0.2, 10, i=1)], RecoveryRules(min_days_between=1))
    assert result.status == "inconclusive" and "measurements_too_close_in_time" in result.limitations


def test_trend_disagreeing_with_endpoints_is_inconclusive():
    scans = [snap(0, 30, i=0), snap(5, 5, i=1), snap(6, 5, i=2), snap(7, 5, i=3), snap(30, 40, i=4)]
    result = assess(scans)
    assert result.status in ("inconclusive", "worsening")
    assert any(i["code"] == "affected_area_trend_pct_points_per_day" for i in result.indicators)


def test_thresholds_are_configurable():
    scans = [snap(0, 20), snap(10, 26)]
    assert assess(scans, RecoveryRules(stable_band_pct=5)).status == "worsening"
    assert assess(scans, RecoveryRules(stable_band_pct=10)).status == "stable"


def test_order_of_input_does_not_matter():
    assert assess([snap(10, 20), snap(0, 40)]).status == "improving"


def test_calibration_recommends_the_middle_of_tied_bands(tmp_path):
    """SYNTHETIC labeled pairs whose changes are far from any band: every band ties, and
    the recommendation is not the noise-sensitive smallest one."""
    import csv

    from ai.recovery.calibrate import BANDS, calibrate

    raw = tmp_path / "raw"
    for sub in ("plants", "scans", "annotations"):
        (raw / sub).mkdir(parents=True)

    def write(path, rows):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    plants, scans, labels = [], [], []
    for i, (a, b, status) in enumerate([(30, 5, "improving"), (10, 40, "worsening"), (20, 20, "stable")]):
        pid = f"p{i}"
        plants.append({"plant_id": pid, "crop": "tomato"})
        for j, (day, pct) in enumerate([("2026-01-01", a), ("2026-01-15", b)]):
            (raw / "scans" / f"{pid}_{j}.png").write_bytes(b"")
            scans.append({"scan_id": f"{pid}_{j}", "plant_id": pid, "scan_date": day, "image_file": f"{pid}_{j}.png",
                          "affected_area_pct": pct})
        labels.append({"plant_id": pid, "from_scan_id": f"{pid}_0", "to_scan_id": f"{pid}_1", "status": status})
    write(raw / "plants" / "plants.csv", plants)
    write(raw / "scans" / "scans.csv", scans)
    write(raw / "annotations" / "recovery_labels.csv", labels)

    out = calibrate(tmp_path)
    assert out["best_accuracy"] == 1.0 and out["tied_best_bands"] == BANDS
    assert out["recommended_stable_band_pct"] == BANDS[len(BANDS) // 2]
