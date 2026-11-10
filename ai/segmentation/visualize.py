"""Visualization artifacts for a predicted (or ground-truth) training-id mask.
The original image is never modified; every artifact is a new file."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
from PIL import Image
from scipy import ndimage

from ai.segmentation import ARTIFACT_FILES as ARTIFACTS
from ai.segmentation.classes import ClassMapping


def binary_mask_image(mask: np.ndarray, mapping: ClassMapping) -> Image.Image:
    """White = any disease class, black = everything else."""
    return Image.fromarray((np.isin(mask, mapping.disease_ids) * 255).astype(np.uint8), mode="L")


def color_mask_rgba(mask: np.ndarray, mapping: ClassMapping, include_leaf: bool = False) -> Image.Image:
    """Transparent everywhere except the disease classes (each in its own color), so
    the client can lay it over the original photo at any opacity."""
    rgba = np.zeros(mask.shape + (4,), dtype=np.uint8)
    kinds = ("disease", "leaf") if include_leaf else ("disease",)
    for c in mapping.classes:
        if c.kind in kinds:
            sel = mask == c.id
            rgba[sel, :3] = c.color
            rgba[sel, 3] = 255 if c.kind == "disease" else 90
    return Image.fromarray(rgba, mode="RGBA")


def contour_rgba(mask: np.ndarray, mapping: ClassMapping, thickness: int = 2) -> Image.Image:
    rgba = np.zeros(mask.shape + (4,), dtype=np.uint8)
    for cid in mapping.disease_ids:
        region = mask == cid
        if not region.any():
            continue
        edge = region & ~ndimage.binary_erosion(region)
        if thickness > 1:
            edge = ndimage.binary_dilation(edge, iterations=thickness - 1)
        rgba[edge, :3] = mapping.classes[cid].color
        rgba[edge, 3] = 255
    return Image.fromarray(rgba, mode="RGBA")


def blend(image: Image.Image, mask: np.ndarray, mapping: ClassMapping, alpha: float = 0.5) -> Image.Image:
    """RGB image with the color mask blended in (used for evaluation example sheets)."""
    base = image.convert("RGB").resize((mask.shape[1], mask.shape[0]))
    overlay = color_mask_rgba(mask, mapping, include_leaf=True)
    weighted = Image.fromarray((np.asarray(overlay)[..., 3] * alpha).astype(np.uint8), mode="L")
    base.paste(overlay.convert("RGB"), (0, 0), weighted)
    return base


def save_artifacts(mask: np.ndarray, mapping: ClassMapping, out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    binary_mask_image(mask, mapping).save(out_dir / ARTIFACTS["mask"])
    color_mask_rgba(mask, mapping).save(out_dir / ARTIFACTS["overlay"])
    contour_rgba(mask, mapping).save(out_dir / ARTIFACTS["contours"])
    return dict(ARTIFACTS)
