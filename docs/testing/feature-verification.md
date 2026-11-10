# Verifying the AI features and reports

How the localization, plant recovery, outbreak and report features are tested, and how to
check them by hand. Passing tests show the **software** works. They say nothing about model
quality on real data, and they are not evidence of production readiness.

## Automated tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1                      # SQLite + frontend lint/typecheck/test/build
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -PostgresUrl postgresql+psycopg2://agriguard:agriguard@127.0.0.1:5432/agriguard_test
```

| File | Covers |
|---|---|
| `backend/tests/unit/test_segmentation_pipeline.py` | Class mapping checks; mask, COCO and YOLO adapters; every validation code; grouped and near-duplicate-aware splits; nearest-neighbour mask resizing; metrics and losses; a real train → evaluate → infer round trip on generated shapes; area rules (no % without a leaf class); EXIF-rotated photos validated and used upright, aligned with their masks |
| `backend/tests/unit/test_outbreak_pipeline.py` | Grid cells; features with missing data; labels never invented where nobody inspected; chronological splits with an embargo (no label window crosses into a later split); minimum-data refusal; Hutton rule (never "not met" on missing weather); training on generated data learns the planted humidity signal |
| `backend/tests/unit/test_recovery_engine.py` | Every status and limitation, incompatible model versions, quality exclusion, a label change alone is never "improving"; calibration recommends the median of tied band values |
| `backend/tests/unit/test_scan_service.py` | (among others) an EXIF-rotated upload is saved upright before diagnosis |
| `backend/tests/unit/test_ai_registry_quality_weather.py` | Readiness states, pinned classifier run, image-quality checks, hourly→daily weather aggregation, classification scanner ignores feature folders |
| `backend/tests/integration/test_localization_api.py` | `/models` lists every task without paths; a scan without a model still diagnoses; with a generated model: area basis, artifacts 200 for the owner, 403 for another user, 401 anonymous, and not reachable under `/storage`; a segmentation failure does not fail the scan |
| `backend/tests/integration/test_tracked_plants_api.py` | Ownership on every route (404 for others), linking, follow-up scans, treatments are user-recorded, reminders, timeline, comparison, honest assessment, admin viewer sees no private plant |
| `backend/tests/integration/test_outbreak_api.py` | k-anonymity suppression, no coordinates in responses, unlocated scans never used, map window applied to the area panel, `model_unavailable` not stored, prediction with a generated model and mocked weather; no risk level without local history or outside the training region; a grid-size mismatch is refused |
| `backend/tests/integration/test_private_media.py` | Photo and heatmap URLs are signed and work without an auth header; old `/storage/scans` and `/storage/heatmaps` paths are closed; tampered, expired or unsigned links are refused; other users never receive a URL |
| `backend/tests/integration/test_reports_api.py` | Every report value has a source and predictions stay predictions; versions, regenerate and archive; Arabic report and PDFs (English and Arabic); other users get 404; share create/list/revoke, public view without internal ids, expired and invalid links; plant report honest without measurements; area report separates observations from estimates |
| `backend/tests/unit/test_report_v2.py` | Report schema v2 from SYNTHETIC evidence, numbers checked exactly: gap to the next class and close-call rule, per-class test metrics, segmentation findings (no share without a valid denominator), alternatives with knowledge-base symptoms, visual panels and history, context-aware recommendations with sources (confirmation, spraying wind/rain limits, label change, recent treatment), healthy predictions get no disease actions; recovery comparability, measured changes and rates, treatment markers, before/after measurements, follow-up gaps; regional risk-level arithmetic, calibration and test-metric statements, factors, neighbour comparison, coverage and inspection priorities; catalog validity, citation numbering, English/Arabic placeholder parity; validation rejects unsourced or unlabelled content; English and Arabic PDFs render every chapter |
| `backend/tests/integration/test_references_api.py` | References API: only agronomists/admins write, URL uniqueness and validation, claims only on existing diseases/treatments, deactivation keeps rows, audit log; reports cite knowledge-base references on the disease and treatment, list them as sources, and keep them in shared copies |
| `backend/tests/unit/test_report_narrative.py` | A grounded LLM summary is accepted; unsupported numbers, doses, references, certainty words, uncited or unknown fact ids and bad JSON fall back to the template; Arabic digits are checked; negated certainty ("not confirmed") is allowed; content validation rejects unsourced values |
| `backend/tests/integration/test_migrations_postgres.py` | 0004–0008 upgrade and downgrade round trip on PostgreSQL, constraints present (including reference URL, source type and claim subject checks) |
| `frontend/src/lib/aiFeatureUi.test.ts` | Template formatting, risk and recovery colours and tones, overlay class filtering, line-chart geometry |
| `backend/tests/unit/test_weather_guidance.py` | Spraying-conditions verdicts (all five), missing / invalid / conflicting readings, missing timestamps, exact wind boundaries (3–8 mph = 4.828032–12.874752 km/h, unrounded), rain at and around 60% (60 counts as likely), legacy km/h config, sourced items only, English and Arabic equivalence, no old advice phrases, invalid values never shown, UTC timestamps, report v2 matches the API |
| `backend/tests/unit/test_ai_text_guard.py` | Weather advice removed from AI text and lists in English and Arabic; symptom text kept |
| `backend/tests/integration/test_weather_guidance_api.py` | Weather guidance through the scan and diagnosis API (weather service stubbed): verdicts, exactly 60%, no location, old scans use stored readings not stored texts, healthy = no check, AI analysis filtered and flagged with the stored text unchanged; per-scan PDF never prints None or invalid values; v2 report and API agree in English and Arabic |
| `frontend/src/lib/weatherGuidanceUi.test.ts` | Weather panel formatting only: server precision, Arabic digits, missing versus invalid, reference numbering |
| `frontend/src/lib/reportUi.test.ts` | Compare deltas only between available values with the same unit; a report's text follows the report's language, not the app's; recommendations grouped by horizon; citation numbers; Arabic digits |

**Synthetic data rule.** Tests generate images, masks, observations and weather on the fly
in temporary folders (`backend/tests/synthetic_fixtures.py`, marked *SYNTHETIC*). Nothing is
written to `datasets/` or `artifacts/`, and no generated model is ever served by the app
outside a test.

## Manual browser checklist

Use a throwaway database and temporary model folders. Never use your real `artifacts/`.

```powershell
psql -U postgres -c "CREATE DATABASE agriguard_e2e OWNER agriguard;"
$env:DATABASE_URL = "postgresql+psycopg2://agriguard:agriguard@127.0.0.1:5432/agriguard_e2e"
$env:AGRIGUARD_ARTIFACTS_DIR = "$env:TEMP\agriguard-e2e\artifacts"
$env:AGRIGUARD_DATASETS_DIR  = "$env:TEMP\agriguard-e2e\datasets"
$env:LOCAL_STORAGE_DIR       = "$env:TEMP\agriguard-e2e\storage"
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1 -NoReload
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1
```

Run it once **without** models (the expected state on a fresh install). Then, optionally,
put small models trained on generated data into those temporary folders to exercise the
"ready" paths. Results from such models are meaningless and must not be shown to users.

**Localization (diagnosis page)**
- [ ] Without a model: the card says it is waiting for a trained model, and the diagnosis is unaffected
- [ ] The Grad-CAM image is captioned as an attention map; the hero percentage is marked "Estimated…, not measured"
- [ ] With a model: Overlay, Original, Mask and Outlines all render, aligned with the photo
- [ ] The opacity slider, zoom and reset work; unticking a class hides it
- [ ] The area shows a % (leaf class present) or the reason it is unavailable
- [ ] Network tab: artifacts load from `/api/v1/diagnoses/<id>/segmentation/*` with 200 and an `Authorization` header; they are not under `/storage`
- [ ] As another farmer, the same artifact URL returns 403

**Plant recovery**
- [ ] *Track this plant* creates a plant; the card then shows *Tracked as … / Open plant*
- [ ] As an admin viewing someone else's diagnosis, the card is not shown
- [ ] Plant page: one scan → *Not enough scans*; two → a status with reasons and limitations
- [ ] Attaching an existing scan and uploading a follow-up (with a stage) both appear in the scan list and timeline
- [ ] Compare: side-by-side and slider; measured change only when both scans are measurable
- [ ] Recording a treatment shows "Recorded by you" and the disclaimer; a follow-up date creates a reminder
- [ ] Marking a reminder done or dismissing it updates its state; open forms stay open while the page refreshes
- [ ] Another user's `/plants/<id>` shows an error (404)

**Outbreak risk**
- [ ] Without a model: the *not ready* notice; observed cells still draw
- [ ] Filters change the map; the legend matches the layer; the privacy note shows the grid size and threshold
- [ ] Clicking a cell: the panel counts equal the cell's tooltip for the same window
- [ ] Clicking an empty spot opens a panel for that grid cell, with no coordinates shown
- [ ] *Estimate risk* with a crop and disease selected: a result with score type, confidence, completeness, factors, limitations and model version; or *model not ready* / *insufficient data*
- [ ] After an estimate, the *Predicted risk* layer colours that cell
- [ ] The OSM attribution is visible

**Private media**
- [ ] Network tab: scan photos and heatmaps load from `/api/v1/media/...?exp=...&sig=...`
- [ ] An old `/storage/scans/<file>` URL returns 404; editing `sig` or `exp` in a media URL returns 403

**Reports**
- [ ] Diagnosis page → *Full report*: cover with reference, executive summary, key facts with a source on each value, images, recommendations with reason and timing, limitations, methods
- [ ] The summary says whether it is AI-worded or automatic. Without `GEMINI_API_KEY` it is automatic
- [ ] Predictions read as predictions; Grad-CAM values are labelled estimates; missing values say "Not available" with a reason
- [ ] *Regenerate* in Arabic: the report is right-to-left with Arabic digits, English knowledge-base text stays left-to-right, and the versions menu lists both
- [ ] *Download PDF* in English and Arabic: Arabic letters are joined and right-to-left, and the images are present
- [ ] *Print*: no app chrome, sections not split mid-card
- [ ] Plant page → *Progress report*; outbreak cell → *Area report* (observations and estimates in separate sections, no coordinates)
- [ ] *Share*: the link opens signed-out in a private window, shows no internal ids, and stops working after *Revoke*
- [ ] `/reports`: search and filters work; tick two reports → *Compare* shows changes only between comparable values
- [ ] Another user's `/reports/<id>` shows an error (404)
- [ ] At 375 px: the report and the shared view have no horizontal scroll
- [ ] v2 reports show nine numbered chapters; every reasoning statement shows its type; citation numbers link to the References chapter, and each reference says what it is cited for
- [ ] Diagnosis: the attention map, overlay, outlines and mask are side by side, each with an explanation; the model's test results appear next to confidence (or "not available")
- [ ] Plant progress: each scan says whether it is comparable and why not; treatments appear as chart markers and next to the measurements around them; missing follow-up data is listed
- [ ] Regional: the risk level is explained from the score and cut-points; observations and estimates stay in separate sections; inspection priorities are ranked with reasons
- [ ] An older (v1) report still opens with its original layout

**Admin → AI models**: each task shows readiness, version, dataset version and metrics, or the reason it is not ready.

**Layout**: at 375 px wide in English and Arabic, there is no horizontal scroll, the bottom bar
shows Dashboard, History, Scan, Plants, Risk map (+ Admin), and Profile is reachable from the
top-bar avatar.

## Cleaning up

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
psql -U postgres -c "DROP DATABASE agriguard_e2e;"        # only the throwaway database
Remove-Item -Recurse "$env:TEMP\agriguard-e2e"             # only the temporary model/data folders
```
