"""
Metrics — accuracy, precision, recall, F1 (macro + per-class + weighted) and
confusion matrix computation (requirement: "Save Precision, Recall, F1-Score",
FR-DATA-8).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


@dataclass
class EvaluationMetrics:
    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    precision_weighted: float
    recall_weighted: float
    f1_weighted: float
    per_class: Dict[str, Dict[str, float]] = field(default_factory=dict)
    confusion_matrix: np.ndarray = field(default_factory=lambda: np.array([]))
    class_names: List[str] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "accuracy": self.accuracy,
            "precision_macro": self.precision_macro,
            "recall_macro": self.recall_macro,
            "f1_macro": self.f1_macro,
            "precision_weighted": self.precision_weighted,
            "recall_weighted": self.recall_weighted,
            "f1_weighted": self.f1_weighted,
            "per_class": self.per_class,
        }


def compute_metrics(y_true: List[int], y_pred: List[int], class_names: List[str]) -> EvaluationMetrics:
    accuracy = float(accuracy_score(y_true, y_pred))

    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    precision_weighted, recall_weighted, f1_weighted, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )

    precisions, recalls, f1s, supports = precision_recall_fscore_support(
        y_true, y_pred, average=None, labels=list(range(len(class_names))), zero_division=0
    )
    per_class = {
        class_names[i]: {
            "precision": float(precisions[i]),
            "recall": float(recalls[i]),
            "f1": float(f1s[i]),
            "support": int(supports[i]),
        }
        for i in range(len(class_names))
    }

    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    return EvaluationMetrics(
        accuracy=accuracy,
        precision_macro=float(precision_macro),
        recall_macro=float(recall_macro),
        f1_macro=float(f1_macro),
        precision_weighted=float(precision_weighted),
        recall_weighted=float(recall_weighted),
        f1_weighted=float(f1_weighted),
        per_class=per_class,
        confusion_matrix=cm,
        class_names=class_names,
    )
