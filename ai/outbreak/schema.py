"""
Outbreak dataset schemas — the single definition used by the validator, the
preprocessing step and docs/datasets/outbreak-dataset-schema.md.

    python -m ai.outbreak.schema   # (re)writes datasets/outbreak/schemas/*.schema.json and samples/*.header.csv
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ai.config import CONFIG


@dataclass
class Column:
    name: str
    type: str                  # date | float | int | bool01 | string
    required: bool
    description: str
    unit: Optional[str] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    allowed: Optional[List[str]] = None
    missing: str = "row rejected"  # what happens when the value is empty


@dataclass
class TableSchema:
    file: str
    description: str
    columns: List[Column] = field(default_factory=list)
    required: bool = True

    @property
    def required_columns(self) -> List[str]:
        return [c.name for c in self.columns if c.required]

    def column(self, name: str) -> Optional[Column]:
        return next((c for c in self.columns if c.name == name), None)


OBSERVATIONS = TableSchema(
    file="observations.csv",
    description="Field inspections: one row per crop/disease check at a place and date. Rows with is_positive=0 "
                "are real negative inspections — do not fabricate negatives for places nobody inspected.",
    columns=[
        Column("observed_on", "date", True, "Inspection date (YYYY-MM-DD)"),
        Column("latitude", "float", True, "WGS84 latitude of the field (aggregated to a grid cell; never shown)", "degrees", -90, 90),
        Column("longitude", "float", True, "WGS84 longitude of the field", "degrees", -180, 180),
        Column("crop", "string", True, "Crop, using AgriGuard plant names (e.g. tomato, potato, date_palm)"),
        Column("disease", "string", True, "Disease checked for, using AgriGuard condition names (e.g. late_blight)"),
        Column("is_positive", "bool01", True, "1 if the disease was found, 0 if inspected and not found"),
        Column("inspected_count", "int", False, "Plants/fields inspected in this record", None, 1, None, missing="treated as 1"),
        Column("positive_count", "int", False, "How many of them were affected", None, 0, None, missing="1 if is_positive else 0"),
        Column("observation_id", "string", False, "Your identifier (used to report duplicates)", missing="ignored"),
        Column("source", "string", False, "Organisation / survey the record comes from", missing="ignored"),
        Column("location_precision_m", "float", False, "Uncertainty of the coordinates", "meters", 0, None, missing="ignored"),
    ],
)

WEATHER_DAILY = TableSchema(
    file="weather_daily.csv",
    description="Daily weather near the observation locations. Optional: missing weather lowers data completeness; "
                "it is never treated as zero.",
    required=False,
    columns=[
        Column("date", "date", True, "Day (YYYY-MM-DD, local)"),
        Column("latitude", "float", True, "Station / grid-point latitude", "degrees", -90, 90),
        Column("longitude", "float", True, "Station / grid-point longitude", "degrees", -180, 180),
        Column("temperature_mean_c", "float", False, "Daily mean air temperature", "degC", -60, 60, "feature left missing"),
        Column("temperature_min_c", "float", False, "Daily minimum air temperature", "degC", -70, 60, "feature left missing"),
        Column("temperature_max_c", "float", False, "Daily maximum air temperature", "degC", -60, 70, "feature left missing"),
        Column("relative_humidity_mean_pct", "float", False, "Daily mean relative humidity", "%", 0, 100, "feature left missing"),
        Column("rh_hours_ge_90", "float", False, "Hours with relative humidity >= 90 %", "hours", 0, 24, "feature left missing"),
        Column("precipitation_mm", "float", False, "Daily precipitation total", "mm", 0, 1000, "feature left missing"),
        Column("source", "string", False, "Data provider", missing="ignored"),
    ],
)

TABLES = [OBSERVATIONS, WEATHER_DAILY]


def write_schema_files() -> None:
    root = CONFIG.paths.datasets_dir / "outbreak"
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "samples").mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        stem = table.file.rsplit(".", 1)[0]
        (root / "schemas" / f"{stem}.schema.json").write_text(json.dumps(asdict(table), indent=2) + "\n", encoding="utf-8")
        (root / "samples" / f"{stem}.header.csv").write_text(",".join(c.name for c in table.columns) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_schema_files()
    sys.exit(0)
