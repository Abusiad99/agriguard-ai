"""
Derives disease localization (FR-AI-4) and severity estimation (FR-AI-5) from an
explainability heatmap (see ai/MODEL_ARCHITECTURE_DECISIONS.md §2 for why this is the
default localization strategy rather than a separately-trained detector).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ai.config import CONFIG


@dataclass
class SeverityResult:
    affected_area_pct: float
    healthy_area_pct: float
    severity_level: str  # "mild" | "moderate" | "severe"


@dataclass
class BoundingRegion:
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    mask_coverage_pct: float


def threshold_heatmap(heatmap: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Binary mask of "affected" pixels: heatmap intensity >= threshold."""
    return (heatmap >= threshold).astype(np.uint8)


def estimate_severity(heatmap: np.ndarray, threshold: float = 0.5) -> SeverityResult:
    mask = threshold_heatmap(heatmap, threshold)
    total_pixels = mask.size
    affected_pixels = int(mask.sum())
    affected_pct = round(100.0 * affected_pixels / total_pixels, 2) if total_pixels else 0.0
    healthy_pct = round(100.0 - affected_pct, 2)

    thresholds = CONFIG.inference
    if affected_pct <= thresholds.severity_mild_max_pct:
        level = "mild"
    elif affected_pct <= thresholds.severity_moderate_max_pct:
        level = "moderate"
    else:
        level = "severe"

    return SeverityResult(affected_area_pct=affected_pct, healthy_area_pct=healthy_pct, severity_level=level)


def localize_region(heatmap: np.ndarray, threshold: float = 0.5) -> BoundingRegion:
    """Derive a bounding box tightly enclosing the affected region for display
    (highlighted disease region, FR-RESULT-1)."""
    mask = threshold_heatmap(heatmap, threshold)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        h, w = heatmap.shape
        return BoundingRegion(x_min=0, y_min=0, x_max=w, y_max=h, mask_coverage_pct=0.0)

    coverage_pct = round(100.0 * mask.sum() / mask.size, 2)
    return BoundingRegion(
        x_min=int(xs.min()), y_min=int(ys.min()),
        x_max=int(xs.max()), y_max=int(ys.max()),
        mask_coverage_pct=coverage_pct,
    )
