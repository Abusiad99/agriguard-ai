# Disease outbreak prediction and risk map

An area-level map of observed disease cases and a model-based estimate of how likely the
disease is to be found in an area over the next 3, 7 or 14 days. An estimate is not a
confirmed outbreak, and the UI says so.

| Milestone | Status |
|---|---|
| Software (pipeline, API, map UI, migrations, tests) | Complete |
| Dataset integration | Waiting for historical inspection data (with real negatives) in `datasets/outbreak/` |
| Training | Not started. Training refuses to run below minimum data volumes |
| Evaluation on real data | Not done |
| Production readiness | Not claimed |

Without a trained model the map still shows observed cases. Estimates return
`status: "model_unavailable"`, are not stored, and the page shows a *not ready* notice.

## Data sources

1. **App scans**, only when the owner attached a location (`attach_location=true`) and the
   scan was classified confidently. Each scan becomes one inspection of its crop. It is
   positive for its predicted disease. Scans without a location are never used.
   Existing located scans can be added with `python -m app.tools.outbreak_data backfill`.
2. **Imported survey data** (`datasets/outbreak/raw/observations.csv`), loaded with
   `scripts\outbreak.ps1 -Action import`. Rows are `source = "dataset"`. Re-importing
   replaces only the rows from the same dataset version.

Absence of reports is **not** treated as absence of disease. A training label is only
created where inspections happened (`label_window` in `ai/outbreak/features.py`).

## Privacy

- Locations are aggregated to grid cells (`OUTBREAK_GRID_RESOLUTION_DEG`, default 0.25°,
  minimum 0.1°). The API never returns individual coordinates or users.
- App-scan counts in a cell are suppressed unless at least `OUTBREAK_MIN_CONTRIBUTORS`
  (default 3) different users contributed. Suppressed cells are left off the map
  (`hidden_for_privacy` reports how many). On the detail panel the app counts are hidden
  and survey counts still show; a suppressed cell's "latest observation" date is the latest
  survey date only.
- The same rule applies to risk estimates. A prediction's history features (case and
  inspection counts, days since the last case) come from the cell and its 8 neighbours, so
  while any of those cells has app scans from fewer than `OUTBREAK_MIN_CONTRIBUTORS` users,
  `POST /predictions` and `GET /predictions/{id}` return those features as `null`, leave
  them out of `factors`, and add the limitation `history_withheld_for_privacy`. The model
  still uses them, and the stored prediction keeps them; the check is repeated on every read.
- Clicking an empty spot looks up its grid cell. The clicked coordinates are not stored.

## Weather

Daily weather comes from Open-Meteo (no key). It uses the forecast API for the last 92 days
plus up to 16 days ahead, and the archive API for older days. Hourly values are aggregated to
mean, min and max temperature, mean relative humidity, hours with RH ≥ 90 % and precipitation.
A day needs at least 20 hourly values. Missing values stay missing and are never zero.
Results are cached per cell and day (`weather_observations`). Forecast rows are refreshed
after `WEATHER_FORECAST_CACHE_HOURS` (3 h).

## Rule-based suitability (sourced, not a prediction)

`configs/outbreak/suitability_profiles.json` holds published weather rules. Each profile
must name its source. The only profile shipped is the **Hutton criteria** for *potato late
blight* (AHDB): two consecutive days with minimum temperature ≥ 10 °C and at least 6 hours
of RH ≥ 90 %. The result is `met`, `not_met` or `insufficient_weather_data`, and is never
"not met" because data is missing. No rule is invented for other crop/disease pairs.

## Model (`ai/outbreak/`)

- **Features** (`outbreak-features-v1`): cell history (inspections and positives over 7, 30
  and 90 days, positive share, neighbouring cells, the same window last year, days since the
  last case), the last 7 and 14 days of weather, forecast weather for the horizon, season,
  horizon, crop and disease. Missing features stay missing. `data_completeness` reports
  how much was available.
- **Model**: scikit-learn `HistGradientBoostingClassifier` (handles missing values).
- **Splits**: chronological (train → validation → test, by date), never random, with an
  embargo. A row is kept in a split only if its label window `(as_of, as_of + horizon]` ends
  before the next split starts, so no training label is an outcome that validation or test is
  scored on. `metrics.json` → `split_sizes` reports the counts and `purged_for_embargo`.
- **Forecast features in training** are built from observed weather (a perfect-forecast
  assumption, recorded in the model card as `forecast_features_training_source`). Live
  estimates use real forecasts, which are less accurate, so real-world skill can be lower
  than the test metrics.
- **Calibration**: isotonic or sigmoid on validation, only with at least 30 examples per
  class. Otherwise the score is reported as an uncalibrated `risk_score`, not a probability,
  with the limitation `score_not_calibrated`. Validation metrics are computed on the split the
  calibrator was fitted on (`metrics.json` says so). Use the test metrics.
- **Risk levels**: cut-points `[0.25, 0.5, 0.75]` → low, moderate, high, critical.
- **Confidence**: `high` only for a calibrated score with ≥ 90 % completeness and ≥ 10
  inspections in the cell in the last 90 days. `medium` with ≥ 70 % completeness.
  Otherwise `low`.
- **Factors**: permutation importance from validation, with today's value relative to the
  training range. This is global importance, not a per-estimate attribution, and the UI
  says so.
- **Minimums** (`configs/outbreak/default.json`): 200 labeled rows, 30 positives, 30
  negatives, a 365-day span. Below that, training stops with `InsufficientData`.

### When an estimate is refused

The model is never asked to score places or setups it knows nothing about. Zero counts there
mean "nobody looked", not "no disease", and would read as low risk.

| Result | Reason | When |
|---|---|---|
| `model_unavailable` | `not_trained_for_crop_disease` | The crop/disease pair wasn't in the training data |
| `model_unavailable` | `grid_resolution_mismatch` | `OUTBREAK_GRID_RESOLUTION_DEG` differs from the grid the model was trained on. Count features are per cell, so they would change meaning |
| `insufficient_data` | `outside_training_region` | The cell is more than one cell away from the training data's extent (`training_extent` in the model card) |
| `insufficient_data` | `no_local_history` | The cell and its 8 neighbours have fewer than `OUTBREAK_MIN_LOCAL_INSPECTIONS` (default 5) inspections of the crop in the last `OUTBREAK_HISTORY_DAYS` |
| `insufficient_data` | `low_data_completeness` | Fewer features than the model card's `min_completeness` (default 0.5) are available, typically because weather couldn't be fetched |

`insufficient_data` results are stored, with their limitations, so they show in the history.
Runs trained before these fields existed have no extent. For them, `outside_training_region`
is not checked.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action preprocess
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action train
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action evaluate
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action import
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action status
```

Runs go to `artifacts/outbreak/runs/<timestamp>_hgb/` (`model.joblib`, `model_card.json`,
`metrics.json`). Evaluation (`<run>/evaluation/`) reports ROC-AUC, PR-AUC, Brier score and
base rate overall and per crop/disease, plus a reliability (calibration) plot. The backend
switches to a newly promoted model on the next request.

`evaluate` refuses to score a run against a processed dataset version other than the one it
was trained on, because the test split would no longer be the one held out. To do it anyway,
pass `-Extra "--allow-dataset-mismatch"`; `metrics.json` then records `dataset_mismatch: true`.
`train` writes the version it used in the model card.

## API (`/api/v1/outbreak`, login required)

| Method | Path | Notes |
|---|---|---|
| GET | `/readiness` | Model card, data counts, suitability profiles, privacy settings, `can_predict`, limitations |
| GET | `/filters` | Crops, crop/disease pairs (with `model_trained`), horizons |
| GET | `/map` | `crop, disease, date_from, date_to (≤ 3 years), bbox=west,south,east,north, horizon_days, page, page_size` → cells with counts and the freshest stored prediction (≤ 2 days old) |
| GET | `/areas/lookup?lat=&lon=` | Grid cell of a point (`area_id` null if the cell has no data yet) |
| GET | `/areas/{id}` | Counts, weekly trend, weather, suitability, recent predictions. Optional `date_from`/`date_to` (the map's window); otherwise the last `weeks` (26) |
| POST | `/predictions` | `{crop, disease, horizon_days, area_id \| latitude+longitude}` → `ok`, `insufficient_data` or `model_unavailable` |
| GET | `/predictions`, `/predictions/{id}` | The caller's stored predictions |

`POST /predictions` is rate-limited (`RATE_LIMIT_PREDICTION_PER_HOUR`, default 60). Dates
use the UTC calendar day, the same as scan observations.

## Frontend (`/outbreak`)

Crop, disease, observation window and horizon filters. An *Observed cases* layer colored by
positive share and a *Predicted risk* layer. A legend and a privacy note. Clicking a cell
opens counts, the weekly bar chart, the weather table, sourced suitability results, recent
estimates and *Estimate risk*. The result shows level, score type, confidence, completeness,
forecast period, main factors, limitations and model version. The map uses OpenStreetMap
tiles with attribution and loads on demand (a separate chunk).

## Database (migration `0006_outbreak_prediction`)

`geo_areas` (unique grid key), `disease_observations` (`source` in `app_scan|dataset`, unique
per diagnosis), `weather_observations` (unique per cell/day/kind), `outbreak_predictions`
(inputs, factors, limitations and model version stored with every estimate).

## Limitations

- The 0.25° grid is coarse (about 28 km at the equator), and estimates describe a cell, not
  a field.
- App scans are opportunistic: who scans and where is not a survey design. Treat them as
  presence data with bias.
- The model can only learn crop/disease pairs present in the training data. Other pairs
  return `not_trained_for_crop_disease`.
