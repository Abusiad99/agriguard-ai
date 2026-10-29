"""
Segmentation metrics computed against genuine ground-truth masks: per-class IoU and
Dice, their means, pixel accuracy, and the error of the derived affected-area
percentage (the quantity users actually see). Pixels labelled IGNORE (255) in the
ground truth are excluded everywhere.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from ai.segmentation.masks import IGNORE, measure_from_class_map

CLASS_NAMES = ("background", "leaf", "lesion")


class SegmentationMeter:
    def __init__(self, num_classes: int = 3):
        self.num_classes = num_classes
        self.confusion = np.zeros((num_classes, num_classes), dtype=np.int64)
        self.area_errors: List[float] = []
        self.area_unavailable = 0
        self.per_image: List[Dict[str, float]] = []

    def update(self, pred: np.ndarray, target: np.ndarray, image_id: str = "") -> Dict[str, float]:
        pred = np.asarray(pred, dtype=np.int64)
        target = np.asarray(target, dtype=np.int64)
        valid = target != IGNORE
        p, t = pred[valid], target[valid]
        cm = np.bincount(t * self.num_classes + p, minlength=self.num_classes ** 2).reshape(
            self.num_classes, self.num_classes)
        self.confusion += cm
        img_iou = _iou_from_confusion(cm)

        gt_area = measure_from_class_map(np.where(valid, target, IGNORE).astype(np.uint8))
        pr_area = measure_from_class_map(np.where(valid, pred, IGNORE).astype(np.uint8))
        area_err = None
        if gt_area.status == "measured" and pr_area.status == "measured":
            area_err = abs(gt_area.affected_area_pct - pr_area.affected_area_pct)
            self.area_errors.append(area_err)
        elif gt_area.status == "measured":
            self.area_unavailable += 1
        record = {"image_id": image_id, "lesion_iou": img_iou[2], "leaf_iou": img_iou[1],
                  "gt_affected_pct": gt_area.affected_area_pct, "pred_affected_pct": pr_area.affected_area_pct,
                  "affected_abs_error": area_err}
        self.per_image.append(record)
        return record

    def summary(self) -> Dict[str, object]:
        iou = _iou_from_confusion(self.confusion)
        dice = _dice_from_confusion(self.confusion)
        total = self.confusion.sum()
        return {
            "per_class": {CLASS_NAMES[i] if i < len(CLASS_NAMES) else str(i):
                          {"iou": iou[i], "dice": dice[i], "gt_pixels": int(self.confusion[i].sum())}
                          for i in range(self.num_classes)},
            "mean_iou": _nanmean(iou),
            "mean_dice": _nanmean(dice),
            "pixel_accuracy": float(np.trace(self.confusion) / total) if total else None,
            "affected_area_mae_pct_points": float(np.mean(self.area_errors)) if self.area_errors else None,
            "affected_area_measured_images": len(self.area_errors),
            "affected_area_unavailable_when_gt_measurable": self.area_unavailable,
            "n_images": len(self.per_image),
        }

    def worst_cases(self, k: int = 10) -> List[Dict[str, float]]:
        scored = [r for r in self.per_image if r["lesion_iou"] is not None]
        return sorted(scored, key=lambda r: r["lesion_iou"])[:k]


def _iou_from_confusion(cm: np.ndarray) -> List[float]:
    out = []
    for i in range(cm.shape[0]):
        tp = cm[i, i]
        denom = cm[i, :].sum() + cm[:, i].sum() - tp
        out.append(float(tp / denom) if denom else None)
    return out


def _dice_from_confusion(cm: np.ndarray) -> List[float]:
    out = []
    for i in range(cm.shape[0]):
        tp = cm[i, i]
        denom = cm[i, :].sum() + cm[:, i].sum()
        out.append(float(2 * tp / denom) if denom else None)
    return out


def _nanmean(values) -> float:
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None
