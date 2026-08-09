"""
LabelEncoder — canonical-label <-> integer-index mapping, persisted as an artifact
so training, evaluation, and inference always agree on class index ordering
(requirement: "Save label encoders").

Deliberately not sklearn's LabelEncoder because we need stable, sorted,
JSON-serializable class ordering plus convenience helpers (plant/condition split)
used by the inference layer to report plant name and disease name separately.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd


@dataclass
class LabelEncoder:
    classes: List[str]  # sorted canonical labels, index position == model output index

    def __post_init__(self):
        self._class_to_idx: Dict[str, int] = {c: i for i, c in enumerate(self.classes)}

    @classmethod
    def fit(cls, labels: pd.Series) -> "LabelEncoder":
        classes = sorted(labels.unique().tolist())
        return cls(classes=classes)

    def encode(self, label: str) -> int:
        return self._class_to_idx[label]

    def decode(self, index: int) -> str:
        return self.classes[index]

    def decode_to_plant_condition(self, index: int) -> Dict[str, str]:
        canonical = self.decode(index)
        if "___" in canonical:
            plant, condition = canonical.split("___", 1)
        else:
            plant, condition = "unknown", canonical
        return {"plant": plant, "condition": condition, "canonical": canonical}

    @property
    def num_classes(self) -> int:
        return len(self.classes)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"classes": self.classes}, indent=2))

    @classmethod
    def load(cls, path: Path) -> "LabelEncoder":
        data = json.loads(path.read_text())
        return cls(classes=data["classes"])
