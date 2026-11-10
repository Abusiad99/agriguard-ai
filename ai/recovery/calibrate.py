"""
Calibrate the recovery rules against labeled longitudinal data.

    python -m ai.recovery.calibrate [--dataset datasets/recovery]

Uses labeled pairs (annotations/recovery_labels.csv) whose two scans both have an
annotated affected_area_pct, runs the rules engine for a range of `stable_band_pct`
values, and writes reports/calibration_report.json with accuracy and a confusion
matrix per value. It recommends a value but never edits configs/recovery/rules.json —
review the report and change the config yourself.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ai.recovery.dataset import default_dataset_root, load, validate
from ai.recovery.engine import RecoveryRules, ScanSnapshot, assess

BANDS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15]


def calibrate(root: Path) -> dict:
    report = validate(root, write_reports=False)
    if report["summary"]["errors"]:
        raise SystemExit("Fix validation errors first (python -m ai.recovery.dataset validate).")
    tables = load(Path(root))
    scans = {s["scan_id"]: s for s in tables.get("scans", [])}
    pairs = []
    for label in tables.get("labels", []):
        a, b = scans[label["from_scan_id"]], scans[label["to_scan_id"]]
        if a.get("affected_area_pct") and b.get("affected_area_pct"):
            pairs.append((label["status"], [
                ScanSnapshot(a["scan_id"], datetime.fromisoformat(a["scan_date"]), area_pct=float(a["affected_area_pct"]),
                             area_model="annotation"),
                ScanSnapshot(b["scan_id"], datetime.fromisoformat(b["scan_date"]), area_pct=float(b["affected_area_pct"]),
                             area_model="annotation")]))
    if not pairs:
        raise SystemExit("No labeled pairs with annotated affected_area_pct on both scans.")
    results = []
    for band in BANDS:
        rules = RecoveryRules(stable_band_pct=band)
        confusion = Counter((truth, assess(snaps, rules).status) for truth, snaps in pairs)
        correct = sum(n for (truth, pred), n in confusion.items() if truth == pred)
        results.append({"stable_band_pct": band, "accuracy": round(correct / len(pairs), 4),
                        "confusion": [{"label": t, "predicted": p, "count": n} for (t, p), n in sorted(confusion.items())]})
    # Several bands often score the same on small label sets. Recommend the middle of the
    # tied range rather than its smallest value: the narrowest band calls measurement
    # noise "improving" or "worsening".
    best_accuracy = max(r["accuracy"] for r in results)
    tied = [r["stable_band_pct"] for r in results if r["accuracy"] == best_accuracy]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "pairs": len(pairs), "results": results,
           "best_accuracy": best_accuracy, "tied_best_bands": tied,
           "recommended_stable_band_pct": tied[len(tied) // 2],
           "note": "Recommendation only; configs/recovery/rules.json is not modified."}
    (Path(root) / "reports").mkdir(parents=True, exist_ok=True)
    (Path(root) / "reports" / "calibration_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate recovery assessment thresholds")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    args = parser.parse_args(argv)
    out = calibrate(args.dataset)
    print(f"{out['pairs']} labeled pairs; recommended stable_band_pct = {out['recommended_stable_band_pct']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
