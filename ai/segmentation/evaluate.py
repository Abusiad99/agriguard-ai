"""
Evaluate a trained segmentation run on a held-out split.

    python -m ai.segmentation.evaluate [--run RUN_DIR] [--split test] [--dataset datasets/segmentation] [--examples 8]

Writes <run>/evaluation/<split>/:
  metrics.json          overall + per-class IoU, Dice, precision, recall, F1
  per_class.csv
  confusion_matrix.png  pixel-level, row-normalized
  examples/*.png        image | ground truth | prediction, for random samples
  failures/*.png        the samples with the lowest foreground Dice
  dataset_stats.json    split sizes and class pixel counts from the manifest
and records the summary in the run's model_card.json. Metrics are computed at the
model input resolution with masks resized by NEAREST (as in validation).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

from ai import registry
from ai.models.architectures import resolve_device
from ai.segmentation.dataset import SegmentationDataset
from ai.segmentation.inference import load_run
from ai.segmentation.metrics import confusion_matrix, metrics_from_confusion
from ai.segmentation.validate import default_dataset_root
from ai.segmentation.visualize import blend


def _sheet(image: Image.Image, gt: np.ndarray, pred: np.ndarray, mapping) -> Image.Image:
    size = (gt.shape[1], gt.shape[0])
    panels = [image.convert("RGB").resize(size), blend(image, gt, mapping), blend(image, pred, mapping)]
    sheet = Image.new("RGB", (size[0] * 3 + 8, size[1]), "white")
    for i, panel in enumerate(panels):
        sheet.paste(panel, (i * (size[0] + 4), 0))
    return sheet


def _plot_confusion(cm: np.ndarray, names, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(1.2 * len(names) + 3, 1.2 * len(names) + 2))
    ax.imshow(norm, cmap="Greens", vmin=0, vmax=1)
    ax.set_xticks(range(len(names)), names, rotation=45, ha="right")
    ax.set_yticks(range(len(names)), names)
    ax.set_xlabel("predicted")
    ax.set_ylabel("ground truth")
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{norm[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def evaluate(dataset_root: Path, run_dir: Optional[Path] = None, split: str = "test", examples: int = 8,
             device: str = "auto", allow_dataset_mismatch: bool = False) -> dict:
    run_dir = run_dir or registry.latest_run_dir("segmentation")
    if run_dir is None:
        raise SystemExit("No trained segmentation run to evaluate. Train one first (scripts/segmentation.ps1 -Action train).")
    dev = resolve_device(device)
    model, card, mapping, config = load_run(run_dir, dev)
    manifest_path = Path(dataset_root) / "manifests" / "dataset_manifest.json"
    current = json.loads(manifest_path.read_text(encoding="utf-8")).get("dataset_version") if manifest_path.is_file() else None
    mismatch = card.get("dataset_version") is not None and current != card.get("dataset_version")
    if mismatch and not allow_dataset_mismatch:
        # Re-preprocessing (new data, other seed) reshuffles the splits: the new test split
        # may contain images this model was trained on.
        raise SystemExit(f"The processed dataset ({current}) is not the one this model was trained on "
                         f"({card.get('dataset_version')}). Retrain, or pass --allow-dataset-mismatch "
                         "to evaluate anyway (results are flagged).")
    dataset = SegmentationDataset(dataset_root, split, config, train=False)
    if not len(dataset):
        raise SystemExit(f"The '{split}' split is empty.")
    out = run_dir / "evaluation" / split
    (out / "examples").mkdir(parents=True, exist_ok=True)
    (out / "failures").mkdir(parents=True, exist_ok=True)

    cm = np.zeros((mapping.num_classes, mapping.num_classes), dtype=np.int64)
    per_sample = []
    with torch.no_grad():
        for i in range(len(dataset)):
            x, y = dataset[i]
            pred = model(x.unsqueeze(0).to(dev)).argmax(1)[0].cpu()
            sample_cm = confusion_matrix(pred, y, mapping.num_classes)
            cm += sample_cm
            fg = metrics_from_confusion(sample_cm, mapping.names, mapping.background_id)["foreground_mean_dice"]
            per_sample.append((i, fg, pred.numpy().astype(np.uint8), y.numpy().astype(np.uint8)))

    metrics = metrics_from_confusion(cm, mapping.names, mapping.background_id)
    metrics.update({"split": split, "samples": len(dataset), "run": run_dir.name,
                    "dataset_version": current, "trained_dataset_version": card.get("dataset_version"),
                    "dataset_mismatch": mismatch,
                    # Scored at the model's input size (image_size x image_size), like validation
                    # during training; served masks are resized back to the photo.
                    "resolution": f"{config.image_size}x{config.image_size}",
                    "evaluated_at": datetime.now(timezone.utc).isoformat()})
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (out / "per_class.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["class", "iou", "dice", "precision", "recall", "f1", "support_pixels"])
        for name, m in metrics["per_class"].items():
            writer.writerow([name, m["iou"], m["dice"], m["precision"], m["recall"], m["f1"], m["support_pixels"]])
    np.save(out / "confusion_matrix.npy", cm)
    _plot_confusion(cm, mapping.names, out / "confusion_matrix.png")

    rng = random.Random(0)
    for i, _, pred, gt in rng.sample(per_sample, min(examples, len(per_sample))):
        image, _ = dataset.load_pair(i)
        _sheet(image, gt, pred, mapping).save(out / "examples" / f"{dataset.keys[i]}.png")
    scored = sorted((s for s in per_sample if s[1] is not None), key=lambda s: s[1])
    for i, score, pred, gt in scored[:examples]:
        image, _ = dataset.load_pair(i)
        _sheet(image, gt, pred, mapping).save(out / "failures" / f"{score:.3f}_{dataset.keys[i]}.png")

    manifest = json.loads((Path(dataset_root) / "manifests" / "dataset_manifest.json").read_text(encoding="utf-8"))
    (out / "dataset_stats.json").write_text(json.dumps({k: manifest.get(k) for k in
                                                        ("dataset_version", "splits", "class_pixels", "num_groups")}, indent=2),
                                            encoding="utf-8")
    card.setdefault("metrics", {})[f"evaluation_{split}"] = {
        k: metrics[k] for k in ("mean_iou", "foreground_mean_iou", "mean_dice", "foreground_mean_dice",
                                "pixel_accuracy", "samples", "evaluated_at")}
    (run_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a segmentation run")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--run", type=Path, default=None, help="run directory (default: the served model)")
    parser.add_argument("--split", default="test", choices=["train", "validation", "test"])
    parser.add_argument("--examples", type=int, default=8)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--allow-dataset-mismatch", action="store_true",
                        help="evaluate even if the dataset changed since training (results are flagged)")
    args = parser.parse_args(argv)
    metrics = evaluate(args.dataset, args.run, args.split, args.examples, args.device, args.allow_dataset_mismatch)
    print(json.dumps({k: metrics[k] for k in ("split", "samples", "mean_iou", "foreground_mean_iou", "mean_dice")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
