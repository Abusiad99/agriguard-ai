# Outbreak dataset (disease risk)

Historical field inspections (and optionally daily weather) used to train the outbreak
risk model. Full schema: [docs/datasets/outbreak-dataset-schema.md](../../docs/datasets/outbreak-dataset-schema.md).

```
raw/
  observations.csv    REQUIRED — one row per crop/disease inspection (see schemas/observations.schema.json)
  weather_daily.csv   optional — daily weather near the fields (see schemas/weather_daily.schema.json)
interim/              scratch space for your own conversions
processed/            training_table.csv (written by preprocessing)
manifests/            dataset_manifest.json (written by preprocessing)
schemas/              JSON column definitions (generated from ai/outbreak/schema.py)
reports/              validation_report.json, validation_summary.md
samples/              CSV header templates
```

Key rules:
- Include **negative inspections** (`is_positive=0`) — places that were checked and were
  clean. Never invent negatives for places nobody inspected: the pipeline treats "not
  inspected" as unknown, not as healthy.
- `crop` / `disease` use AgriGuard names (`tomato`, `late_blight`, ...).
- Coordinates are aggregated to grid cells (0.25 deg by default) and never shown.
- Training needs at least 200 labeled rows, 30 positives, 30 negatives and a year of
  history by default (`configs/outbreak/default.json`).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action preprocess
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action train
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action evaluate
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action import   # load observations into the app database for the map
```
