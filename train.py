#!/usr/bin/env python3
"""
AgriGuard AI — Training Entry Point.

Usage:
    python train.py

Requires nothing but a `datasets/` folder containing one or more supported datasets
(any internal structure — see ai/data/adapters/). No paths need to be edited; all
configuration is via environment variables / .env (see ai/config.py) or left at
sensible defaults.

This script performs, in order (FR-DATA-1..8):
  1. Dataset discovery, structural adapter selection, label normalization,
     corrupted-image rejection, cross-dataset deduplication.
  2. Stratified train/validation/test split.
  3. Label encoding.
  4. Dataset construction with augmentation applied to the TRAIN split only.
  5. Model construction (architecture selected via AGRIGUARD_ARCHITECTURE).
  6. Training with class balancing, backbone-freeze warmup, mixed precision, and
     early stopping.
  7. Evaluation on the held-out test split (accuracy/precision/recall/F1, confusion
     matrix).
  8. Persisting every required artifact (weights, label encoder, preprocessing
     config, training history, metrics, confusion matrix image, training curve
     image, a copy of the exact unified dataset index used, and the resolved run
     configuration) to a timestamped `artifacts/runs/<timestamp>_<arch>/` directory,
     and updating `artifacts/runs/latest.json` so inference.py always loads the most
     recent model with no manual path editing.
"""
from __future__ import annotations

import sys
import time

from ai.config import CONFIG
from ai.logging_setup import configure_logging
from ai.models.architectures import build_classifier, resolve_device
from ai.pipeline.data_pipeline import prepare_data
from ai.training.artifact_manager import ArtifactManager
from ai.training.metrics import compute_metrics
from ai.training.trainer import Trainer

import torch
from torch.utils.data import DataLoader


def evaluate_on_split(model, dataset, device, batch_size, num_workers):
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1).cpu().tolist()
            all_preds.extend(preds)
            all_labels.extend(labels.tolist())
    return all_labels, all_preds


def main() -> int:
    logger = configure_logging("train.log")
    start = time.time()
    logger.info("AgriGuard AI — Training Pipeline starting.")
    logger.info("Datasets directory: %s", CONFIG.paths.datasets_dir)
    logger.info("Artifacts directory: %s", CONFIG.paths.artifacts_dir)

    try:
        prepared = prepare_data()
    except RuntimeError as exc:
        logger.error("Data preparation failed: %s", exc)
        return 1

    device = resolve_device(CONFIG.train.device)
    logger.info("Training on device: %s", device)

    num_classes = prepared.label_encoder.num_classes
    model = build_classifier(CONFIG.train.architecture, num_classes=num_classes, pretrained=True)

    trainer = Trainer(
        model=model,
        device=device,
        train_dataset=prepared.train_dataset,
        val_dataset=prepared.val_dataset,
        num_classes=num_classes,
    )

    logger.info("=== Training: architecture=%s, classes=%d, train=%d, val=%d, test=%d ===",
                CONFIG.train.architecture, num_classes,
                len(prepared.train_dataset), len(prepared.val_dataset), len(prepared.test_dataset))
    history = trainer.fit()

    logger.info("=== Evaluating on held-out TEST split ===")
    y_true, y_pred = evaluate_on_split(
        trainer.model, prepared.test_dataset, device,
        CONFIG.train.batch_size, CONFIG.train.num_workers,
    )
    metrics = compute_metrics(y_true, y_pred, prepared.label_encoder.classes)
    logger.info(
        "Test results — accuracy=%.4f, precision(macro)=%.4f, recall(macro)=%.4f, f1(macro)=%.4f",
        metrics.accuracy, metrics.precision_macro, metrics.recall_macro, metrics.f1_macro,
    )

    logger.info("=== Persisting artifacts ===")
    artifact_manager = ArtifactManager(architecture=CONFIG.train.architecture)
    artifact_manager.save_model(trainer.model, num_classes=num_classes, image_size=CONFIG.data.image_size)
    artifact_manager.save_label_encoder(prepared.label_encoder)
    artifact_manager.save_preprocessing_config(prepared.preprocessing_config)
    artifact_manager.save_training_history(history)
    artifact_manager.save_metrics(metrics)
    artifact_manager.copy_dataset_index(CONFIG.paths.artifacts_dir / "unified_dataset_index.csv")
    artifact_manager.save_run_config()
    artifact_manager.mark_as_latest()

    elapsed = time.time() - start
    logger.info("Training complete in %.1fs. Artifacts saved to: %s", elapsed, artifact_manager.run_dir)
    logger.info("Run `python evaluate.py` for a standalone evaluation report, or "
                "`python predict.py <image_path>` / `python inference.py` to use the model.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
