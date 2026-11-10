"""
Outbreak dataset validator.

    python -m ai.outbreak.validate [--dataset datasets/outbreak]

Checks raw/observations.csv (required) and raw/weather_daily.csv (optional) against
ai/outbreak/schema.py and writes reports/validation_report.json + validation_summary.md.
Every problem is reported with its file and line; nothing is changed or dropped.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai.config import CONFIG
from ai.outbreak.schema import OBSERVATIONS, TABLES, WEATHER_DAILY, TableSchema

MAX_ISSUES_PER_CODE = 200


def default_dataset_root() -> Path:
    return CONFIG.paths.datasets_dir / "outbreak"


def parse_value(raw: str, kind: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "float":
        return float(raw)
    if kind == "int":
        value = float(raw)
        if not value.is_integer():
            raise ValueError("not an integer")
        return int(value)
    if kind == "bool01":
        if raw not in ("0", "1"):
            raise ValueError("must be 0 or 1")
        return raw == "1"
    return raw


def read_table(path: Path, schema: TableSchema, issues: List[dict]) -> List[Tuple[int, Dict]]:
    """Parsed rows (line number, values) that pass every column rule; every failure
    is appended to `issues`."""
    rows: List[Tuple[int, Dict]] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in schema.required_columns if c not in header]
        if missing:
            issues.append({"severity": "error", "code": "missing_columns", "file": schema.file, "line": 1,
                           "message": f"required columns missing: {missing}"})
            return rows
        unknown = [h for h in header if schema.column(h) is None]
        if unknown:
            issues.append({"severity": "warning", "code": "unknown_columns", "file": schema.file, "line": 1,
                           "message": f"columns not in the schema are ignored: {unknown}"})
        for line_no, raw in enumerate(reader, start=2):
            values, ok = {}, True
            for column in schema.columns:
                try:
                    value = parse_value(raw.get(column.name, ""), column.type)
                except ValueError as exc:
                    issues.append({"severity": "error", "code": "invalid_value", "file": schema.file, "line": line_no,
                                   "message": f"{column.name}={raw.get(column.name)!r}: {exc}"})
                    ok = False
                    continue
                if value is None and column.required:
                    issues.append({"severity": "error", "code": "missing_value", "file": schema.file, "line": line_no,
                                   "message": f"{column.name} is required"})
                    ok = False
                elif value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
                    if (column.minimum is not None and value < column.minimum) or (column.maximum is not None and value > column.maximum):
                        issues.append({"severity": "error", "code": "out_of_range", "file": schema.file, "line": line_no,
                                       "message": f"{column.name}={value} outside [{column.minimum}, {column.maximum}]"})
                        ok = False
                values[column.name] = value
            if ok:
                rows.append((line_no, values))
    return rows


def validate_dataset(root: Path, write_reports: bool = True) -> dict:
    root = Path(root)
    raw = root / "raw"
    issues: List[dict] = []
    stats: Dict = {}
    obs_rows: List[Tuple[int, Dict]] = []
    today = date.today()

    obs_path = raw / OBSERVATIONS.file
    if not obs_path.is_file():
        issues.append({"severity": "error", "code": "missing_file", "file": OBSERVATIONS.file, "line": None,
                       "message": "raw/observations.csv is required (see datasets/outbreak/README.md)"})
    else:
        obs_rows = read_table(obs_path, OBSERVATIONS, issues)
        seen: Dict[tuple, int] = {}
        ids: Dict[str, int] = {}
        for line, row in obs_rows:
            if row["observed_on"] > today:
                issues.append({"severity": "error", "code": "future_date", "file": OBSERVATIONS.file, "line": line,
                               "message": f"observed_on {row['observed_on']} is in the future"})
            if row.get("positive_count") is not None:
                inspected = row.get("inspected_count") or 1
                if row["positive_count"] > inspected:
                    issues.append({"severity": "error", "code": "inconsistent_counts", "file": OBSERVATIONS.file, "line": line,
                                   "message": "positive_count is larger than inspected_count"})
                if (row["positive_count"] > 0) != row["is_positive"]:
                    issues.append({"severity": "error", "code": "inconsistent_counts", "file": OBSERVATIONS.file, "line": line,
                                   "message": "is_positive disagrees with positive_count"})
            key = tuple(row.get(k) for k in ("observed_on", "latitude", "longitude", "crop", "disease", "is_positive"))
            if key in seen:
                issues.append({"severity": "warning", "code": "duplicate_row", "file": OBSERVATIONS.file, "line": line,
                               "message": f"same values as line {seen[key]}"})
            seen.setdefault(key, line)
            if row.get("observation_id"):
                if row["observation_id"] in ids:
                    issues.append({"severity": "error", "code": "duplicate_id", "file": OBSERVATIONS.file, "line": line,
                                   "message": f"observation_id already used on line {ids[row['observation_id']]}"})
                ids.setdefault(row["observation_id"], line)
        dates = [r["observed_on"] for _, r in obs_rows]
        pairs = Counter((r["crop"], r["disease"]) for _, r in obs_rows)
        positives = Counter((r["crop"], r["disease"]) for _, r in obs_rows if r["is_positive"])
        stats["observations"] = {
            "valid_rows": len(obs_rows),
            "date_range": [min(dates).isoformat(), max(dates).isoformat()] if dates else None,
            "span_days": (max(dates) - min(dates)).days if dates else 0,
            "crop_disease": [{"crop": c, "disease": d, "rows": n, "positives": positives[(c, d)]} for (c, d), n in pairs.most_common()],
            "positives": sum(1 for _, r in obs_rows if r["is_positive"]),
        }

    weather_path = raw / WEATHER_DAILY.file
    if weather_path.is_file():
        w_rows = read_table(weather_path, WEATHER_DAILY, issues)
        stats["weather"] = {"valid_rows": len(w_rows),
                            "coverage": {c.name: sum(1 for _, r in w_rows if r.get(c.name) is not None)
                                         for c in WEATHER_DAILY.columns if c.unit}}
    else:
        issues.append({"severity": "warning", "code": "no_weather", "file": WEATHER_DAILY.file, "line": None,
                       "message": "no weather_daily.csv: weather features will be missing (lower data completeness)"})

    capped, per_code = [], Counter()
    for issue in issues:
        per_code[issue["code"]] += 1
        if per_code[issue["code"]] <= MAX_ISSUES_PER_CODE:
            capped.append(issue)
    errors = sum(1 for i in issues if i["severity"] == "error")
    result = {
        "dataset_root": str(root), "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"errors": errors, "warnings": len(issues) - errors, "issue_counts": dict(per_code),
                    "ready_for_preprocessing": errors == 0 and bool(obs_rows)},
        "statistics": stats, "issues": capped,
    }
    if write_reports:
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "reports" / "validation_report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (root / "reports" / "validation_summary.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _markdown(result: dict) -> str:
    s, st = result["summary"], result["statistics"]
    lines = ["# Outbreak dataset validation", "", f"- Generated: {result['generated_at']}",
             f"- Errors: {s['errors']}, warnings: {s['warnings']}",
             f"- **Ready for preprocessing: {'yes' if s['ready_for_preprocessing'] else 'no'}**", ""]
    obs: Optional[dict] = st.get("observations")
    if obs:
        lines += [f"- Valid observation rows: {obs['valid_rows']} ({obs['positives']} positive)",
                  f"- Date range: {obs['date_range']} ({obs['span_days']} days)", "",
                  "| Crop | Disease | Rows | Positives |", "|---|---|---|---|"]
        lines += [f"| {r['crop']} | {r['disease']} | {r['rows']} | {r['positives']} |" for r in obs["crop_disease"]]
        lines.append("")
    if result["issues"]:
        lines += ["## Issues", ""]
        lines += [f"- {i['severity'].upper()} `{i['file']}`" + (f" line {i['line']}" if i["line"] else "")
                  + f" ({i['code']}): {i['message']}" for i in result["issues"][:300]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate the outbreak dataset")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    args = parser.parse_args(argv)
    result = validate_dataset(args.dataset)
    print(f"{result['summary']['errors']} errors, {result['summary']['warnings']} warnings -> "
          f"{args.dataset / 'reports' / 'validation_summary.md'}")
    return 0 if result["summary"]["ready_for_preprocessing"] else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["validate_dataset", "read_table", "parse_value", "TABLES"]
