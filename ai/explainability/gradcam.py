"""
GradCAM — standard Grad-CAM (Selvaraju et al. 2017) for CNN backbones
(EfficientNet, ConvNeXt, MobileNetV4). Hooks the last convolutional feature map,
backpropagates the target class score, and weights feature-map channels by their
average gradient to produce a localization heatmap (FR-AI-7, and the basis for
FR-AI-4 region localization and FR-AI-5 severity estimation — see severity.py).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from ai.explainability.base import Explainer


def _find_last_conv_layer(model: torch.nn.Module) -> Optional[torch.nn.Module]:
    last_conv = None
    for module in model.modules():
        if isinstance(module, torch.nn.Conv2d):
            last_conv = module
    return last_conv


class GradCAM(Explainer):
    def __init__(self, target_layer: Optional[torch.nn.Module] = None):
        self._target_layer = target_layer
        self._activations: Optional[torch.Tensor] = None
        self._gradients: Optional[torch.Tensor] = None

    def _register_hooks(self, model: torch.nn.Module) -> torch.nn.Module:
        target_layer = self._target_layer or _find_last_conv_layer(model)
        if target_layer is None:
            raise ValueError(
                "GradCAM requires a Conv2d layer; none found in the given model. "
                "For transformer backbones, use AttentionRolloutExplainer instead."
            )

        def forward_hook(_module, _input, output):
            self._activations = output.detach()

        def backward_hook(_module, _grad_input, grad_output):
            self._gradients = grad_output[0].detach()

        target_layer.register_forward_hook(forward_hook)
        target_layer.register_full_backward_hook(backward_hook)
        return target_layer

    def explain(self, model: torch.nn.Module, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        model.eval()
        self._register_hooks(model)

        input_tensor = input_tensor.clone().requires_grad_(True)
        output = model(input_tensor)
        score = output[0, target_class]

        model.zero_grad()
        score.backward(retain_graph=False)

        if self._activations is None or self._gradients is None:
            raise RuntimeError("GradCAM hooks did not fire; check target layer selection.")

        weights = self._gradients.mean(dim=(2, 3), keepdim=True)  # [1, C, 1, 1]
        cam = (weights * self._activations).sum(dim=1, keepdim=True)  # [1, 1, h, w]
        cam = F.relu(cam)

        cam = F.interpolate(cam, size=input_tensor.shape[-2:], mode="bilinear", align_corners=False)
        cam = cam.squeeze().cpu().numpy()

        cam_min, cam_max = cam.min(), cam.max()
        if cam_max - cam_min > 1e-8:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)
        return cam
