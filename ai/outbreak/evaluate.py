"""
Evaluate an outbreak run on the current processed table's held-out (latest) period.

    python -m ai.outbreak.evaluate [--run RUN_DIR] [--dataset datasets/outbreak]

Writes <run>/evaluation/: metrics.json (overall + per crop/disease), reliability.png
(predicted score vs observed rate), and adds the summary to model_card.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai.outbreak.config import OutbreakConfig
from ai.outbreak.model import OutbreakModel, apply_calibration, to_matrix
from ai.outbreak.train import chronological_split, classification_metrics, load_table
from ai.outbreak.validate import default_dataset_root


def evaluate(dataset_root: Path, run_dir: Optional[Path] = None, allow_dataset_mismatch: bool = False) -> dict:
    try:
        model = OutbreakModel(run_dir)
    except FileNotFoundError as exc:
        raise SystemExit(f"{exc} Train a model first (scripts/outbreak.ps1 -Action train).")
    config = OutbreakConfig(**json.loads((model.run_dir / "config.json").read_text(encoding="utf-8")))
    table, manifest = load_table(dataset_root)
    trained_on = (model.card or {}).get("dataset_version")
    mismatch = trained_on is not None and trained_on != manifest.get("dataset_version")
    if mismatch and not allow_dataset_mismatch:
        raise SystemExit(f"The processed dataset ({manifest.get('dataset_version')}) is not the one this model was "
                         f"trained on ({trained_on}); its test period may overlap the model's training data. Retrain, "
                         "or pass --allow-dataset-mismatch to evaluate anyway (results are flagged).")
    _, _, test = chronological_split(table, config)
    if not len(test):
        raise SystemExit("The test period is empty.")
    bundle = model.bundle
    scores = apply_calibration(bundle, bundle["model"].predict_proba(
        to_matrix(test.to_dict("records"), bundle["crops"], bundle["diseases"]))[:, 1])
    y = test["label"].to_numpy(dtype=int)
    metrics = {"overall": classification_metrics(y, scores, model.calibrated), "per_crop_disease": []}
    for (crop, disease), idx in test.groupby(["crop", "disease"]).groups.items():
        sel = test.index.get_indexer(idx)
        metrics["per_crop_disease"].append({"crop": crop, "disease": disease,
                                            **classification_metrics(y[sel], scores[sel], model.calibrated)})
    metrics.update({"run": model.run_dir.name, "dataset_version": manifest.get("dataset_version"),
                    "dataset_mismatch": mismatch,
                    "score_kind": "calibrated_probability" if model.calibrated else "risk_score",
                    "evaluated_at": datetime.now(timezone.utc).isoformat()})
    out = model.run_dir / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    _plot_reliability(metrics["overall"].get("reliability", []), out / "reliability.png")
    card = model.card
    card.setdefault("metrics", {})["evaluation"] = {k: metrics["overall"].get(k) for k in
                                                    ("samples", "positives", "roc_auc", "pr_auc", "brier")}
    (model.run_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return metrics


def _plot_reliability(bins, path: Path) -> None:
    if not bins:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect calibration")
    ax.plot([b["mean_score"] for b in bins], [b["observed_rate"] for b in bins], "o-", color="#2e7d32", label="model")
    ax.set_xlabel("predicted score")
    ax.set_ylabel("observed outbreak rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate an outbreak risk run")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--allow-dataset-mismatch", action="store_true",
                        help="evaluate even if the dataset changed since training (results are flagged)")
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.dataset, args.run, args.allow_dataset_mismatch)["overall"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
