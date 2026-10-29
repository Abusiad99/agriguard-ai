#!/usr/bin/env python3
"""
AgriGuard AI — Reproducible Evaluation Report.

Usage:
    python evaluate.py                     # evaluates the most recent training run on TEST
    python evaluate.py --run-dir <path>    # a specific run directory
    python evaluate.py --split val

Evaluates against the exact split recorded in the run's split_manifest.csv (never a
re-derived split) and writes `<run_dir>/evaluation_<split>/`:

  report.json            every number below + model version, data fingerprint,
                         evaluation date and configuration
  report.md              human-readable summary
  per_class_metrics.csv  precision / recall / F1 / support per class
  confusion_matrix.csv / confusion_matrix.png
  reliability_diagram.png, risk_coverage.png

Metrics: accuracy, top-3/top-5 accuracy, macro & weighted precision/recall/F1,
per-class metrics, confusion matrix, calibration (ECE, MCE, Brier, NLL) before and
after temperature scaling, selective classification (risk–coverage, AURC), the
validation-selected decision thresholds applied to this split, cross-split leakage
check, and single-image CPU latency.

Limitations stated in the report itself: the TEST split comes from the same source
distribution as training (web-collected "in-the-wild" photos); it is not an
independent field trial, and it contains no healthy plants and no out-of-
distribution images, so unknown-disease rejection is NOT measured here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ai.config import CONFIG
from ai.evaluation.manifest import leakage_report, load_split_manifest, manifest_fingerprint
from ai.evaluation.runner import compute_logits, load_bundle, measure_latency, split_arrays
from ai.inference.calibration import (
    CalibrationArtifact,
    calibration_metrics,
    evaluate_thresholds,
    reliability_bins,
    risk_coverage_curve,
    softmax,
    summarize_risk_coverage,
)
from ai.logging_setup import configure_logging
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
    parser.add_argument("--latency-samples", type=int, default=50)
    parser.add_argument("--skip-leakage", action="store_true")
    return parser.parse_args()


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=CONFIG.paths.project_root,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _topk_accuracy(probs: np.ndarray, labels: np.ndarray, k: int) -> float:
    k = min(k, probs.shape[1])
    top = np.argsort(-probs, axis=1)[:, :k]
    return float((top == labels[:, None]).any(axis=1).mean())


def _plots(out_dir: Path, probs_raw, probs_cal, labels):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 5))
    for probs, name in ((probs_raw, "raw softmax"), (probs_cal, "temperature-scaled")):
        bins = [b for b in reliability_bins(probs, labels) if b.count]
        ax.plot([b.mean_confidence for b in bins], [b.accuracy for b in bins], marker="o", label=name)
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect calibration")
    ax.set_xlabel("mean predicted confidence")
    ax.set_ylabel("observed accuracy")
    ax.set_title("Reliability diagram")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "reliability_diagram.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 4))
    conf = probs_cal.max(axis=1)
    correct = probs_cal.argmax(axis=1) == labels
    curve = risk_coverage_curve(conf, correct)
    ax.plot(curve["coverage"], curve["selective_accuracy"])
    ax.set_xlabel("coverage (fraction of images answered)")
    ax.set_ylabel("accuracy on answered images")
    ax.set_title(f"Risk–coverage (AURC={curve['aurc']:.3f})")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "risk_coverage.png", dpi=120)
    plt.close(fig)


def _markdown(report: dict) -> str:
    m = report["classification"]
    cal = report["calibration"]
    lines = [
        f"# Evaluation report — {report['model']['model_version']}",
        "",
        f"- Evaluated: {report['evaluated_at']} (git {report['git_commit'][:10]})",
        f"- Split: **{report['split']}** — {report['data']['n_images']} images, "
        f"{report['data']['n_classes_present']} classes present "
        f"(fingerprint `{report['data']['split_fingerprint'][:16]}`)",
        f"- Architecture: {report['model']['architecture']}; temperature: {cal['temperature']}",
        "",
        "## Classification (top-1 prediction, no abstention)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| accuracy | {m['accuracy']:.4f} |",
        f"| top-3 accuracy | {m['top3_accuracy']:.4f} |",
        f"| top-5 accuracy | {m['top5_accuracy']:.4f} |",
        f"| macro precision | {m['precision_macro']:.4f} |",
        f"| macro recall | {m['recall_macro']:.4f} |",
        f"| macro F1 | {m['f1_macro']:.4f} |",
        f"| weighted F1 | {m['f1_weighted']:.4f} |",
        "",
        "## Calibration",
        "",
        "| | ECE | MCE | Brier | NLL | mean confidence |",
        "|---|---|---|---|---|---|",
    ]
    for key, label in (("raw", "raw softmax"), ("calibrated", "temperature-scaled")):
        c = cal[key]
        lines.append(f"| {label} | {c['ece']:.4f} | {c['mce']:.4f} | {c['brier']:.4f} | {c['nll']:.4f} | "
                     f"{c['mean_confidence']:.4f} |")
    lines += ["", "## Selective classification (calibrated confidence)", "",
              f"AURC: {report['selective']['aurc']:.4f}", "",
              "| coverage | accuracy on answered | confidence threshold |", "|---|---|---|"]
    for r in report["selective"]["summary"]:
        lines.append(f"| {r['coverage']:.2f} | {r['selective_accuracy']:.4f} | {r['confidence_threshold']:.4f} |")
    d = report["decision_thresholds"]
    lines += ["", "## Validation-selected decision thresholds applied to this split", ""]
    if d.get("available"):
        a = d["applied"]
        fmt = lambda v: "n/a" if v is None else f"{v:.4f}"  # noqa: E731
        lines += [
            f"confident ≥ {d['confident_threshold']:.4f}, inconclusive < {d['reject_threshold']:.4f} "
            f"(selected on {d['selection_split']}, target selective accuracy {d['target_selective_accuracy']:.0%})",
            "",
            "| status | share of images | accuracy |",
            "|---|---|---|",
            f"| confident | {a['confident_coverage']:.4f} | top-1 {fmt(a['confident_accuracy'])} |",
            f"| uncertain | {a['uncertain_coverage']:.4f} | top-1 {fmt(a['uncertain_top1_accuracy'])}, "
            f"top-{d['candidate_top_k']} {fmt(a['uncertain_topk_accuracy'])} |",
            f"| inconclusive | {a['rejected_coverage']:.4f} | (top-1 if forced: {fmt(a['rejected_top1_accuracy_if_forced'])}) |",
        ]
    else:
        lines.append("No calibration.json — run `python calibrate.py` first.")
    weak = report["per_class_flags"]
    lines += ["", "## Classes needing attention", "",
              f"- Classes with < {weak['min_support']} test images (metrics unreliable): "
              f"{len(weak['low_support'])}",
              f"- Classes with F1 < 0.5: {len(weak['low_f1'])}: " + ", ".join(weak["low_f1"][:30]),
              "", "## Leakage check", "", "```", json.dumps(report.get("leakage", {}), indent=2), "```",
              "", "## Latency (single image, batch 1)", "", "```", json.dumps(report["latency"], indent=2), "```",
              "", "## Limitations", ""]
    lines += [f"- {x}" for x in report["limitations"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    logger = configure_logging("evaluate.log")
    args = parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else ArtifactManager.load_latest_run_dir()
    logger.info("Evaluating run: %s", run_dir)
    manifest = load_split_manifest(run_dir)
    if manifest is None:
        logger.error("%s has no split_manifest.csv. Retrain with the current train.py so the exact "
                     "split is recorded; re-deriving the split is not reproducible.", run_dir)
        return 2

    bundle = load_bundle(run_dir)
    paths, labels = split_arrays(bundle, manifest, args.split)
    logits = compute_logits(bundle, paths, args.split)
    calibration = CalibrationArtifact.load(run_dir)
    temperature = calibration.temperature if calibration else 1.0
    probs_raw = softmax(logits, 1.0)
    probs_cal = softmax(logits, temperature)
    classes = bundle.label_encoder.classes

    metrics = compute_metrics(labels.tolist(), probs_cal.argmax(axis=1).tolist(), classes)
    out_dir = run_dir / f"evaluation_{args.split}"
    out_dir.mkdir(exist_ok=True)

    per_class = pd.DataFrame.from_dict(metrics.per_class, orient="index")
    per_class.index.name = "class"
    per_class.to_csv(out_dir / "per_class_metrics.csv")
    pd.DataFrame(metrics.confusion_matrix, index=classes, columns=classes).to_csv(out_dir / "confusion_matrix.csv")
    plot_confusion_matrix(metrics.confusion_matrix, classes, out_dir / "confusion_matrix.png")
    _plots(out_dir, probs_raw, probs_cal, labels)

    conf = probs_cal.max(axis=1)
    correct = probs_cal.argmax(axis=1) == labels
    curve = risk_coverage_curve(conf, correct)

    decision = {"available": False}
    if calibration:
        t = calibration.thresholds
        decision = {
            "available": True,
            "confident_threshold": t.confident_threshold,
            "reject_threshold": t.reject_threshold,
            "selection_split": t.selection_split,
            "target_selective_accuracy": t.target_selective_accuracy,
            "target_candidate_topk_accuracy": t.target_candidate_topk_accuracy,
            "candidate_top_k": t.candidate_top_k,
            "achieved_on_selection_split": {
                "confident_coverage": t.confident_coverage, "confident_accuracy": t.confident_accuracy,
                "uncertain_coverage": t.uncertain_coverage, "uncertain_topk_accuracy": t.uncertain_topk_accuracy,
                "rejected_coverage": t.rejected_coverage, "target_met": t.target_met,
            },
            "applied": evaluate_thresholds(probs_cal, labels, t.confident_threshold, t.reject_threshold,
                                           t.candidate_top_k),
        }

    min_support = 10
    low_support = [c for c, v in metrics.per_class.items() if v["support"] < min_support]
    low_f1 = sorted((c for c, v in metrics.per_class.items() if v["support"] > 0 and v["f1"] < 0.5),
                    key=lambda c: metrics.per_class[c]["f1"])

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "split": args.split,
        "model": {
            "model_version": bundle.model_version,
            "run_dir": str(run_dir),
            "architecture": bundle.architecture,
            "weights_sha256": bundle.weights_sha256,
            "num_classes": bundle.label_encoder.num_classes,
            "image_size": bundle.preprocessing.image_size,
        },
        "data": {
            "n_images": int(len(labels)),
            "n_classes_present": int(len(set(labels.tolist()))),
            "split_sizes": manifest["split"].value_counts().to_dict(),
            "split_fingerprint": manifest_fingerprint(manifest, args.split),
            "manifest_fingerprint": manifest_fingerprint(manifest),
            "source_datasets": sorted(set(manifest["source_dataset"].astype(str))),
        },
        "classification": {
            "accuracy": metrics.accuracy,
            "top3_accuracy": _topk_accuracy(probs_cal, labels, 3),
            "top5_accuracy": _topk_accuracy(probs_cal, labels, 5),
            "precision_macro": metrics.precision_macro,
            "recall_macro": metrics.recall_macro,
            "f1_macro": metrics.f1_macro,
            "precision_weighted": metrics.precision_weighted,
            "recall_weighted": metrics.recall_weighted,
            "f1_weighted": metrics.f1_weighted,
            "per_class_csv": "per_class_metrics.csv",
        },
        "calibration": {
            "temperature": temperature,
            "calibrated": calibration is not None,
            "raw": calibration_metrics(probs_raw, labels),
            "calibrated": calibration_metrics(probs_cal, labels),
        },
        "selective": {"aurc": curve["aurc"], "summary": summarize_risk_coverage(conf, correct)},
        "decision_thresholds": decision,
        "per_class_flags": {"min_support": min_support, "low_support": low_support, "low_f1": low_f1},
        "latency": measure_latency(bundle, paths, n=args.latency_samples),
        "config": {"inference": {k: v for k, v in vars(CONFIG.inference).items()},
                   "data": {"image_size": CONFIG.data.image_size, "seed": CONFIG.data.random_seed}},
        "limitations": [
            "Test images come from the same web-collected source distribution as training; this is not an "
            "independent field validation.",
            "The dataset contains no healthy-plant images and no non-plant / unsupported-disease images, so the "
            "model cannot output 'healthy' and its ability to reject unknown conditions is NOT measured here.",
            "Classes with few test images have unreliable per-class metrics (see per_class_flags).",
            "Calibration (temperature) and thresholds were fitted on the validation split; numbers here are "
            "held-out only if this report is for the test split.",
        ],
    }
    if not args.skip_leakage:
        report["leakage"] = leakage_report(manifest)

    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / "report.md").write_text(_markdown(report))
    logger.info("=== %s split: acc=%.4f macroF1=%.4f top3=%.4f ECE raw=%.4f cal=%.4f ===",
                args.split, metrics.accuracy, metrics.f1_macro, report["classification"]["top3_accuracy"],
                report["calibration"]["raw"]["ece"], report["calibration"]["calibrated"]["ece"])
    logger.info("Evaluation report written to: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
