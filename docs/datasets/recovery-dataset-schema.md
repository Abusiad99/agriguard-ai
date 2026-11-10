# Recovery dataset schema (longitudinal monitoring)

Repeated photos of the same plants over time. This data is used to **calibrate and check**
the recovery rules (`ai/recovery/engine.py`). It does not train a neural network. All files
are UTF-8 CSV with a header row. Templates are in `datasets/recovery/samples/`, and the JSON
schema is in `datasets/recovery/schemas/recovery.schema.json`.

## `raw/plants/plants.csv`

| Column | Required | Notes |
|---|---|---|
| `plant_id` | yes | Opaque id, unique |
| `crop` | yes | AgriGuard plant name |
| `species`, `region`, `notes` | no | Keep `region` coarse (district or country). No personal data |

## `raw/scans/scans.csv` (images in `raw/scans/`)

| Column | Required | Notes |
|---|---|---|
| `scan_id` | yes | Unique |
| `plant_id` | yes | Must exist in `plants.csv` |
| `scan_date` | yes | ISO date or date-time |
| `image_file` | yes | Path relative to `raw/scans/`; must exist |
| `disease_label` | no | AgriGuard condition name, or `healthy` |
| `severity_label` | no | `none`, `mild`, `moderate`, `severe` |
| `affected_area_pct` | no | 0–100, **measured from an annotation mask**. Calibration uses this |
| `mask_file` | no | Path relative to `raw/annotations/` |
| `treatment_stage` | no | `before_treatment`, `during_treatment`, `after_treatment`, `unknown` |

## `raw/treatments/treatments.csv`

| Column | Required | Notes |
|---|---|---|
| `treatment_id`, `plant_id`, `applied_on`, `category`, `name` | yes | `category`: `organic`, `chemical`, `biological`, `cultural`, `other` |
| `notes` | no | Record what was applied. Do not use this file to encode recommendations |

## `raw/annotations/recovery_labels.csv`

Expert judgements on pairs of scans of the same plant.

| Column | Required | Notes |
|---|---|---|
| `plant_id`, `from_scan_id`, `to_scan_id` | yes | Both scans belong to `plant_id`, and `from` is earlier than `to` |
| `status` | yes | `improving`, `stable`, `worsening`, `inconclusive` |
| `annotator_id`, `notes` | no | Opaque annotator id |

**How to judge the status**: compare visible symptoms on comparable photos (same leaves,
similar angle and light). Use `inconclusive` when photos are not comparable. Do not use
`improving` just because a treatment was applied. Two annotators per pair and an
agreement check are recommended.

## Validation and calibration

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action calibrate
```

Validation errors: `missing_file` (required tables), `missing_columns`, `duplicate_id`,
`invalid_value`, `unknown_plant`, `unknown_scan`, `plant_mismatch`, `not_chronological`,
`missing_image`, `missing_mask`. A missing optional table is a warning.

Calibration takes the labeled pairs where both scans have `affected_area_pct`. It runs the
rules for `stable_band_pct` values 1–15 and writes `reports/calibration_report.json` with
accuracy and a confusion matrix for each value, plus a recommended value (the median of tied
best values, listed in `tied_best_bands`). It **does not** change
`configs/recovery/rules.json`. Review the report, change the config yourself if justified,
and bump `method_version`.
