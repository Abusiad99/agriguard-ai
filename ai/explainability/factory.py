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


def render_heatmap_overlay(original_image: Image.Image, heatmap: np.ndarray, alpha: float = 0.45) -> Image.Image:
    """Overlay a normalized [0,1] heatmap as a red-toned heat layer on the original
    image, resized to match. Returns a new PIL Image (RGB)."""
    original = original_image.convert("RGB").resize((heatmap.shape[1], heatmap.shape[0]))
    base = np.array(original).astype(np.float32)

    heat_rgb = np.zeros_like(base)
    heat_rgb[..., 0] = heatmap * 255.0  # red channel encodes intensity
    heat_rgb[..., 1] = (1 - heatmap) * 60.0
    heat_rgb[..., 2] = (1 - heatmap) * 60.0

    blended = (1 - alpha) * base + alpha * heat_rgb
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(blended)
