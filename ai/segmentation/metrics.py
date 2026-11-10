"""Segmentation losses and metrics. Metrics come from an accumulated pixel confusion
matrix, so they are exact over the whole split (not averaged per batch)."""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from ai.segmentation.classes import IGNORE_INDEX


def confusion_matrix(pred: torch.Tensor, target: torch.Tensor, num_classes: int) -> np.ndarray:
    """[C, C] counts, rows = ground truth, cols = prediction; IGNORE_INDEX pixels skipped."""
    valid = target != IGNORE_INDEX
    idx = target[valid].to(torch.int64) * num_classes + pred[valid].to(torch.int64)
    return torch.bincount(idx, minlength=num_classes * num_classes).reshape(num_classes, num_classes).cpu().numpy()


def metrics_from_confusion(cm: np.ndarray, class_names: Sequence[str], background_id: int = 0) -> dict:
    cm = cm.astype(np.float64)
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp
    support = cm.sum(axis=1)

    def safe(num, den):
        return np.divide(num, den, out=np.full_like(num, np.nan), where=den > 0)

    iou = safe(tp, tp + fp + fn)
    dice = safe(2 * tp, 2 * tp + fp + fn)
    precision = safe(tp, tp + fp)
    recall = safe(tp, tp + fn)
    present = support > 0
    fg = present & (np.arange(len(class_names)) != background_id)

    def nanmean(values, where):
        sel = values[where]
        sel = sel[~np.isnan(sel)]
        return float(sel.mean()) if sel.size else None

    per_class = {
        name: {"iou": _f(iou[i]), "dice": _f(dice[i]), "precision": _f(precision[i]),
               "recall": _f(recall[i]), "f1": _f(dice[i]), "support_pixels": int(support[i])}
        for i, name in enumerate(class_names)
    }
    return {
        "pixel_accuracy": float(tp.sum() / cm.sum()) if cm.sum() else None,
        "mean_iou": nanmean(iou, present),
        "mean_dice": nanmean(dice, present),
        "foreground_mean_iou": nanmean(iou, fg),
        "foreground_mean_dice": nanmean(dice, fg),
        "mean_precision": nanmean(precision, present),
        "mean_recall": nanmean(recall, present),
        "per_class": per_class,
    }


def _f(value) -> Optional[float]:
    return None if np.isnan(value) else round(float(value), 6)


class DiceLoss(nn.Module):
    """Soft multi-class Dice loss (1 - mean Dice over classes present in the batch or
    predicted). Robust to class imbalance, so it pairs well with cross-entropy."""

    def __init__(self, num_classes: int, ignore_index: int = IGNORE_INDEX, smooth: float = 1.0):
        super().__init__()
        self.num_classes, self.ignore_index, self.smooth = num_classes, ignore_index, smooth

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        probs = logits.float().softmax(dim=1)
        valid = (target != self.ignore_index).unsqueeze(1)
        one_hot = F.one_hot(target.clamp(0, self.num_classes - 1), self.num_classes).permute(0, 3, 1, 2).float()
        probs, one_hot = probs * valid, one_hot * valid
        dims = (0, 2, 3)
        inter = (probs * one_hot).sum(dims)
        denom = probs.sum(dims) + one_hot.sum(dims)
        dice = (2 * inter + self.smooth) / (denom + self.smooth)
        return 1 - dice.mean()


class CombinedLoss(nn.Module):
    def __init__(self, ce: Optional[nn.Module], dice: Optional[nn.Module]):
        super().__init__()
        self.ce, self.dice = ce, dice

    def forward(self, logits, target):
        loss = 0.0
        if self.ce is not None:
            loss = loss + self.ce(logits.float(), target)
        if self.dice is not None:
            loss = loss + self.dice(logits, target)
        return loss


def build_loss(name: str, num_classes: int, class_weights: Optional[List[float]] = None) -> nn.Module:
    weight = torch.tensor(class_weights, dtype=torch.float32) if class_weights else None
    ce = nn.CrossEntropyLoss(weight=weight, ignore_index=IGNORE_INDEX)
    dice = DiceLoss(num_classes)
    if name == "ce":
        return CombinedLoss(ce, None)
    if name == "dice":
        return CombinedLoss(None, dice)
    if name == "ce_dice":
        return CombinedLoss(ce, dice)
    raise ValueError(f"unknown loss '{name}' (ce | dice | ce_dice)")


def median_frequency_weights(pixel_counts: Sequence[int], max_weight: float = 10.0) -> List[float]:
    """Median-frequency balancing (Eigen & Fergus): weight_c = median(freq) / freq_c,
    clipped. Classes absent from the training split get weight 0 (nothing to learn)."""
    counts = np.asarray(pixel_counts, dtype=np.float64)
    total = counts.sum()
    if total <= 0:
        return [1.0] * len(counts)
    freq = counts / total
    present = freq > 0
    median = np.median(freq[present]) if present.any() else 1.0
    weights = np.where(present, median / np.where(present, freq, 1.0), 0.0)
    return [round(float(min(w, max_weight)), 4) for w in weights]
