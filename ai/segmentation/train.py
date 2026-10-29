"""
Train the leaf/lesion U-Net on GENUINE pixel annotations.

    python -m ai.segmentation.train --seg-root datasets_segmentation --epochs 40

Refuses to run when fewer than `--min-images` validated image/mask pairs exist —
image-level class labels are never converted into "masks". Writes a timestamped run
to artifacts/segmentation/runs/<ts>/ (weights, config, split manifest, history,
validation metrics) and marks it as latest. Evaluate the held-out TEST split with
`python -m ai.segmentation.evaluate`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ai.config import CONFIG
from ai.logging_setup import configure_logging
from ai.models.architectures import resolve_device
from ai.segmentation.data import SegmentationDataset, discover_samples, split_samples, write_manifest
from ai.segmentation.masks import IGNORE
from ai.segmentation.metrics import SegmentationMeter
from ai.segmentation.model import NUM_SEG_CLASSES, UNet

logger = logging.getLogger("agriguard.segmentation.train")

SEG_RUNS_DIR = CONFIG.paths.artifacts_dir / "segmentation" / "runs"
DEFAULT_SEG_ROOT = CONFIG.paths.project_root / "datasets_segmentation"


def _class_weights(loader: DataLoader) -> torch.Tensor:
    counts = np.zeros(NUM_SEG_CLASSES, dtype=np.float64)
    for _, target in loader:
        t = target.numpy()
        for c in range(NUM_SEG_CLASSES):
            counts[c] += (t == c).sum()
    counts = np.where(counts == 0, 1, counts)
    w = counts.sum() / (NUM_SEG_CLASSES * counts)
    return torch.tensor(np.clip(w, 0.1, 20.0), dtype=torch.float32)


def run_validation(model: nn.Module, loader: DataLoader, device: torch.device) -> dict:
    meter = SegmentationMeter(NUM_SEG_CLASSES)
    model.eval()
    with torch.no_grad():
        for images, targets in loader:
            preds = model(images.to(device)).argmax(dim=1).cpu().numpy()
            for p, t in zip(preds, targets.numpy()):
                meter.update(p, t)
    return meter.summary()


def main() -> int:
    configure_logging("segmentation_train.log")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seg-root", default=str(DEFAULT_SEG_ROOT))
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--image-size", type=int, default=256)
    ap.add_argument("--base-channels", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--min-images", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    report = discover_samples(Path(args.seg_root))
    for path, reason in report.invalid[:20]:
        logger.warning("Skipping invalid mask %s: %s", path, reason)
    n = len(report.samples)
    logger.info("Found %d validated image/mask pairs (%d images without mask, %d invalid) under %s",
                n, report.images_without_mask, len(report.invalid), args.seg_root)
    if n < args.min_images:
        logger.error(
            "Not enough genuine segmentation annotations to train (%d < %d). Annotate leaf and "
            "lesion masks as described in docs/SEGMENTATION.md; no model was trained.", n, args.min_images)
        return 2

    splits = split_samples(report.samples, seed=args.seed)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = SEG_RUNS_DIR / f"{ts}_unet"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(splits, run_dir / "split_manifest.csv")

    device = resolve_device(CONFIG.train.device)
    train_loader = DataLoader(SegmentationDataset(splits["train"], args.image_size, augment=True, seed=args.seed),
                              batch_size=args.batch_size, shuffle=True, num_workers=CONFIG.train.num_workers)
    val_loader = DataLoader(SegmentationDataset(splits["val"], args.image_size),
                            batch_size=args.batch_size, num_workers=CONFIG.train.num_workers)

    model = UNet(base_channels=args.base_channels).to(device)
    weights = _class_weights(train_loader).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights, ignore_index=IGNORE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    history, best_state, best_iou = [], None, -1.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for images, targets in train_loader:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), targets)
            loss.backward()
            optimizer.step()
            total += loss.item() * images.size(0)
        scheduler.step()
        val = run_validation(model, val_loader, device) if splits["val"] else {}
        lesion_iou = (val.get("per_class", {}).get("lesion", {}) or {}).get("iou") or 0.0
        history.append({"epoch": epoch, "train_loss": total / max(1, len(splits["train"])),
                        "val_mean_iou": val.get("mean_iou"), "val_lesion_iou": lesion_iou})
        logger.info("Epoch %d/%d loss=%.4f val_mIoU=%s val_lesionIoU=%.4f", epoch, args.epochs,
                    history[-1]["train_loss"], val.get("mean_iou"), lesion_iou)
        if lesion_iou > best_iou:
            best_iou = lesion_iou
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
    torch.save(model.state_dict(), run_dir / "model.pt")
    sha = hashlib.sha256((run_dir / "model.pt").read_bytes()).hexdigest()
    meta = {
        "architecture": "unet", "base_channels": args.base_channels, "image_size": args.image_size,
        "num_classes": NUM_SEG_CLASSES, "label_convention": {"0": "background", "1": "leaf", "2": "lesion"},
        "weights_sha256": sha, "trained_at": ts, "seg_root": str(args.seg_root),
        "split_sizes": {k: len(v) for k, v in splits.items()},
    }
    (run_dir / "model_meta.json").write_text(json.dumps(meta, indent=2))
    (run_dir / "training_history.json").write_text(json.dumps(history, indent=2))
    (run_dir / "validation_metrics.json").write_text(
        json.dumps(run_validation(model, val_loader, device) if splits["val"] else {}, indent=2))
    (SEG_RUNS_DIR / "latest.json").write_text(json.dumps({"run_dir": str(run_dir)}, indent=2))
    logger.info("Segmentation run saved to %s. Evaluate with `python -m ai.segmentation.evaluate`.", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
