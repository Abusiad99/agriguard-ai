"""
Outbreak preprocessing: raw CSVs -> processed/training_table.csv + manifests/dataset_manifest.json

    python -m ai.outbreak.preprocess [--dataset datasets/outbreak] [--config configs/outbreak/default.json]

Observations are aggregated to grid cells (ai/outbreak/grid.py). For every cell x crop
x disease series, one row is generated per `step_days` reference date (`as_of`) and
per forecast horizon, with features from ai/outbreak/features.py and the label
"any positive in (as_of, as_of + horizon]". Rows whose window has no inspection at
all are not labeled negative — they are skipped (unknown, not healthy).
Weather rows are matched to the cell containing their coordinates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ai.outbreak import grid
from ai.outbreak.config import load_config
from ai.outbreak.features import (FEATURE_NAMES, FEATURE_VERSION, DailyWeather, Observation, build_features,
                                  label_window)
from ai.outbreak.schema import OBSERVATIONS, WEATHER_DAILY
from ai.outbreak.validate import default_dataset_root, read_table, validate_dataset


def preprocess(root: Path, config) -> dict:
    root = Path(root)
    report = validate_dataset(root)
    if not report["summary"]["ready_for_preprocessing"]:
        raise SystemExit(f"Validation failed ({report['summary']['errors']} errors); see {root / 'reports' / 'validation_summary.md'}")
    issues: list = []
    obs_rows = read_table(root / "raw" / OBSERVATIONS.file, OBSERVATIONS, issues)
    by_series = defaultdict(list)
    for _, r in obs_rows:
        cell = grid.cell_for(r["latitude"], r["longitude"], config.grid_resolution_deg)
        o = Observation(r["observed_on"], r["is_positive"], r.get("inspected_count") or 1, r.get("positive_count"))
        by_series[(cell.key, r["crop"], r["disease"])].append(o)

    weather_by_cell = defaultdict(dict)
    weather_path = root / "raw" / WEATHER_DAILY.file
    if weather_path.is_file():
        for _, w in read_table(weather_path, WEATHER_DAILY, issues):
            cell = grid.cell_for(w["latitude"], w["longitude"], config.grid_resolution_deg)
            weather_by_cell[cell.key][w["date"]] = DailyWeather(
                w["date"], w.get("temperature_mean_c"), w.get("temperature_min_c"), w.get("temperature_max_c"),
                w.get("relative_humidity_mean_pct"), w.get("rh_hours_ge_90"), w.get("precipitation_mm"))

    rows = []
    for (cell_key, crop, disease), observations in by_series.items():
        cell = grid.cell_from_key(cell_key)
        neighbor_obs = [o for n in grid.neighbors(cell) for o in by_series.get((n.key, crop, disease), [])]
        first, last = min(o.observed_on for o in observations), max(o.observed_on for o in observations)
        as_of = first
        while as_of < last:
            for horizon in config.horizons_days:
                label = label_window(observations, as_of, horizon)
                if label is not None:
                    features = build_features(as_of, horizon, observations, neighbor_obs, weather_by_cell.get(cell_key, {}))
                    rows.append({"area_key": cell_key, "crop": crop, "disease": disease, "as_of": as_of.isoformat(),
                                 "horizon_days": horizon, **features, "label": label})
            as_of += timedelta(config.step_days)

    columns = ["area_key", "crop", "disease", "as_of"] + FEATURE_NAMES + ["label"]
    table = pd.DataFrame(rows, columns=columns).sort_values(["as_of", "area_key", "crop", "disease", "horizon_days"])
    out = root / "processed"
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "training_table.csv", index=False)

    digest = hashlib.sha256(pd.util.hash_pandas_object(table, index=False).values.tobytes()).hexdigest()[:16]
    manifest = {
        "dataset": "outbreak", "dataset_version": digest, "feature_version": FEATURE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "grid_resolution_deg": config.grid_resolution_deg, "horizons_days": config.horizons_days, "step_days": config.step_days,
        "rows": int(len(table)), "positives": int(table["label"].sum()) if len(table) else 0,
        "date_range": [table["as_of"].min(), table["as_of"].max()] if len(table) else None,
        "areas": int(table["area_key"].nunique()) if len(table) else 0,
        "crop_disease": table.groupby(["crop", "disease"])["label"].agg(["count", "sum"]).reset_index()
                             .rename(columns={"count": "rows", "sum": "positives"}).to_dict("records") if len(table) else [],
        "weather_cells": len(weather_by_cell),
    }
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the outbreak training table")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = preprocess(args.dataset, load_config(args.config))
    print(f"dataset_version {manifest['dataset_version']}: {manifest['rows']} rows, {manifest['positives']} positive, "
          f"{manifest['areas']} areas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
