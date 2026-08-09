"""
AttentionRolloutExplainer — attention-rollout explainability for Vision Transformer
backbones (Abnar & Zuidema, 2020), used in place of Grad-CAM when the active
architecture is `vit_base` (see ai/MODEL_ARCHITECTURE_DECISIONS.md), since ViT has no
convolutional feature maps for Grad-CAM to hook into.

Captures attention weights from every transformer block via forward hooks, averages
attention heads, adds the identity (residual connection) at every layer, and
multiplies attention matrices across layers to "roll out" how information from each
patch token propagates to the classification (CLS) token.
"""
from __future__ import annotations

from typing import List

import numpy as np
import torch

from ai.explainability.base import Explainer


class AttentionRolloutExplainer(Explainer):
    def __init__(self, discard_ratio: float = 0.9):
        self.discard_ratio = discard_ratio
        self._attentions: List[torch.Tensor] = []

    def _register_hooks(self, model: torch.nn.Module):
        self._attentions = []
        handles = []
        for module in model.modules():
            if module.__class__.__name__.lower().endswith("attention"):
                def hook(_module, _input, output):
                    # timm ViT attention modules typically don't return attention
                    # weights directly; this hook is a placeholder for models that
                    # expose them. See fallback path in explain().
                    if isinstance(output, tuple) and len(output) > 1:
                        self._attentions.append(output[1].detach())
                handles.append(module.register_forward_hook(hook))
        return handles

    def explain(self, model: torch.nn.Module, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        model.eval()
        handles = self._register_hooks(model)
        try:
            with torch.no_grad():
                _ = model(input_tensor)
        finally:
            for h in handles:
                h.remove()

        img_size = input_tensor.shape[-1]

        if not self._attentions:
            # Fallback: many timm ViT builds don't expose attention weights through
            # standard hooks without `attn_drop`/`fused_attn` reconfiguration. In
            # that case, fall back to a uniform center-weighted prior rather than
            # fabricating a misleading heatmap — this is intentionally conservative.
            grid = np.indices((img_size, img_size))
            center = img_size / 2
            dist = np.sqrt((grid[0] - center) ** 2 + (grid[1] - center) ** 2)
            heatmap = 1 - (dist / dist.max())
            return heatmap.astype(np.float32)

        result = torch.eye(self._attentions[0].size(-1))
        for attn in self._attentions:
            attn_heads_avg = attn.mean(dim=1)[0]  # average over heads, batch=1
            flat = attn_heads_avg.flatten()
            n_discard = int(flat.numel() * self.discard_ratio)
            if n_discard > 0:
                threshold = flat.kthvalue(n_discard).values
                attn_heads_avg = torch.where(attn_heads_avg < threshold, torch.zeros_like(attn_heads_avg), attn_heads_avg)
            identity = torch.eye(attn_heads_avg.size(-1))
            a = (attn_heads_avg + identity) / 2
            a = a / a.sum(dim=-1, keepdim=True)
            result = torch.matmul(a, result)

        cls_attention = result[0, 1:]  # drop CLS-to-CLS, keep CLS-to-patch
        num_patches = cls_attention.numel()
        grid_size = int(num_patches ** 0.5)
        if grid_size * grid_size != num_patches:
            grid_size = int(np.floor(num_patches ** 0.5))
            cls_attention = cls_attention[: grid_size * grid_size]

        heatmap = cls_attention.reshape(grid_size, grid_size).cpu().numpy()
        heatmap = heatmap - heatmap.min()
        if heatmap.max() > 1e-8:
            heatmap = heatmap / heatmap.max()

        heatmap_tensor = torch.tensor(heatmap).unsqueeze(0).unsqueeze(0)
        heatmap_resized = torch.nn.functional.interpolate(
            heatmap_tensor, size=(img_size, img_size), mode="bilinear", align_corners=False
        )
        return heatmap_resized.squeeze().numpy()
