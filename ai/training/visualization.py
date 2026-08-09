"""
Visualization — saves training curve plots and confusion matrix images to disk
(requirements: "Save training graphs", "Save confusion matrix"). Uses matplotlib with
the non-interactive Agg backend so this runs headless on any training server.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def plot_training_curves(history: Dict[str, List[float]], out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].plot(history["train_loss"], label="Train Loss")
    axes[0].plot(history["val_loss"], label="Validation Loss")
    axes[0].set_title("Loss over Epochs")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(history["train_accuracy"], label="Train Accuracy")
    axes[1].plot(history["val_accuracy"], label="Validation Accuracy")
    axes[1].set_title("Accuracy over Epochs")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_confusion_matrix(cm: np.ndarray, class_names: List[str], out_path: Path,
                           normalize: bool = True) -> None:
    if normalize:
        with np.errstate(all="ignore"):
            row_sums = cm.sum(axis=1, keepdims=True)
            cm_display = np.divide(cm, row_sums, out=np.zeros_like(cm, dtype=float), where=row_sums != 0)
    else:
        cm_display = cm

    n = len(class_names)
    fig_size = max(6, min(0.35 * n, 30))
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    im = ax.imshow(cm_display, cmap="Blues")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names, rotation=90, fontsize=max(4, 10 - n // 20))
    ax.set_yticklabels(class_names, fontsize=max(4, 10 - n // 20))
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix" + (" (normalized)" if normalize else ""))
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
