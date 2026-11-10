"""
Trained outbreak model wrapper (bundle written by ai.outbreak.train).

The bundle is a joblib/pickle file produced locally by the training script; only load
bundles you trained yourself (pickle can execute code).

Scores: when the run was calibrated on validation data the score is a calibrated
probability ("calibrated_probability"); otherwise it is an uncalibrated "risk_score"
and must not be presented as a probability.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ai import registry
from ai.outbreak.features import FEATURE_NAMES, FEATURE_VERSION

RISK_LEVELS = ("low", "moderate", "high", "critical")


def to_matrix(rows: List[Dict], crops: List[str], diseases: List[str]) -> np.ndarray:
    """Feature matrix: FEATURE_NAMES (NaN for missing) + crop and disease codes."""
    matrix = np.full((len(rows), len(FEATURE_NAMES) + 2), np.nan, dtype=np.float64)
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            value = row.get(name)
            if value is not None and value == value:
                matrix[i, j] = float(value)
        matrix[i, -2] = crops.index(row["crop"]) if row["crop"] in crops else np.nan
        matrix[i, -1] = diseases.index(row["disease"]) if row["disease"] in diseases else np.nan
    return matrix


def risk_level(score: float, cutpoints: List[float]) -> str:
    for level, cut in zip(RISK_LEVELS, cutpoints):
        if score < cut:
            return level
    return RISK_LEVELS[-1]


def apply_calibration(bundle: dict, raw: np.ndarray) -> np.ndarray:
    calibrator = bundle.get("calibrator")
    if calibrator is None:
        return raw
    if bundle["calibration"] == "isotonic":
        return np.clip(calibrator.predict(raw), 0.0, 1.0)
    return calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]


class OutbreakModel:
    def __init__(self, run_dir: Optional[Path] = None):
        import joblib

        self.run_dir = run_dir or registry.latest_run_dir("outbreak")
        if self.run_dir is None:
            raise FileNotFoundError("No trained outbreak model (artifacts/outbreak/runs/latest.json).")
        self.card = registry.read_model_card(self.run_dir)
        self.bundle = joblib.load(self.run_dir / "model.joblib")
        if self.bundle.get("feature_version") != FEATURE_VERSION:
            raise ValueError(f"model was trained on {self.bundle.get('feature_version')}, code computes {FEATURE_VERSION}")

    @property
    def calibrated(self) -> bool:
        return self.bundle.get("calibrator") is not None

    def supports(self, crop: str, disease: str) -> bool:
        return [crop, disease] in self.bundle["pairs"]

    @property
    def grid_resolution_deg(self) -> Optional[float]:
        return self.bundle.get("grid_resolution_deg")

    def covers(self, lat_index: int, lon_index: int) -> Optional[bool]:
        """Whether a cell lies inside the training area (or next to it). None for runs
        trained before the extent was recorded."""
        extent = self.bundle.get("extent")
        if not extent:
            return None
        (lat_lo, lat_hi), (lon_lo, lon_hi) = extent["lat_index"], extent["lon_index"]
        return lat_lo - 1 <= lat_index <= lat_hi + 1 and lon_lo - 1 <= lon_index <= lon_hi + 1

    def predict(self, features: Dict, crop: str, disease: str) -> dict:
        row = dict(features, crop=crop, disease=disease)
        raw = self.bundle["model"].predict_proba(to_matrix([row], self.bundle["crops"], self.bundle["diseases"]))[:, 1]
        score = float(apply_calibration(self.bundle, raw)[0])
        return {"score": round(score, 4), "score_kind": "calibrated_probability" if self.calibrated else "risk_score",
                "risk_level": risk_level(score, self.bundle["risk_cutpoints"])}

    def explain(self, features: Dict, top: int = 6) -> List[dict]:
        """Global (validation permutation) importance of each feature, with this
        prediction's value compared with the training distribution. This is not a
        per-prediction attribution."""
        factors = []
        for name, importance in sorted(self.bundle["importance"].items(), key=lambda kv: -kv[1])[:top]:
            value, ref = features.get(name), self.bundle["reference"].get(name, {})
            if value is None:
                relation = "missing"
            elif ref.get("p25") is None or ref.get("p75") is None:
                relation = "not_in_training_data"  # e.g. trained without weather data
            elif value > ref["p75"]:
                relation = "above_typical"
            elif value < ref["p25"]:
                relation = "below_typical"
            else:
                relation = "typical"
            factors.append({"feature": name, "value": value, "importance": round(float(importance), 4),
                            "relation": relation, "typical_range": [ref.get("p25"), ref.get("p75")] if ref else None})
        return factors
