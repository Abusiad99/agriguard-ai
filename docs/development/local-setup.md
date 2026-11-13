# Developer notes: AI feature settings

Installing and running the app is described in one place:
**[docs/SETUP_AND_RUN.md](../SETUP_AND_RUN.md)**. Datasets and training are in
**[DATASET_SETUP_GUIDE.md](../../DATASET_SETUP_GUIDE.md)**. This page only adds reference
notes for the AI features (localization, plant recovery, outbreak risk, reports).

## What the migrations add

| Migration | Adds |
|---|---|
| `0004_disease_localization` | `diagnoses.image_quality_json`, `diagnosis_segmentations` |
| `0005_plant_recovery` | `tracked_plants`, `tracked_plant_scans`, `treatment_records`, `follow_up_reminders`, `recovery_assessments`, `plant_timeline_events` |
| `0006_outbreak_prediction` | `geo_areas`, `disease_observations`, `weather_observations`, `outbreak_predictions` |
| `0007_agricultural_reports` | `diagnoses.top_predictions_json`, `generated_reports`, `report_shares` |
| `0008_knowledge_references` | `knowledge_references`, `knowledge_reference_claims` (structured sources for the knowledge base) |

All five only add tables and nullable columns. Existing rows are not modified. Diagnoses made
before 0007 have no stored alternatives, and their reports say so. Each has
a `downgrade`, but `migrate.ps1` never runs one implicitly, and downgrading drops the
feature tables and their data.

Back up before migrating a database that holds data (`scripts\backup-db.ps1`, SETUP_AND_RUN
section 3.9).

## Settings (`.env`)

New settings, all optional with the defaults shown in `.env.example`:

| Setting | Default | Purpose |
|---|---|---|
| `OUTBREAK_GRID_RESOLUTION_DEG` | 0.25 | Size of the map's grid cells (≥ 0.1) |
| `OUTBREAK_MIN_CONTRIBUTORS` | 3 | Hide app-scan counts in cells with fewer distinct users |
| `OUTBREAK_MIN_LOCAL_INSPECTIONS` | 5 | Refuse an estimate (`no_local_history`) when the cell and its neighbours have fewer inspections |
| `MEDIA_URL_TTL_SECONDS` | 3600 | Lifetime of signed scan-photo and heatmap links |
| `LEGACY_PUBLIC_MEDIA` | false | `true` re-opens the old public `/storage/scans` and `/storage/heatmaps` paths. Not recommended |
| `REPORT_SHARE_MAX_DAYS` | 30 | Longest allowed lifetime of a report share link |
| `REPORTS_LLM_ENABLED` | true | Let Gemini word report summaries (also needs `GEMINI_API_KEY`); otherwise a template is used |
| `OUTBREAK_HISTORY_DAYS` | 400 | History window for features and trends |
| `WEATHER_ARCHIVE_BASE_URL` | Open-Meteo archive | Daily history older than 92 days |
| `WEATHER_FORECAST_CACHE_HOURS` | 3 | Re-fetch cached forecast days after this |
| `RATE_LIMIT_PREDICTION_PER_HOUR` | 60 | Per-client limit on `POST /outbreak/predictions` |
| `AGRIGUARD_ARTIFACTS_DIR`, `AGRIGUARD_DATASETS_DIR` | `<repo>/artifacts`, `<repo>/datasets` | Move model runs and datasets elsewhere |
| `AI_ARTIFACTS_RUN_DIR` | empty | Pin the classifier to one run folder |

Segmentation PNGs are written under `LOCAL_STORAGE_DIR/segmentations/` and are served only by
the authenticated artifact endpoint. Scan photos and heatmaps are served through signed,
expiring `/api/v1/media/...` links. The old public `/storage/...` paths return 404 unless
`LEGACY_PUBLIC_MEDIA=true`. Report PDFs are cached under `LOCAL_STORAGE_DIR/reports/generated/`,
which is never served directly.

## Pages and network access

New pages: **My plants** (`/plants`), **Outbreak risk** (`/outbreak`), **Reports** (`/reports`)
and **Admin → AI models** (`/admin/models`). The diagnosis page gains the localization card, the photo-quality notice
and *Track this plant*. On phones, Profile moves to the avatar in the top bar.

The outbreak map loads OpenStreetMap tiles in the browser, and risk estimates call
Open-Meteo from the backend. Both need internet access. The rest works offline.

## Without trained models

Out of the box no segmentation or outbreak model exists, and that is the expected state:

- scans succeed; the localization card says it is waiting for a trained model;
- tracked plants with two or more scans are *Inconclusive*, with the reason shown;
- the outbreak map shows observed cases (if any). Estimates return *model not ready*.

To prepare data and train the models, follow
[DATASET_SETUP_GUIDE.md](../../DATASET_SETUP_GUIDE.md).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Localization says "could not be loaded" | Check `logs\backend-dev.err.log`. The model run may be incomplete; `scripts\segmentation.ps1 -Action status` shows readiness |
| Outbreak estimate "insufficient data" | The limitations say which: weather could not be fetched (no internet), too few inspections near the cell (`no_local_history`), or the cell is outside the training region. See the outbreak feature page |
| Old photo links (`/storage/scans/...`) return 404 | Expected: photos are private now, and the app uses signed links. See `LEGACY_PUBLIC_MEDIA` |
| Arabic PDF shows boxes or reversed letters | `arabic-reshaper` / `python-bidi` missing: re-run `install-backend.ps1` |
| `Port 5173 is already in use` right after `stop-dev.ps1` | Windows can keep the socket briefly; wait or pass `-Port 5174` |
| pip path-length errors | Set `$env:AGRIGUARD_VENV` to a short path |
