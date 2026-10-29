"""
Decision layer: turns calibrated class probabilities into an explicit decision
status instead of always forcing a single disease label.

Statuses
--------
confident     calibrated top-1 probability >= confident threshold. The prediction is
              shown as the leading result (still a model prediction, not a
              confirmed diagnosis).
uncertain     reject threshold <= top-1 < confident threshold. The system shows a
              short list of candidates and recommends a better photo or expert
              review; it does not present any single class as "the" diagnosis.
inconclusive  top-1 < reject threshold. Even the candidate shortlist was unreliable
              on validation data at this confidence, so no disease is named. This
              is also the status most likely (but NOT guaranteed) for images of
              diseases the model was never trained on.

The thresholds come from ai/config.py (env override) or the run's calibration.json
(validation-selected) — see `resolve_thresholds`. The source is always reported.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ai.config import CONFIG
from ai.inference.calibration import CalibrationArtifact

CONFIDENT = "confident"
UNCERTAIN = "uncertain"
INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class DecisionThresholds:
    confident: float
    reject: float
    plant_mass: Optional[float]
    source: str  # "env_override" | "validation" | "unvalidated_default"
    temperature: float
    calibrated: bool

    def to_dict(self) -> dict:
        return {
            "confident": self.confident,
            "reject": self.reject,
            "plant_mass": self.plant_mass,
            "source": self.source,
            "temperature": self.temperature,
            "calibrated": self.calibrated,
        }


def resolve_thresholds(calibration: Optional[CalibrationArtifact]) -> DecisionThresholds:
    cfg = CONFIG.inference
    temperature = calibration.temperature if calibration else 1.0
    calibrated = calibration is not None

    if cfg.confident_threshold_override is not None or cfg.reject_threshold_override is not None:
        base_conf = calibration.thresholds.confident_threshold if calibration else cfg.disease_low_confidence_threshold
        base_rej = calibration.thresholds.reject_threshold if calibration else cfg.reject_confidence_default
        confident = cfg.confident_threshold_override if cfg.confident_threshold_override is not None else base_conf
        reject = cfg.reject_threshold_override if cfg.reject_threshold_override is not None else base_rej
        source = "env_override"
    elif calibration is not None:
        confident = calibration.thresholds.confident_threshold
        reject = calibration.thresholds.reject_threshold
        source = "validation"
    else:
        confident = cfg.disease_low_confidence_threshold
        reject = cfg.reject_confidence_default
        source = "unvalidated_default"

    reject = min(reject, confident)
    plant_mass = calibration.plant_mass_threshold if calibration and calibration.plant_mass_threshold is not None \
        else cfg.plant_id_confidence_threshold
    return DecisionThresholds(confident=float(confident), reject=float(reject), plant_mass=plant_mass,
                              source=source, temperature=float(temperature), calibrated=calibrated)


@dataclass(frozen=True)
class Decision:
    status: str
    top1_probability: float
    margin: float              # top-1 minus top-2 probability
    normalized_entropy: float  # 0 = all mass on one class, 1 = uniform
    plant_identified: bool

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "top1_probability": self.top1_probability,
            "margin": self.margin,
            "normalized_entropy": self.normalized_entropy,
            "plant_identified": self.plant_identified,
        }


def decide(probs: np.ndarray, plant_mass: float, thresholds: DecisionThresholds) -> Decision:
    probs = np.asarray(probs, dtype=np.float64)
    sorted_p = np.sort(probs)[::-1]
    top1 = float(sorted_p[0])
    top2 = float(sorted_p[1]) if len(sorted_p) > 1 else 0.0
    p = np.clip(probs, 1e-12, 1.0)
    entropy = float(-(p * np.log(p)).sum() / np.log(len(p))) if len(p) > 1 else 0.0

    if top1 >= thresholds.confident:
        status = CONFIDENT
    elif top1 >= thresholds.reject:
        status = UNCERTAIN
    else:
        status = INCONCLUSIVE
    plant_ok = thresholds.plant_mass is None or plant_mass >= thresholds.plant_mass
    return Decision(status=status, top1_probability=top1, margin=top1 - top2,
                    normalized_entropy=entropy, plant_identified=bool(plant_ok))
