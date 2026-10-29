#!/usr/bin/env python3
"""
AgriGuard AI — Confidence calibration & threshold selection.

Usage:
    python calibrate.py                    # calibrates the most recent training run
    python calibrate.py --run-dir <path>

Uses ONLY the validation split recorded in the run's split_manifest.csv:
  1. fits a softmax temperature (temperature scaling) by minimizing validation NLL;
  2. selects the "confident" and "reject" thresholds against the targets in
     ai/config.py (AGRIGUARD_TARGET_SELECTIVE_ACCURACY,
     AGRIGUARD_TARGET_CANDIDATE_TOPK_ACCURACY);
  3. selects a plant-identification threshold on the summed probability of the
     predicted plant's classes;
  4. writes calibration.json into the run directory (loaded by InferenceService).

The TEST split is never touched here; evaluate.py reports how these validation-
selected settings perform on held-out test data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from ai.config import CONFIG
from ai.evaluation.manifest import load_split_manifest
from ai.evaluation.runner import compute_logits, load_bundle, split_arrays
from ai.inference.calibration import (
    CalibrationArtifact,
    calibration_metrics,
    fit_temperature,
    select_thresholds,
    softmax,
)
from ai.logging_setup import configure_logging
from ai.training.artifact_manager import ArtifactManager


def plant_mass_and_correct(probs: np.ndarray, labels: np.ndarray, classes):
    plants = np.array([c.split("___", 1)[0] for c in classes])
    pred_plant = plants[probs.argmax(axis=1)]
    true_plant = plants[labels]
    mass = np.array([probs[i, plants == pred_plant[i]].sum() for i in range(len(labels))])
    return mass, pred_plant == true_plant


def select_min_threshold(scores: np.ndarray, correct: np.ndarray, target: float) -> float:
    order = np.argsort(-scores, kind="stable")
    cum = np.cumsum(correct[order].astype(float)) / np.arange(1, len(order) + 1)
    ok = np.where(cum >= target)[0]
    if len(ok) == 0:
        return float(scores.max())
    return float(scores[order][int(ok.max())])


def calibrate_run(run_dir: Path, logger) -> CalibrationArtifact:
    manifest = load_split_manifest(run_dir)
    if manifest is None:
        raise SystemExit(f"{run_dir} has no split_manifest.csv; retrain with the current train.py "
                         "so the exact validation split is recorded.")
    bundle = load_bundle(run_dir)
    paths, labels = split_arrays(bundle, manifest, "val")
    logger.info("Calibrating %s on %d validation images.", bundle.model_version, len(labels))
    logits = compute_logits(bundle, paths, "val")

    before = calibration_metrics(softmax(logits, 1.0), labels)
    temperature = fit_temperature(logits, labels)
    probs = softmax(logits, temperature)
    after = calibration_metrics(probs, labels)
    logger.info("Temperature=%.3f  val ECE %.4f -> %.4f  NLL %.4f -> %.4f",
                temperature, before["ece"], after["ece"], before["nll"], after["nll"])

    cfg = CONFIG.inference
    thresholds = select_thresholds(
        probs, labels,
        target_selective_accuracy=cfg.target_selective_accuracy,
        target_candidate_topk_accuracy=cfg.target_candidate_topk_accuracy,
        top_k=cfg.candidate_top_k, selection_split="val",
    )
    mass, plant_correct = plant_mass_and_correct(probs, labels, bundle.label_encoder.classes)
    plant_threshold = select_min_threshold(mass, plant_correct, cfg.target_selective_accuracy)

    artifact = CalibrationArtifact(
        temperature=temperature, thresholds=thresholds, plant_mass_threshold=plant_threshold,
        validation_metrics_before=before, validation_metrics_after=after,
    )
    path = artifact.save(run_dir)
    logger.info("Thresholds (val): confident>=%.3f (coverage %.1f%%, acc %s) reject<%.3f (%.1f%% inconclusive); "
                "plant-mass>=%.3f. Saved %s",
                thresholds.confident_threshold, 100 * thresholds.confident_coverage,
                f"{thresholds.confident_accuracy:.3f}" if thresholds.confident_accuracy is not None else "n/a",
                thresholds.reject_threshold, 100 * thresholds.rejected_coverage, plant_threshold, path)
    for note in thresholds.notes:
        logger.warning(note)
    return artifact


def main() -> int:
    logger = configure_logging("calibrate.log")
    ap = argparse.ArgumentParser(description="Calibrate confidences and select thresholds on the validation split.")
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else ArtifactManager.load_latest_run_dir()
    calibrate_run(run_dir, logger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
