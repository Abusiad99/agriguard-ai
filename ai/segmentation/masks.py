"""
Mask conventions and affected-area measurement.

Label convention for segmentation masks (single-channel PNG, uint8):
    0   background (anything that is not visible leaf tissue)
    1   visible leaf tissue without visible lesion
    2   visible diseased tissue (lesion) ON a leaf
  255   ignore / unannotated (excluded from training loss and from metrics)

Affected area is computed exactly as

    affected_area_pct = lesion_pixels_on_leaf / visible_leaf_pixels * 100

where visible_leaf_pixels = pixels labelled 1 or 2. Background never enters the
denominator. Pixels labelled 255 are excluded from both numerator and denominator.

This is a measurement of *visible* affected leaf area in one photo. It is not, by
itself, an agronomically validated severity score: the result depends on viewing
angle, how many leaves are in frame, and occlusion. Mapping a percentage to
mild / moderate / severe requires a crop-specific, documented scale (see
severity_scales.py); none is assumed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

BACKGROUND = 0
LEAF = 1
LESION = 2
IGNORE = 255
VALID_LABELS = {BACKGROUND, LEAF, LESION, IGNORE}


@dataclass
class AreaMeasurement:
    status: str  # "measured" | "unavailable"
    affected_area_pct: Optional[float] = None
    healthy_area_pct: Optional[float] = None
    leaf_pixels: int = 0
    lesion_pixels: int = 0
    image_pixels: int = 0
    leaf_fraction_of_image: float = 0.0
    leaf_regions: int = 0
    lesion_regions: int = 0
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def validate_class_map(class_map: np.ndarray) -> None:
    if class_map.ndim != 2:
        raise ValueError(f"Mask must be 2-D (H x W); got shape {class_map.shape}.")
    values = set(np.unique(class_map).tolist())
    unexpected = values - VALID_LABELS
    if unexpected:
        raise ValueError(f"Mask contains unexpected label values {sorted(unexpected)}; "
                         f"allowed values are {sorted(VALID_LABELS)}.")


def _count_regions(binary: np.ndarray, min_pixels: int) -> int:
    if not binary.any():
        return 0
    from scipy import ndimage  # scipy ships with scikit-learn, already an ai/ dependency

    labelled, n = ndimage.label(binary)
    if n == 0:
        return 0
    sizes = np.bincount(labelled.ravel())[1:]
    return int((sizes >= min_pixels).sum())


def measure_from_class_map(class_map: np.ndarray, *, min_leaf_fraction: float = 0.02,
                           min_region_pixels: int = 25) -> AreaMeasurement:
    """Measure affected leaf area from a single class map (0/1/2/255)."""
    validate_class_map(class_map)
    valid = class_map != IGNORE
    leaf = (class_map == LEAF) | (class_map == LESION)
    lesion = class_map == LESION
    return _measure(leaf, lesion, valid, min_leaf_fraction, min_region_pixels)


def measure_from_masks(leaf_mask: np.ndarray, lesion_mask: np.ndarray, *,
                       min_leaf_fraction: float = 0.02, min_region_pixels: int = 25,
                       max_lesion_outside_leaf: float = 0.05) -> AreaMeasurement:
    """Measure from separate binary leaf and lesion masks (e.g. two model heads or
    two annotation layers). Lesion pixels outside the leaf mask are NOT counted; if
    more than `max_lesion_outside_leaf` of the lesion lies outside the leaf, the
    masks are considered inconsistent and no measurement is returned."""
    leaf = np.asarray(leaf_mask).astype(bool)
    lesion = np.asarray(lesion_mask).astype(bool)
    if leaf.shape != lesion.shape:
        raise ValueError(f"Leaf mask {leaf.shape} and lesion mask {lesion.shape} differ in shape.")
    if lesion.any():
        outside = float((lesion & ~leaf).sum()) / float(lesion.sum())
        if outside > max_lesion_outside_leaf:
            return AreaMeasurement(
                status="unavailable", image_pixels=int(leaf.size),
                reason=f"inconsistent_masks: {outside:.0%} of the lesion mask lies outside the leaf mask",
            )
    valid = np.ones_like(leaf, dtype=bool)
    return _measure(leaf, lesion & leaf, valid, min_leaf_fraction, min_region_pixels)


def _measure(leaf: np.ndarray, lesion: np.ndarray, valid: np.ndarray,
             min_leaf_fraction: float, min_region_pixels: int) -> AreaMeasurement:
    leaf = leaf & valid
    lesion = lesion & leaf
    image_pixels = int(valid.sum())
    leaf_px = int(leaf.sum())
    lesion_px = int(lesion.sum())
    leaf_fraction = leaf_px / image_pixels if image_pixels else 0.0
    base = dict(leaf_pixels=leaf_px, lesion_pixels=lesion_px, image_pixels=image_pixels,
                leaf_fraction_of_image=round(leaf_fraction, 4))
    if image_pixels == 0:
        return AreaMeasurement(status="unavailable", reason="no_valid_pixels", **base)
    if leaf_fraction < min_leaf_fraction or leaf_px < min_region_pixels:
        return AreaMeasurement(status="unavailable", reason="leaf_not_identified", **base)

    affected = 100.0 * lesion_px / leaf_px
    return AreaMeasurement(
        status="measured",
        affected_area_pct=round(affected, 2),
        healthy_area_pct=round(100.0 - affected, 2),
        leaf_regions=_count_regions(leaf, min_region_pixels),
        lesion_regions=_count_regions(lesion, max(4, min_region_pixels // 5)),
        **base,
    )


def colorize_class_map(class_map: np.ndarray) -> np.ndarray:
    """RGBA visualization: leaf = translucent green, lesion = opaque magenta,
    background/ignore = transparent. Separate from the original photo, which is
    never modified."""
    h, w = class_map.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[class_map == LEAF] = (46, 160, 67, 110)
    rgba[class_map == LESION] = (214, 51, 132, 200)
    return rgba
