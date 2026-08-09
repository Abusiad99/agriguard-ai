#!/usr/bin/env python3
"""
AgriGuard AI — Standalone Evaluation Entry Point.

Usage:
    python evaluate.py                     # evaluates the most recent training run
    python evaluate.py --run-dir <path>    # evaluates a specific run directory

Rebuilds the unified dataset (same deterministic pipeline as train.py, given the same
`datasets/` contents and CONFIG.data.random_seed) to reconstruct the exact test split
the model was evaluated on at training time, loads the saved model weights, and
recomputes accuracy/precision/recall/F1 and the confusion matrix — useful for
re-validating a model after a code change, or generating a fresh report without
retraining.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from ai.config import CONFIG
from ai.data.label_encoder import LabelEncoder
from ai.data.preprocessing import PreprocessingConfig, build_eval_transform
from ai.logging_setup import configure_logging
from ai.models.architectures import build_classifier, resolve_device
from ai.pipeline.data_pipeline import prepare_data
from ai.training.artifact_manager import ArtifactManager
from ai.training.metrics import compute_metrics
from ai.training.visualization import plot_confusion_matrix


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate a trained AgriGuard AI model.")
    parser.add_argument("--run-dir", type=str, default=None,
                         help="Path to a specific artifacts/runs/<timestamp>_<arch> directory. "
                              "Defaults to the most recent run.")
    parser.add_argument("--split", choices=["test", "val"], default="test",
                         help="Which split to evaluate on (default: test).")
    return parser.parse_args()


def main() -> int:
    logger = configure_logging("evaluate.log")
    args = parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else ArtifactManager.load_latest_run_dir()
    logger.info("Evaluating run: %s", run_dir)

    label_encoder = LabelEncoder.load(run_dir / "label_encoder.json")
    preprocessing_config = PreprocessingConfig.load(run_dir / "preprocessing_config.json")

    import json
    model_meta = json.loads((run_dir / "model_meta.json").read_text())
    architecture = model_meta["architecture"]
    num_classes = model_meta["num_classes"]

    device = resolve_device(CONFIG.train.device)
    model = build_classifier(architecture, num_classes=num_classes, pretrained=False)
    state_dict = torch.load(run_dir / "model.pt", map_location=device)
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()

    logger.info("Rebuilding dataset splits to recover the %s partition...", args.split)
    prepared = prepare_data()
    dataset = prepared.test_dataset if args.split == "test" else prepared.val_dataset
    # Ensure eval transform matches the saved run's preprocessing config exactly.
    dataset.transform = build_eval_transform(preprocessing_config)

    loader = DataLoader(dataset, batch_size=CONFIG.train.batch_size, shuffle=False,
                         num_workers=CONFIG.train.num_workers)

    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1).cpu().tolist()
            all_preds.extend(preds)
            all_labels.extend(labels.tolist())

    metrics = compute_metrics(all_labels, all_preds, label_encoder.classes)

    logger.info("=== Evaluation Results (%s split) ===", args.split)
    logger.info("Accuracy:            %.4f", metrics.accuracy)
    logger.info("Precision (macro):   %.4f", metrics.precision_macro)
    logger.info("Recall (macro):      %.4f", metrics.recall_macro)
    logger.info("F1 (macro):          %.4f", metrics.f1_macro)
    logger.info("Precision (weighted):%.4f", metrics.precision_weighted)
    logger.info("Recall (weighted):   %.4f", metrics.recall_weighted)
    logger.info("F1 (weighted):       %.4f", metrics.f1_weighted)

    out_dir = run_dir / f"evaluation_{args.split}"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics.to_json_dict(), indent=2))
    plot_confusion_matrix(metrics.confusion_matrix, metrics.class_names, out_dir / "confusion_matrix.png")
    logger.info("Evaluation report written to: %s", out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
