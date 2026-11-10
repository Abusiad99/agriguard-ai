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
        """Capture each block's softmaxed attention matrix [B, heads, N, N].

        timm's ViT Attention computes it as `attn = softmax(q @ k^T)` and passes it
        through `self.attn_drop` — but only on the unfused path. With `fused_attn`
        (the default) it calls scaled_dot_product_attention and the weights never
        exist as a tensor, so fused attention is switched off for the duration of
        the call and restored afterwards. Returns (hook handles, modules to restore).
        """
        self._attentions = []
        handles, unfused = [], []
        for module in model.modules():
            attn_drop = getattr(module, "attn_drop", None)
            if attn_drop is None or not module.__class__.__name__.lower().endswith("attention"):
                continue
            if getattr(module, "fused_attn", False):
                module.fused_attn = False
                unfused.append(module)

            def hook(_module, inputs, _output):
                self._attentions.append(inputs[0].detach())

            handles.append(attn_drop.register_forward_hook(hook))
        return handles, unfused

    def explain(self, model: torch.nn.Module, input_tensor: torch.Tensor, target_class: int) -> np.ndarray:
        model.eval()
        handles, unfused = self._register_hooks(model)
        try:
            with torch.no_grad():
                _ = model(input_tensor)
        finally:
            for h in handles:
                h.remove()
            for module in unfused:
                module.fused_attn = True

        img_size = input_tensor.shape[-1]

        if not self._attentions:
            # No attention weights could be captured from this model. Raise rather
            # than return a stand-in pattern: the caller treats an explainability
            # failure as "no heatmap, no severity", which is honest, whereas a fixed
            # center-weighted prior used to give every image the same ~39% affected
            # area and "moderate" severity.
            raise RuntimeError("Attention rollout: the model exposed no attention weights.")

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
