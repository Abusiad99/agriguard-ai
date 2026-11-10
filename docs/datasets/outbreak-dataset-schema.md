# Outbreak dataset schema

Historical field inspections, plus optional daily weather, used to train and evaluate the
outbreak risk model and to fill the risk map. The column definitions live in one place,
`ai/outbreak/schema.py`. `python -m ai.outbreak.schema` regenerates
`datasets/outbreak/schemas/*.schema.json` and `samples/*.header.csv` from it.

## `raw/observations.csv` (required)

One row per crop/disease inspection at a place and date.

| Column | Type | Required | Meaning | If empty |
|---|---|---|---|---|
| `observed_on` | date `YYYY-MM-DD` | yes | Inspection date (not in the future) | row rejected |
| `latitude` | float, −90…90 | yes | WGS84 latitude of the field. Aggregated to a grid cell, never shown | row rejected |
| `longitude` | float, −180…180 | yes | WGS84 longitude | row rejected |
| `crop` | string | yes | AgriGuard plant name, for example `tomato`, `potato` | row rejected |
| `disease` | string | yes | AgriGuard condition name, for example `late_blight` | row rejected |
| `is_positive` | `0`/`1` | yes | 1 = disease found, 0 = **inspected and not found** | row rejected |
| `inspected_count` | int ≥ 1 | no | Plants or fields inspected in this record | treated as 1 |
| `positive_count` | int ≥ 0 | no | How many of them were affected (≤ `inspected_count`, consistent with `is_positive`) | 1 if positive, else 0 |
| `observation_id` | string | no | Your id, used to report duplicates | ignored |
| `source` | string | no | Organisation or survey | ignored |
| `location_precision_m` | float ≥ 0 | no | Coordinate uncertainty in metres | ignored |

## `raw/weather_daily.csv` (optional)

| Column | Type | Unit / range | If empty |
|---|---|---|---|
| `date` | date | local day | row rejected |
| `latitude`, `longitude` | float | degrees | row rejected |
| `temperature_mean_c`, `temperature_min_c`, `temperature_max_c` | float | °C | feature left missing |
| `relative_humidity_mean_pct` | float | 0–100 % | feature left missing |
| `rh_hours_ge_90` | float | 0–24 h | feature left missing |
| `precipitation_mm` | float | 0–1000 mm | feature left missing |
| `source` | string | | ignored |

Missing weather lowers *data completeness*. It is never replaced by zero. Without this file,
training uses history and season features only (validation warns `no_weather`).

## What the data must and must not contain

- **Real negatives.** `is_positive=0` rows are inspections where the disease was looked for
  and not found. Never add negatives for places nobody inspected. The pipeline treats "no
  inspection" as unknown, and labels are only built where inspections exist.
- **Consistent names.** Use the same `crop` and `disease` spellings everywhere. The model can
  only predict pairs it was trained on.
- **No personal data.** No farmer names, phone numbers or exact addresses. Coordinates are
  snapped to grid cells on import.
- **Volume.** By default training requires at least 200 labeled rows, 30 positives, 30
  negatives and 365 days of history (`configs/outbreak/default.json`). These are minimums
  for the code to run, not a guarantee of a useful model.

## Validation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action validate
```

| Errors | Warnings |
|---|---|
| `missing_file`, `missing_columns`, `missing_value`, `invalid_value`, `out_of_range`, `future_date`, `inconsistent_counts`, `duplicate_id` | `unknown_columns`, `duplicate_row`, `no_weather` |

The report (`reports/validation_report.json`, `validation_summary.md`) includes the date
span, positives, and rows per crop/disease.

## Preprocessing and training

`preprocess` builds `processed/training_table.csv`: one row per grid cell, crop/disease, as-of
date (weekly steps) and horizon (3, 7, 14 days). Each row has the features from
`ai/outbreak/features.py` and a label from inspections in the following window.
`train` splits chronologically and refuses below the minimums. See
[../features/outbreak-prediction.md](../features/outbreak-prediction.md).

## Loading into the app (risk map)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action import
```

This inserts every valid row as a `dataset` observation in its grid cell. Re-importing the same
dataset version replaces its earlier rows. Scan data and other imports are untouched.
