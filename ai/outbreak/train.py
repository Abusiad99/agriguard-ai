"""
Train the outbreak risk model on processed/training_table.csv.

    python -m ai.outbreak.train [--dataset datasets/outbreak] [--config configs/outbreak/default.json] [--no-promote]

Model: scikit-learn HistGradientBoostingClassifier — gradient-boosted trees for small,
tabular, partly-missing data. It handles missing weather natively (no imputation to
"normal" values) and categorical crop/disease codes, and needs no new dependency.
A temporal sequence model is not used: it needs long, regular per-area histories that
field-inspection data rarely has (revisit when such data exists).

Splits are chronological (train on the past, validate/test on later dates). The score
is calibrated on the validation period (isotonic, or sigmoid for smaller sets) only
when it has enough positives and negatives; otherwise it stays an uncalibrated risk
score and the model card says so. Training refuses to run below the configured data
minimums (readiness: insufficient_data).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from ai import registry
from ai.outbreak.config import OutbreakConfig, load_config
from ai.outbreak.features import FEATURE_NAMES, FEATURE_VERSION
from ai.outbreak.model import apply_calibration, to_matrix
from ai.outbreak.validate import default_dataset_root


class InsufficientData(Exception):
    pass


def load_table(dataset_root: Path) -> Tuple[pd.DataFrame, dict]:
    table_path = Path(dataset_root) / "processed" / "training_table.csv"
    manifest_path = Path(dataset_root) / "manifests" / "dataset_manifest.json"
    if not table_path.is_file() or not manifest_path.is_file():
        raise InsufficientData("No processed training table. Run validate and preprocess first.")
    table = pd.read_csv(table_path, keep_default_na=True)
    return table, json.loads(manifest_path.read_text(encoding="utf-8"))


def chronological_split(table: pd.DataFrame, config: OutbreakConfig):
    """Train on the past, validate and test on later dates, with an embargo: a row is
    kept only if its label window (as_of, as_of + horizon] ends before the next split
    starts. Otherwise a training label could be an outcome the validation or test
    period is scored on (leakage). `split_summary` reports how many rows were purged."""
    dates = sorted(table["as_of"].unique())
    n = len(dates)
    test_start = dates[max(1, int(n * (1 - config.test_fraction)))] if n > 2 else dates[-1]
    val_start = dates[max(1, int(n * (1 - config.test_fraction - config.validation_fraction)))] if n > 2 else dates[-1]
    as_of = pd.to_datetime(table["as_of"])
    label_end = as_of + pd.to_timedelta(table["horizon_days"], unit="D")
    val_ts, test_ts = pd.Timestamp(val_start), pd.Timestamp(test_start)
    train = table[(as_of < val_ts) & (label_end < val_ts)]
    val = table[(as_of >= val_ts) & (as_of < test_ts) & (label_end < test_ts)]
    test = table[as_of >= test_ts]
    return train, val, test


def split_summary(table: pd.DataFrame, train, val, test) -> dict:
    return {"train": len(train), "validation": len(val), "test": len(test),
            "purged_for_embargo": int(len(table) - len(train) - len(val) - len(test)),
            "validation_start": str(val["as_of"].min()) if len(val) else None,
            "test_start": str(test["as_of"].min()) if len(test) else None}


def training_extent(train_df: pd.DataFrame, resolution: float) -> dict:
    """Grid-index bounds of the cells seen in training; predictions far outside them
    would be extrapolation (see OutbreakModel.covers)."""
    cells = [key.split(":") for key in train_df["area_key"].unique()]
    lat = [int(c[1]) for c in cells]
    lon = [int(c[2]) for c in cells]
    return {"resolution_deg": resolution, "lat_index": [min(lat), max(lat)], "lon_index": [min(lon), max(lon)],
            "cells": len(cells),
            "bounds_deg": {"south": min(lat) * resolution, "north": (max(lat) + 1) * resolution,
                           "west": min(lon) * resolution, "east": (max(lon) + 1) * resolution}}


def check_minimums(table: pd.DataFrame, config: OutbreakConfig) -> None:
    positives = int(table["label"].sum())
    negatives = int(len(table) - positives)
    span = (pd.to_datetime(table["as_of"]).max() - pd.to_datetime(table["as_of"]).min()).days if len(table) else 0
    problems = []
    if len(table) < config.min_rows:
        problems.append(f"{len(table)} rows < {config.min_rows}")
    if positives < config.min_positives:
        problems.append(f"{positives} positives < {config.min_positives}")
    if negatives < config.min_negatives:
        problems.append(f"{negatives} negatives < {config.min_negatives}")
    if span < config.min_span_days:
        problems.append(f"{span} days of history < {config.min_span_days}")
    if problems:
        raise InsufficientData("Not enough data to train responsibly: " + "; ".join(problems))


def classification_metrics(y: np.ndarray, scores: np.ndarray, calibrated: bool) -> dict:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    out = {"samples": int(len(y)), "positives": int(y.sum()), "base_rate": round(float(y.mean()), 4) if len(y) else None}
    if len(np.unique(y)) == 2:
        out["roc_auc"] = round(float(roc_auc_score(y, scores)), 4)
        out["pr_auc"] = round(float(average_precision_score(y, scores)), 4)
        if calibrated:
            out["brier"] = round(float(brier_score_loss(y, scores)), 4)
        bins = np.clip((scores * 10).astype(int), 0, 9)
        out["reliability"] = [{"bin": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "count": int((bins == b).sum()),
                               "mean_score": round(float(scores[bins == b].mean()), 4),
                               "observed_rate": round(float(y[bins == b].mean()), 4)}
                              for b in range(10) if (bins == b).any()]
    else:
        out["note"] = "only one class present; ranking metrics undefined"
    return out


def train(dataset_root: Path, config: OutbreakConfig, promote: bool = True) -> Path:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    import joblib

    table, manifest = load_table(dataset_root)
    if manifest.get("feature_version") != FEATURE_VERSION:
        raise InsufficientData(f"training table was built with {manifest.get('feature_version')}; re-run preprocess")
    check_minimums(table, config)
    train_df, val_df, test_df = chronological_split(table, config)
    if train_df["label"].nunique() < 2:
        raise InsufficientData("the training period contains only one class")
    crops, diseases = sorted(table["crop"].unique()), sorted(table["disease"].unique())

    def xy(df):
        return to_matrix(df.to_dict("records"), crops, diseases), df["label"].to_numpy(dtype=int)

    x_train, y_train = xy(train_df)
    model = HistGradientBoostingClassifier(
        max_iter=config.max_iter, learning_rate=config.learning_rate, max_leaf_nodes=config.max_leaf_nodes,
        l2_regularization=config.l2_regularization, random_state=config.seed, early_stopping=False,
        categorical_features=[len(FEATURE_NAMES), len(FEATURE_NAMES) + 1])
    model.fit(x_train, y_train)

    calibration, calibrator = None, None
    x_val, y_val = xy(val_df) if len(val_df) else (None, np.array([]))
    if len(y_val):
        pos, neg = int(y_val.sum()), int(len(y_val) - y_val.sum())
        raw_val = model.predict_proba(x_val)[:, 1]
        if pos >= config.min_calibration_per_class and neg >= config.min_calibration_per_class:
            calibration, calibrator = "isotonic", IsotonicRegression(out_of_bounds="clip").fit(raw_val, y_val)
        elif pos >= 10 and neg >= 10:
            calibration, calibrator = "sigmoid", LogisticRegression().fit(raw_val.reshape(-1, 1), y_val)

    bundle = {"model": model, "calibrator": calibrator, "calibration": calibration,
              "feature_names": FEATURE_NAMES, "feature_version": FEATURE_VERSION, "crops": crops, "diseases": diseases,
              "pairs": sorted([list(p) for p in train_df[["crop", "disease"]].drop_duplicates().itertuples(index=False)]),
              "risk_cutpoints": config.risk_cutpoints,
              "grid_resolution_deg": manifest.get("grid_resolution_deg"),
              "extent": training_extent(train_df, manifest.get("grid_resolution_deg") or config.grid_resolution_deg)}
    bundle["reference"] = {name: {"p25": _q(train_df[name], .25), "p50": _q(train_df[name], .5), "p75": _q(train_df[name], .75)}
                           for name in FEATURE_NAMES}
    importance = {name: 0.0 for name in FEATURE_NAMES}
    if len(y_val) and len(np.unique(y_val)) == 2:
        result = permutation_importance(model, x_val, y_val, scoring="roc_auc", n_repeats=5, random_state=config.seed)
        importance = {name: max(0.0, float(result.importances_mean[i])) for i, name in enumerate(FEATURE_NAMES)}
    bundle["importance"] = importance

    metrics = {}
    for split, df in (("validation", val_df), ("test", test_df)):
        if len(df):
            x, y = xy(df)
            metrics[split] = classification_metrics(y, apply_calibration(bundle, model.predict_proba(x)[:, 1]), calibrator is not None)
    if "validation" in metrics and calibrator is not None:
        # The calibrator was fitted on this split, so its calibrated metrics are optimistic;
        # the test split is the honest estimate.
        metrics["validation"]["note"] = "calibrator fitted on this split; use test metrics"
    metrics["split_sizes"] = split_summary(table, train_df, val_df, test_df)

    base = registry.runs_dir("outbreak")
    run_dir = base / f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_hgb"
    suffix = 1
    while run_dir.exists():
        run_dir, suffix = base / f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_hgb_{suffix}", suffix + 1
    run_dir.mkdir(parents=True)
    joblib.dump(bundle, run_dir / "model.joblib")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    card = {
        "name": "outbreak-risk", "task": "outbreak", "version": run_dir.name, "architecture": "hist_gradient_boosting",
        "dataset_version": manifest.get("dataset_version"), "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_status": "completed", "classes": [f"{c}/{d}" for c, d in bundle["pairs"]],
        "metrics": metrics,
        "details": {"calibration": calibration, "score_kind": "calibrated_probability" if calibrator else "risk_score",
                    "feature_version": FEATURE_VERSION, "horizons_days": manifest.get("horizons_days"),
                    "grid_resolution_deg": manifest.get("grid_resolution_deg"), "risk_cutpoints": config.risk_cutpoints,
                    "min_completeness": config.min_completeness,
                    "trained_date_range": [str(train_df["as_of"].min()), str(train_df["as_of"].max())],
                    "training_extent": bundle["extent"],
                    # Training rows use the weather later observed for the forecast window; live
                    # predictions use a real forecast, so live skill may be lower than measured.
                    "forecast_features_training_source": "observed_weather_perfect_forecast_assumption"},
    }
    (run_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    if promote:
        registry.mark_latest("outbreak", run_dir)
    return run_dir


def _q(series: pd.Series, q: float):
    values = series.dropna()
    return round(float(values.quantile(q)), 4) if len(values) else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Train the outbreak risk model")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--no-promote", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_dir = train(args.dataset, load_config(args.config), promote=not args.no_promote)
    except InsufficientData as exc:
        print(f"Not trained: {exc}")
        return 2
    print(f"Run saved to {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
