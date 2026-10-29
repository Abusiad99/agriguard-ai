"""
Explainer factory: picks Grad-CAM or attention-rollout based on the active
architecture family, and renders a saveable heatmap-overlay image (used by the report
generator and the results page, FR-AI-7 / FR-RESULT-1).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from ai.explainability.attention_rollout import AttentionRolloutExplainer
from ai.explainability.base import Explainer
from ai.explainability.gradcam import GradCAM

_VIT_ARCHITECTURES = {"vit_base"}


def get_explainer(architecture: str) -> Explainer:
    if architecture in _VIT_ARCHITECTURES:
        return AttentionRolloutExplainer()
    return GradCAM()


def _heat_colormap(values: np.ndarray) -> np.ndarray:
    """Map [0,1] -> RGB with a perceptually ordered blue->cyan->yellow->red ramp."""
    stops = np.array([0.0, 0.35, 0.65, 1.0])
    colors = np.array([[49, 54, 149], [69, 189, 207], [254, 224, 76], [215, 25, 28]], dtype=np.float32)
    out = np.empty(values.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(values, stops, colors[:, c])
    return out


def render_heatmap_overlay(original_image: Image.Image, heatmap: np.ndarray, alpha: float = 0.55) -> Image.Image:
    """Overlay a normalized [0,1] model-attention map on the photo at the photo's own
    resolution. Opacity scales with attention, so low-attention areas keep the
    original photo visible. This visualizes where the classifier "looked"; it is not
    a lesion mask (see ai/explainability/gradcam.py)."""
    original = original_image.convert("RGB")
    heat = Image.fromarray(np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)).resize(original.size, Image.BILINEAR)
    h = np.asarray(heat, dtype=np.float32) / 255.0
    base = np.asarray(original, dtype=np.float32)
    weight = (alpha * np.clip((h - 0.15) / 0.85, 0.0, 1.0))[..., None]
    blended = (1.0 - weight) * base + weight * _heat_colormap(h)
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))
