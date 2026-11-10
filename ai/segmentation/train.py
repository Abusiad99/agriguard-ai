"""
Train a disease-localization (segmentation) model on the preprocessed dataset.

    python -m ai.segmentation.train [--config configs/segmentation/default.json] [--dataset datasets/segmentation]
                                    [--epochs N] [--device cpu|cuda] [--resume RUN_DIR] [--no-promote]

Never started automatically (training is expensive). Each run gets a new directory
under artifacts/segmentation/runs/ — existing runs and weights are never overwritten —
holding best.pt, last.pt (resumable), config.json, class_mapping.json, history.json,
manifest_ref.json, train.log and model_card.json. On success the run is marked as the
served model (latest.json) unless --no-promote is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

from ai import registry
from ai.models.architectures import resolve_device
from ai.segmentation.classes import ClassMapping
from ai.segmentation.config import SegmentationConfig, load_config
from ai.segmentation.dataset import SegmentationDataset
from ai.segmentation.metrics import build_loss, confusion_matrix, median_frequency_weights, metrics_from_confusion
from ai.segmentation.models import build_segmentation_model
from ai.segmentation.validate import default_dataset_root


class DatasetNotReady(Exception):
    pass


def _grad_scaler(enabled: bool):
    try:
        return torch.amp.GradScaler("cuda", enabled=enabled)
    except (AttributeError, TypeError):  # torch < 2.3
        return torch.cuda.amp.GradScaler(enabled=enabled)


def _new_run_dir(config: SegmentationConfig) -> Path:
    base = registry.runs_dir("segmentation")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = base / f"{stamp}_{config.architecture}-{config.encoder}"
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{config.architecture}-{config.encoder}_{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)
    return run_dir


def _logger(run_dir: Path) -> logging.Logger:
    log = logging.getLogger(f"agriguard.segmentation.train.{run_dir.name}")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        for handler in (logging.FileHandler(run_dir / "train.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
            handler.setFormatter(fmt)
            log.addHandler(handler)
    return log


def _class_weights(config: SegmentationConfig, manifest: dict, mapping: ClassMapping):
    if config.class_weights in (None, "none"):
        return None
    if config.class_weights == "auto":
        train_px = manifest["class_pixels"]["train"]
        return median_frequency_weights([train_px.get(c.name, 0) for c in mapping.classes])
    weights = [float(w) for w in config.class_weights]
    if len(weights) != mapping.num_classes:
        raise ValueError(f"class_weights has {len(weights)} values for {mapping.num_classes} classes")
    return weights


def evaluate_loader(model, loader, loss_fn, device, num_classes, use_amp):
    model.eval()
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    total, batches = 0.0, 0
    with torch.no_grad():
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits = model(images)
            total += float(loss_fn(logits, masks))
            batches += 1
            cm += confusion_matrix(logits.argmax(1), masks, num_classes)
    return total / max(1, batches), cm


def train(dataset_root: Path, config: SegmentationConfig, resume: Optional[Path] = None, promote: bool = True,
          allow_small: bool = False) -> Path:
    dataset_root = Path(dataset_root)
    manifest_path = dataset_root / "manifests" / "dataset_manifest.json"
    if not manifest_path.is_file():
        raise DatasetNotReady("No dataset manifest. Run validate and preprocess first "
                              "(scripts\\segmentation.ps1 -Action preprocess).")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mapping = ClassMapping.load(dataset_root / "manifests" / "class_mapping.json")
    if manifest["splits"].get("train", 0) < config.min_train_images and not allow_small:
        raise DatasetNotReady(f"Only {manifest['splits'].get('train', 0)} training images; at least "
                              f"{config.min_train_images} are required (config.min_train_images).")
    if manifest["splits"].get("validation", 0) < 1:
        raise DatasetNotReady("The validation split is empty; adjust split_ratios or add data.")

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    device = resolve_device(config.device)
    use_amp = bool(config.mixed_precision and device.type == "cuda")

    run_dir = Path(resume) if resume else _new_run_dir(config)
    log = _logger(run_dir)
    train_ds = SegmentationDataset(dataset_root, "train", config, train=True)
    val_ds = SegmentationDataset(dataset_root, "validation", config, train=False)
    loader_kw = {"num_workers": config.num_workers, "pin_memory": device.type == "cuda"}
    train_loader = DataLoader(train_ds, batch_size=config.batch_size, shuffle=True, drop_last=len(train_ds) > config.batch_size, **loader_kw)
    val_loader = DataLoader(val_ds, batch_size=config.batch_size, shuffle=False, **loader_kw)

    model = build_segmentation_model(config.architecture, config.encoder, mapping.num_classes, config.encoder_pretrained).to(device)
    weights = _class_weights(config, manifest, mapping)
    loss_fn = build_loss(config.loss, mapping.num_classes, weights).to(device)
    if config.optimizer == "sgd":
        optimizer = torch.optim.SGD(model.parameters(), lr=config.learning_rate, momentum=0.9, weight_decay=config.weight_decay)
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    if config.scheduler == "cosine":
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, config.epochs))
    elif config.scheduler == "plateau":
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=3)
    else:
        scheduler = None
    scaler = _grad_scaler(use_amp)

    start_epoch, best_score, stale, history, best_metrics = 1, -1.0, 0, [], {}
    if resume:
        state = torch.load(run_dir / "last.pt", map_location=device, weights_only=False)
        model.load_state_dict(state["model_state"])
        optimizer.load_state_dict(state["optimizer_state"])
        if scheduler and state.get("scheduler_state"):
            scheduler.load_state_dict(state["scheduler_state"])
        scaler.load_state_dict(state.get("scaler_state", {}))
        start_epoch, best_score, stale = state["epoch"] + 1, state["best_score"], state["stale"]
        history, best_metrics = state["history"], state.get("best_metrics", {})
        log.info("Resuming %s at epoch %d", run_dir.name, start_epoch)
    else:
        (run_dir / "config.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
        mapping.save(run_dir / "class_mapping.json")
        (run_dir / "manifest_ref.json").write_text(json.dumps({
            "dataset_root": str(dataset_root), "dataset_version": manifest["dataset_version"],
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
    log.info("Device %s, AMP %s, %d train / %d validation images, classes %s, weights %s",
             device, use_amp, len(train_ds), len(val_ds), mapping.names, weights)

    status = "completed"
    for epoch in range(start_epoch, config.epochs + 1):
        t0 = time.time()
        model.train()
        running = 0.0
        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits = model(images)
            loss = loss_fn(logits, masks)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running += loss.item()
        val_loss, cm = evaluate_loader(model, val_loader, loss_fn, device, mapping.num_classes, use_amp)
        metrics = metrics_from_confusion(cm, mapping.names, mapping.background_id)
        score = metrics["foreground_mean_iou"] if metrics["foreground_mean_iou"] is not None else (metrics["mean_iou"] or 0.0)
        if isinstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
            scheduler.step(score)
        elif scheduler is not None:
            scheduler.step()
        record = {"epoch": epoch, "train_loss": round(running / max(1, len(train_loader)), 6), "val_loss": round(val_loss, 6),
                  "val_mean_iou": metrics["mean_iou"], "val_foreground_mean_iou": metrics["foreground_mean_iou"],
                  "val_mean_dice": metrics["mean_dice"], "lr": optimizer.param_groups[0]["lr"], "seconds": round(time.time() - t0, 1)}
        history.append(record)
        log.info("epoch %d %s", epoch, json.dumps(record))

        if score > best_score + 1e-6:
            best_score, stale, best_metrics = score, 0, {**metrics, "epoch": epoch}
            torch.save({"model_state": model.state_dict(), "epoch": epoch, "score": score}, run_dir / "best.pt")
        else:
            stale += 1
        torch.save({"model_state": model.state_dict(), "optimizer_state": optimizer.state_dict(),
                    "scheduler_state": scheduler.state_dict() if scheduler else None, "scaler_state": scaler.state_dict(),
                    "epoch": epoch, "best_score": best_score, "stale": stale, "history": history,
                    "best_metrics": best_metrics}, run_dir / "last.pt")
        if stale >= config.early_stopping_patience:
            status = "stopped_early"
            log.info("Early stopping at epoch %d (no improvement for %d epochs)", epoch, stale)
            break

    (run_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    card = {
        "name": "disease-segmentation", "task": "segmentation", "version": run_dir.name,
        "architecture": f"{config.architecture}/{config.encoder}", "dataset_version": manifest["dataset_version"],
        "trained_at": datetime.now(timezone.utc).isoformat(), "training_status": status,
        "classes": mapping.names,
        "metrics": {"validation": {k: best_metrics.get(k) for k in
                                   ("mean_iou", "foreground_mean_iou", "mean_dice", "foreground_mean_dice", "pixel_accuracy", "epoch")},
                    "validation_per_class": best_metrics.get("per_class", {})},
        "details": {"class_mapping": mapping.to_dict(), "config": config.to_dict(),
                    "has_leaf_annotation": mapping.has_leaf_annotation, "epochs_run": len(history),
                    "device": str(device), "train_images": len(train_ds), "validation_images": len(val_ds)},
    }
    (run_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    if promote:
        registry.mark_latest("segmentation", run_dir)
        log.info("Promoted %s as the served segmentation model", run_dir.name)
    return run_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Train the disease segmentation model")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--resume", type=Path, default=None, help="continue an interrupted run from its last.pt")
    parser.add_argument("--no-promote", action="store_true", help="don't make this run the served model")
    args = parser.parse_args(argv)
    config = load_config(args.config, epochs=args.epochs, batch_size=args.batch_size, device=args.device)
    if args.resume:
        config = load_config(args.resume / "config.json", epochs=args.epochs, device=args.device)
    try:
        run_dir = train(args.dataset, config, resume=args.resume, promote=not args.no_promote)
    except DatasetNotReady as exc:
        print(f"Dataset not ready: {exc}")
        return 2
    print(f"Run saved to {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
