"""Outbreak pipeline configuration (configs/outbreak/default.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional

from ai.config import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "outbreak" / "default.json"


@dataclass
class OutbreakConfig:
    grid_resolution_deg: float = 0.25
    horizons_days: List[int] = field(default_factory=lambda: [3, 7, 14])
    step_days: int = 7
    # --- training minimums: below these the trainer refuses (readiness "insufficient_data")
    min_rows: int = 200
    min_positives: int = 30
    min_negatives: int = 30
    min_span_days: int = 365
    # chronological split: the latest `test_fraction` of dates is the test set, the
    # `validation_fraction` before it is validation (used for calibration + thresholds)
    validation_fraction: float = 0.15
    test_fraction: float = 0.2
    # calibration needs enough validation examples of both classes
    min_calibration_per_class: int = 30
    # --- model
    max_iter: int = 300
    learning_rate: float = 0.05
    max_leaf_nodes: int = 31
    l2_regularization: float = 1.0
    seed: int = 42
    # --- risk levels: cut points on the (calibrated or raw) score for low / moderate / high / critical
    risk_cutpoints: List[float] = field(default_factory=lambda: [0.25, 0.5, 0.75])
    # --- prediction-time requirement
    min_completeness: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: Optional[Path] = None, **overrides) -> OutbreakConfig:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data.pop("_comment", None)
    unknown = set(data) - {f.name for f in fields(OutbreakConfig)}
    if unknown:
        raise ValueError(f"unknown outbreak config keys: {sorted(unknown)}")
    data.update({k: v for k, v in overrides.items() if v is not None})
    return OutbreakConfig(**data)
