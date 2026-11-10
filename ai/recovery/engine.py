"""
Recovery assessment rules (method "rules-v1") — pure Python, shared by the backend
and the calibration script (ai/recovery/calibrate.py).

Inputs are the chronological scans of ONE tracked plant. The only quantity treated as
evidence of improvement or worsening is the measured affected-area percentage from the
segmentation model, and only when two measurements are comparable:
  - both come from the same segmentation model name + version,
  - both have a valid denominator (plant tissue pixels; `area_pct` is not None),
  - neither image failed the quality checks that matter (blurry/dark/overexposed),
  - they are at least `min_days_between` apart.
Everything else is reported as an indicator with its limitation but never decides the
status on its own:
  - classifier confidence is not a measure of recovery;
  - a changed predicted label (e.g. now "healthy") is not proof of recovery;
  - Grad-CAM-based severity is an explanation heatmap, not a measurement.

Status: improving | stable | worsening | inconclusive | insufficient_data.
Thresholds live in RecoveryRules (configs/recovery/rules.json) so they can be
calibrated against labeled longitudinal data later.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ai.config import PROJECT_ROOT

RULES_PATH = PROJECT_ROOT / "configs" / "recovery" / "rules.json"
STATUSES = ("improving", "stable", "worsening", "inconclusive", "insufficient_data")


@dataclass
class RecoveryRules:
    method_version: str = "rules-v1"
    stable_band_pct: float = 5.0          # |change in affected %| below this = stable (percentage points)
    min_days_between: float = 1.0          # measurements closer than this are not compared
    blocking_quality_issues: List[str] = field(default_factory=lambda: ["blurry", "too_dark", "overexposed"])

    @classmethod
    def load(cls, path: Path = RULES_PATH) -> "RecoveryRules":
        if not Path(path).is_file():
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.pop("_comment", None)
        return cls(**data)


@dataclass
class ScanSnapshot:
    diagnosis_id: str
    taken_at: datetime
    condition: Optional[str] = None           # predicted condition label
    is_healthy: Optional[bool] = None
    confidence: Optional[float] = None        # classifier confidence, 0-100
    area_pct: Optional[float] = None          # segmentation affected-area % (None = not measured / invalid)
    area_model: Optional[str] = None          # "<model name>@<version>" of the segmentation model
    quality_issues: List[str] = field(default_factory=list)
    treatment_stage: Optional[str] = None


@dataclass
class Assessment:
    status: str
    method_version: str
    baseline_diagnosis_id: Optional[str]
    latest_diagnosis_id: Optional[str]
    indicators: List[dict] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    area_series: List[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _usable_area(s: ScanSnapshot, rules: RecoveryRules) -> bool:
    return s.area_pct is not None and s.area_model is not None and not (set(s.quality_issues) & set(rules.blocking_quality_issues))


def assess(snapshots: List[ScanSnapshot], rules: Optional[RecoveryRules] = None) -> Assessment:
    rules = rules or RecoveryRules()
    scans = sorted(snapshots, key=lambda s: s.taken_at)
    if len(scans) < 2:
        return Assessment("insufficient_data", rules.method_version,
                          scans[0].diagnosis_id if scans else None, scans[-1].diagnosis_id if scans else None,
                          limitations=["needs_two_scans"],
                          summary="At least two scans of this plant are needed to assess change.")
    baseline, latest = scans[0], scans[-1]
    indicators, limitations = [], []

    span_days = (latest.taken_at - baseline.taken_at).total_seconds() / 86400
    indicators.append({"code": "days_between_first_and_latest", "value": round(span_days, 1)})
    if baseline.condition != latest.condition:
        indicators.append({"code": "classification_changed", "from": baseline.condition, "to": latest.condition,
                           "note": "a different predicted label is not, by itself, evidence of recovery"})
        if latest.is_healthy:
            limitations.append("label_change_alone_insufficient")
    if baseline.confidence is not None and latest.confidence is not None:
        indicators.append({"code": "classifier_confidence", "from": baseline.confidence, "to": latest.confidence,
                           "note": "classifier confidence measures certainty of the label, not plant health"})
    poor = [s.diagnosis_id for s in scans if set(s.quality_issues) & set(rules.blocking_quality_issues)]
    if poor:
        indicators.append({"code": "poor_quality_scans", "diagnosis_ids": poor})
        limitations.append("some_images_failed_quality_checks")

    # Area measurements from the latest scan's segmentation model, quality-checked.
    reference_model = next((s.area_model for s in reversed(scans) if _usable_area(s, rules)), None)
    measured = [s for s in scans if s.area_pct is not None]
    if not measured:
        limitations.append("area_comparison_unavailable")
    series = [s for s in scans if _usable_area(s, rules) and s.area_model == reference_model]
    if measured and len({s.area_model for s in measured}) > 1:
        limitations.append("incompatible_segmentation_models")
    area_series = [{"diagnosis_id": s.diagnosis_id, "taken_at": s.taken_at.isoformat(), "area_pct": s.area_pct,
                    "model": s.area_model} for s in series]

    if len(series) < 2 or (series[-1].taken_at - series[0].taken_at).total_seconds() / 86400 < rules.min_days_between:
        if len(series) >= 2:
            limitations.append("measurements_too_close_in_time")
        elif measured:
            limitations.append("fewer_than_two_comparable_measurements")
        return Assessment("inconclusive", rules.method_version, baseline.diagnosis_id, latest.diagnosis_id,
                          indicators, sorted(set(limitations)), area_series,
                          "No two comparable affected-area measurements are available, so change can't be assessed.")

    first, last = series[0], series[-1]
    delta = round(last.area_pct - first.area_pct, 2)
    indicators.append({"code": "affected_area_change_pct_points", "from": first.area_pct, "to": last.area_pct,
                       "value": delta, "model": reference_model})
    if len(series) >= 3:
        xs = [(s.taken_at - first.taken_at).total_seconds() / 86400 for s in series]
        ys = [s.area_pct for s in series]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
        indicators.append({"code": "affected_area_trend_pct_points_per_day", "value": round(slope, 3)})
        if (slope < 0) != (delta < 0) and abs(delta) >= rules.stable_band_pct:
            limitations.append("trend_disagrees_with_endpoints")

    if abs(delta) < rules.stable_band_pct:
        status = "stable"
    else:
        status = "improving" if delta < 0 else "worsening"
    if "trend_disagrees_with_endpoints" in limitations:
        status = "inconclusive"
    summary = {
        "improving": f"Measured affected area fell from {first.area_pct:.1f}% to {last.area_pct:.1f}%.",
        "worsening": f"Measured affected area rose from {first.area_pct:.1f}% to {last.area_pct:.1f}%.",
        "stable": f"Measured affected area changed by {delta:+.1f} points (within ±{rules.stable_band_pct:g}).",
        "inconclusive": "Measurements point in different directions over time.",
    }[status]
    return Assessment(status, rules.method_version, baseline.diagnosis_id, latest.diagnosis_id, indicators,
                      sorted(set(limitations)), area_series, summary)
