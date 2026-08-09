"""
Explainer interface — model-agnostic contract for producing a heatmap over an input
image given a trained model and a target class (FR-AI-7). Both the Grad-CAM (CNN) and
attention-rollout (ViT) implementations satisfy this same interface, and it is the
designated substitution point for a future SAM2-based refinement (see
ai/MODEL_ARCHITECTURE_DECISIONS.md §2).
"""
from __future__ import annotations

import abc

import numpy as np
import torch


class Explainer(abc.ABC):
    @abc.abstractmethod
    def explain(self, model: torch.nn.Module, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        """Return a 2D numpy array (H x W, values in [0, 1]) heatmap for the given
        input tensor (shape [1, C, H, W], already preprocessed) and target class
        index."""
        raise NotImplementedError
