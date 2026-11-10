"""
Longitudinal recovery dataset (datasets/recovery) — validation and loading.

    python -m ai.recovery.dataset validate [--dataset datasets/recovery]

raw/plants/plants.csv          plant_id, crop[, species, region, notes]
raw/scans/scans.csv            scan_id, plant_id, scan_date, image_file[, disease_label, severity_label,
                               affected_area_pct, mask_file, treatment_stage]   (images in raw/scans/)
raw/treatments/treatments.csv  treatment_id, plant_id, applied_on, category, name[, notes]
raw/annotations/recovery_labels.csv
                               plant_id, from_scan_id, to_scan_id, status[, annotator_id, notes]
No personal information is needed: ids are opaque, `region` is optional and coarse.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List

from ai.config import CONFIG

STATUS_LABELS = ("improving", "stable", "worsening", "inconclusive")
SEVERITY_LABELS = ("none", "mild", "moderate", "severe")
STAGES = ("before_treatment", "during_treatment", "after_treatment", "unknown")
CATEGORIES = ("organic", "chemical", "biological", "cultural", "other")
FILES = {
    "plants": ("plants/plants.csv", ["plant_id", "crop"]),
    "scans": ("scans/scans.csv", ["scan_id", "plant_id", "scan_date", "image_file"]),
    "treatments": ("treatments/treatments.csv", ["treatment_id", "plant_id", "applied_on", "category", "name"]),
    "labels": ("annotations/recovery_labels.csv", ["plant_id", "from_scan_id", "to_scan_id", "status"]),
}


def default_dataset_root() -> Path:
    return CONFIG.paths.datasets_dir / "recovery"


def _read(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def load(root: Path) -> Dict[str, List[Dict[str, str]]]:
    return {name: _read(root / "raw" / rel) for name, (rel, _) in FILES.items() if (root / "raw" / rel).is_file()}


def validate(root: Path, write_reports: bool = True) -> dict:
    root = Path(root)
    issues: List[dict] = []

    def add(severity, code, file, line, message):
        issues.append({"severity": severity, "code": code, "file": file, "line": line, "message": message})

    tables = {}
    for name, (rel, required) in FILES.items():
        path = root / "raw" / rel
        if not path.is_file():
            if name in ("plants", "scans"):
                add("error", "missing_file", rel, None, "required file is missing")
            else:
                add("warning", "missing_file", rel, None, "optional file is missing")
            continue
        rows = _read(path)
        header = rows[0].keys() if rows else []
        missing = [c for c in required if c not in header]
        if rows and missing:
            add("error", "missing_columns", rel, 1, f"required columns missing: {missing}")
            continue
        tables[name] = rows

    plants = {r["plant_id"]: r for r in tables.get("plants", [])}
    scans: Dict[str, dict] = {}
    for line, r in enumerate(tables.get("scans", []), start=2):
        rel = FILES["scans"][0]
        if r["scan_id"] in scans:
            add("error", "duplicate_id", rel, line, f"scan_id {r['scan_id']} repeated")
        if r["plant_id"] not in plants:
            add("error", "unknown_plant", rel, line, f"plant_id {r['plant_id']} not in plants.csv")
        try:
            r["_date"] = date.fromisoformat(r["scan_date"])
        except ValueError:
            add("error", "invalid_value", rel, line, f"scan_date {r['scan_date']!r} is not YYYY-MM-DD")
            continue
        if not (root / "raw" / "scans" / r["image_file"]).is_file():
            add("error", "missing_image", rel, line, f"raw/scans/{r['image_file']} not found")
        if r.get("mask_file") and not (root / "raw" / "annotations" / r["mask_file"]).is_file():
            add("error", "missing_mask", rel, line, f"raw/annotations/{r['mask_file']} not found")
        if r.get("severity_label") and r["severity_label"] not in SEVERITY_LABELS:
            add("error", "invalid_value", rel, line, f"severity_label must be one of {SEVERITY_LABELS}")
        if r.get("treatment_stage") and r["treatment_stage"] not in STAGES:
            add("error", "invalid_value", rel, line, f"treatment_stage must be one of {STAGES}")
        if r.get("affected_area_pct"):
            try:
                if not 0 <= float(r["affected_area_pct"]) <= 100:
                    raise ValueError
            except ValueError:
                add("error", "invalid_value", rel, line, "affected_area_pct must be a number 0-100")
        scans[r["scan_id"]] = r

    for line, r in enumerate(tables.get("treatments", []), start=2):
        rel = FILES["treatments"][0]
        if r["plant_id"] not in plants:
            add("error", "unknown_plant", rel, line, f"plant_id {r['plant_id']} not in plants.csv")
        if r["category"] not in CATEGORIES:
            add("error", "invalid_value", rel, line, f"category must be one of {CATEGORIES}")
        try:
            date.fromisoformat(r["applied_on"])
        except ValueError:
            add("error", "invalid_value", rel, line, f"applied_on {r['applied_on']!r} is not YYYY-MM-DD")

    for line, r in enumerate(tables.get("labels", []), start=2):
        rel = FILES["labels"][0]
        if r["status"] not in STATUS_LABELS:
            add("error", "invalid_value", rel, line, f"status must be one of {STATUS_LABELS}")
        a, b = scans.get(r["from_scan_id"]), scans.get(r["to_scan_id"])
        if a is None or b is None:
            add("error", "unknown_scan", rel, line, "from_scan_id / to_scan_id not in scans.csv")
            continue
        if a["plant_id"] != r["plant_id"] or b["plant_id"] != r["plant_id"]:
            add("error", "plant_mismatch", rel, line, "both scans must belong to plant_id")
        if "_date" in a and "_date" in b and a["_date"] >= b["_date"]:
            add("error", "not_chronological", rel, line, "from_scan must be dated before to_scan")

    per_plant: Dict[str, int] = {}
    for s in scans.values():
        per_plant[s["plant_id"]] = per_plant.get(s["plant_id"], 0) + 1
    errors = sum(1 for i in issues if i["severity"] == "error")
    result = {"dataset_root": str(root), "generated_at": datetime.now(timezone.utc).isoformat(),
              "summary": {"errors": errors, "warnings": len(issues) - errors, "plants": len(plants), "scans": len(scans),
                          "plants_with_2plus_scans": sum(1 for n in per_plant.values() if n >= 2),
                          "labeled_pairs": len(tables.get("labels", [])), "ready": errors == 0 and bool(scans)},
              "issues": issues}
    if write_reports:
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "reports" / "validation_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the recovery dataset")
    parser.add_argument("action", choices=["validate"])
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    args = parser.parse_args(argv)
    result = validate(args.dataset)
    print(json.dumps(result["summary"], indent=2))
    return 0 if result["summary"]["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
