"""
GradCAM — standard Grad-CAM (Selvaraju et al. 2017) for CNN backbones
(EfficientNet, ConvNeXt, MobileNetV4). Hooks the last convolutional feature map,
backpropagates the target class score, and weights feature-map channels by their
average gradient to produce a class-discriminative attention map (FR-AI-7).

What a Grad-CAM map is — and is not:
  * It shows which image regions most increased the model's score for the
    predicted class ("model attention").
  * It is coarse (the last feature map of EfficientNet-B0 is 7x7 for a 224px input)
    and upsampled for display.
  * It is NOT a disease segmentation mask and must not be used to measure lesion
    area or severity, and highlighted regions do not prove the biological cause of
    a disease. (An earlier version of this project derived "affected area %" and a
    severity level from this map; that has been removed — see
    ai/segmentation/ for genuine mask-based measurement.)

Hooks are registered for the duration of a single `explain()` call and always
removed afterwards; previously they were re-registered on every call and never
removed, so every diagnosis added two more hooks to the shared model.
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
    method_name = "grad_cam"

    def __init__(self, target_layer: Optional[torch.nn.Module] = None):
        self._target_layer = target_layer

    def explain(self, model: torch.nn.Module, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        target_layer = self._target_layer or _find_last_conv_layer(model)
        if target_layer is None:
            raise ValueError(
                "GradCAM requires a Conv2d layer; none found in the given model. "
                "For transformer backbones, use AttentionRolloutExplainer instead."
            )

        captured: dict = {}

        def forward_hook(_module, _input, output):
            captured["activations"] = output.detach()

        def backward_hook(_module, _grad_input, grad_output):
            captured["gradients"] = grad_output[0].detach()

        handles = [
            target_layer.register_forward_hook(forward_hook),
            target_layer.register_full_backward_hook(backward_hook),
        ]
        try:
            model.eval()
            input_tensor = input_tensor.clone().requires_grad_(True)
            with torch.enable_grad():
                output = model(input_tensor)
                score = output[0, target_class]
                model.zero_grad(set_to_none=True)
                score.backward(retain_graph=False)
        finally:
            for h in handles:
                h.remove()
            model.zero_grad(set_to_none=True)

        activations = captured.get("activations")
        gradients = captured.get("gradients")
        if activations is None or gradients is None:
            raise RuntimeError("GradCAM hooks did not fire; check target layer selection.")

        weights = gradients.mean(dim=(2, 3), keepdim=True)  # [1, C, 1, 1]
        cam = (weights * activations).sum(dim=1, keepdim=True)  # [1, 1, h, w]
        cam = F.relu(cam)

        cam = F.interpolate(cam, size=input_tensor.shape[-2:], mode="bilinear", align_corners=False)
        cam = cam.squeeze().cpu().numpy()

        cam_min, cam_max = cam.min(), cam.max()
        if cam_max - cam_min > 1e-8:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)
        return cam
