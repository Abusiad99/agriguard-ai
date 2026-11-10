# Agricultural reports

AgriGuard turns stored diagnoses, segmentation results, recovery records and outbreak data
into structured, versioned assessments. Every report can be:
- viewed in the app, downloaded as a PDF or printed;
- shared through an expiring link;
- compared with another report, and found again in the archive.

Reports are available in English and Arabic.

| Milestone | Status |
|---|---|
| Software (schema v2, service, API, PDF in English and Arabic, UI, sharing, references, migrations 0007–0008, tests) | Complete |
| Content quality on real data | Depends on the trained models, their test results and the knowledge base you load |
| Disease- and treatment-specific references | The knowledge base ships empty. Agronomists attach sources through the references API |
| LLM-written summaries | Optional. Off unless `GEMINI_API_KEY` is set. Validated, with a template fallback |
| Production readiness | Not claimed |

## What a report contains (schema `agriguard.report.v2`)

Every report has nine chapters, in the order of a professional assessment:

| # | Chapter | Diagnosis | Plant progress | Regional risk |
|---|---|---|---|---|
| 1 | Executive summary | Narrative and key facts | Same | Same |
| 2 | Condition | Prediction, confidence, knowledge-base match | Recovery status and why | Observations in the selected cell and the region |
| 3 | Evidence and analysis | See *Diagnosis evidence* below | Every scan in order, with whether it is comparable and why not; measured changes between comparable scans | Weekly trend, last year, observations per cell, weather summary, published suitability rules |
| 4 | Visual results | Photo, attention map, segmentation overlay, outlines, mask, each explained; photo quality; earlier scans of a tracked plant | Area and estimated-severity trends with recorded treatments marked; photo series | Region map |
| 5 | Interpretation | Severity estimate vs measured area; weather at scan time against spraying limits; area activity; plant context | Treatments next to the measurements before and after them; possible explanations (hypotheses); timeline | How the risk level was computed; main factors vs training data; why the cell is higher or lower than its neighbours; coverage gaps |
| 6 | Recommended actions | Grouped as immediate, short-term and long-term (see below) | Same | Ranked inspection priorities and actions |
| 7 | Monitoring plan | Rescan date, comparable photos, recording treatments | Missing follow-up data (long gaps, follow-up due, treatments with no later scan, overdue reminders, unmeasured scans), next scan | Weekly scouting, recording negatives, new estimate after the forecast window |
| 8 | Limitations and missing information | Every "not available" value with its reason, plus limitations | Same | Same |
| 9 | References and source traceability | Numbered sources with what each is cited for; methods, data fingerprint, records used | Same | Same |

### Diagnosis evidence

- **Why the system produced this result**: one sentence per piece of evidence. Each sentence is typed:
  - *model output*: the ranking, and the gap to the next class;
  - *test result*: the model's held-out precision and recall for this class, when `metrics.json` exists;
  - *published source*: confidence is not accuracy;
  - *estimate*: what the attention map shows;
  - *measured*: segmentation regions and area;
  - *knowledge base*: symptoms to check;
  - *AgriGuard rule*: the close-call threshold, photo problems;
  - *not available*.
- **Model confidence and measured accuracy**: confidence next to the model's own test precision, recall, test-image count and overall accuracy. A close call is flagged when the gap is below `close_margin_pp` (15 pp, an AgriGuard rule).
- **Detected visual findings**: per disease class, regions, pixels, share of plant tissue and mean confidence, plus mean uncertainty. Shares appear only when the measured area is valid.
- **Other possible diagnoses**: the stored top-k alternatives, with each one's test recall and its knowledge-base symptoms, to tell them apart.
- **Knowledge-base information**: copied verbatim, in its language, with its references.
- **What would make this assessment more reliable**: fixes for each photo issue, more views at different stages, a laboratory sample before any pesticide, context to record, the segmentation model, tracking, an optional location.

AgriGuard does not detect symptoms. Knowledge-base symptoms are shown as *symptoms to check*, never as findings.

### Integrity rules (enforced by `validate_content`)

- Every value has a provenance kind. These are listed below.
- Every number comes from a stored value or a computation over stored values.
- Every unavailable value gives its reason. Chart series have equal lengths, and markers lie on the axis.
- Every statement has a type. A statement typed *published source* must cite one.
- Every cited reference id exists in the report's reference list.
- Every recommendation has a horizon and a basis:
  - basis *reference* requires citations;
  - *knowledge_base* requires a knowledge-base record;
  - *general_guidance* must be labelled so.
- Each v2 section belongs to a chapter.

A report that fails these checks is not stored.

Other rules followed by the builders (`builders.py`):
- Predictions are predictions.
- Grad-CAM is an explanation of the classifier, never a lesion outline or a measured area.
- Measured area is never turned into a severity grade, and nothing is called "critical".
- A changed label or a changed confidence is never evidence of recovery.
- Treatments are shown next to measurements, never credited with a change.
- A grid cell is never a farm, and an estimate is never a confirmed outbreak.

### Provenance kinds

`model`, `model_evaluation` (held-out test results), `model_measurement` (segmentation), `model_estimate`
(Grad-CAM), `rule` (AgriGuard rule), `sourced_rule` (published rule such as the Hutton criteria),
`reference` (published source), `knowledge_base`, `general_guidance`, `user_recorded`, `observation`,
`historical`, `weather_provider`, `llm_summary`, `system`.

## Recommendations (`recommendations.py`, `configs/reports/rules.json`)

Each recommendation has:
- a **horizon**: immediate, short-term or long-term;
- an **action type**: inspection, monitoring, weather and timing, expert confirmation, treatment, prevention or data quality;
- a priority, reason, evidence, timing, objective and warnings;
- a **basis**:

| Basis | Meaning | Examples |
|---|---|---|
| Published source | Rests on a verified reference, cited by number | Confirm with a laboratory before any pesticide; spraying wind and rain limits; weekly scouting; spread and long-term prevention practices; Hutton criteria met |
| Knowledge base | Copied from the knowledge base, with its references | Treatments |
| AgriGuard rule | Procedural, triggered by this report's data, no agronomic claim | Retake the photo; prediction changed since the last scan; track the plant; rescan after a recorded treatment; inspect cells with confirmed cases |
| General guidance | No verified source, labelled as such | Used only if a catalogued source is missing |

**Context used**:
- crop, prediction, gap to the next class and the class's test precision;
- estimated severity and measured area;
- photo quality;
- wind and rain at scan time against the sourced spraying limits;
- confirmed cases in the scan's grid cell;
- recorded treatments (recent ones, same-category ones, ones with no later scan);
- earlier scans (label changes, persistence);
- overdue reminders;
- the region's priority cells and suitability rules.

**Never generated**:
- product names, concentrations or doses;
- claims that a treatment works.

Chemical instructions appear only when the knowledge base cites a source and the entry isn't referral-only.

**General prevention practice** (water at the base of plants, airflow, sanitation, rotation, removing infected material, resistant varieties) is cited to a university extension source and marked *General practice, not specific to this disease*.

Thresholds (`configs/reports/rules.json`):

| Setting | Value | Basis |
|---|---|---|
| `rescan_days_disease` | 7 | AgriGuard default, consistent with weekly scouting (`ref-umn-prevention`) |
| `rescan_days_healthy` | 30 | AgriGuard default |
| `close_margin_pp` | 15 | AgriGuard rule |
| `min_class_precision_pct` | 80 | AgriGuard rule |
| `spray_wind_min_mph`, `spray_wind_max_mph` | 3, 8 | Published source (`ref-spray-wind`); converted exactly, see *Weather and spraying guidance* |
| `spray_rain_probability_pct` | 60 | AgriGuard threshold for "rain likely" (no published number) |
| `follow_up_gap_factor` | 2 | AgriGuard rule |

`rules_version` is `report-rules-v3`. Older configs that still give `spray_wind_min_kmh` / `spray_wind_max_kmh` are read as km/h and converted to mph, so they keep working.

## Weather and spraying guidance (`weather_guidance.py`)

One module, `backend/app/application/reporting/weather_guidance.py`, decides whether the weather recorded at scan time was within the advised spraying limits. Everything that talks about spraying weather uses it:

| Consumer | What it shows |
|---|---|
| Diagnosis API: `GET /api/v1/diagnoses/{id}` and the scan response | `weather_guidance`: verdict, measurements, limits, summary and items in English and Arabic, references (see *API* below) |
| Diagnosis page (`WeatherGuidancePanel.tsx`) | The server's result, formatted. No threshold, rule or verdict is computed in React |
| Report v2: environment section and recommendation `R-DX-SPRAY-CONDITIONS` | The same summary and item texts and the same verdict (`weather_verdict` on the section) |
| Per-scan PDF (`pdf_report_generator.py`) | "Weather at Scan Time" and "Spraying Conditions at Scan Time", with numbered sources |
| Gemini context | Only the measured values (`measurements_text`), never a verdict or advice |

The input is the weather snapshot stored with the scan (Open-Meteo current conditions, fetched once at scan time). Older scans are assessed from their stored snapshot when the API is read; the advice texts stored with them are no longer shown.

**Measurements.** Each value is `ok`, `missing` or `invalid`. A value is invalid when it is not a number or is outside these physically possible ranges: wind 0–400 km/h, rain probability 0–100%, temperature −80 to 65 °C, relative humidity 0–100%, UV index 0–25. These are plausibility checks, not agricultural limits. An invalid value is never used and never displayed: the page, the PDFs and the texts say "Not a valid measurement" or "Invalid reading, not used". A missing value says "Not recorded", and a missing scan time says "time not recorded".

**Limits.**

| Condition | Rule | Basis |
|---|---|---|
| Wind | Within limits from 3 to 8 mph inclusive. 1 mph = 1.609344 km/h exactly, so 4.828032–12.874752 km/h. Above 8 mph: drift more likely. Below 3 mph: possible temperature inversion. Displayed rounded ("4.8–12.9 km/h (3–8 mph)") but compared unrounded: 12.874752 km/h is within; 12.874753 and 12.9 are not | Published source `ref-spray-wind`, which applies when the product label gives no wind directions |
| Rain | Likely when the weather service's probability is **at or above 60%**; exactly 60% counts as likely | The 60% figure is an AgriGuard threshold (no source gives a number). "Avoid applying when rain is likely" is from `ref-rainfast` |
| Temperature, humidity | Shown, no limit applied | No general limit was verified. `ref-spray-wind` supports only that labels may set limits and that hot, dry air makes droplets drift |

The product label always comes first, and every text says so.

**Verdicts.**

| Verdict | When | Badge (English / Arabic) |
|---|---|---|
| `within_limits` | Wind within limits and rain not likely | Within advised limits / ضمن الحدود الموصى بها |
| `wait` | Wind above or below the limits, or rain likely. One valid problem is enough, even if another value is missing | Wait / انتظر |
| `incomplete` | Weather was recorded, but wind or rain is missing or invalid, and no valid value is outside the limits | Could not be fully assessed / تعذّر التقييم الكامل |
| `not_assessed` | No weather recorded (no location shared, or the weather service failed) | Not assessed / لم يُقيَّم |
| `not_applicable` | Healthy prediction: no spraying check is given, and the legacy `recommendation` is `null` | No spraying check / لا يوجد فحص للرش |

**Items and basis.** Each item (`wind`, `rain`, `label_limits`) has a status (`ok`, `caution`, `unavailable` or `info`), a basis (`reference`, or `missing_data` when the measurement is missing or invalid) and the ids of the references it cites. Items with basis `reference` always cite a catalog entry; items without a usable measurement cite nothing.

**API** (`WeatherGuidanceSchema` in `diagnosis_schemas.py`):

```json
"weather_guidance": {
  "verdict": "wait",
  "observed_at": "2026-11-01T10:00:00+00:00",
  "limits": {"wind_min_kmh": 4.828032, "wind_max_kmh": 12.874752, "wind_min_mph": 3.0, "wind_max_mph": 8.0,
             "rain_likely_at_or_above_pct": 60.0},
  "measurements": {"wind_speed_kmh": {"state": "ok", "value": 20.0, "status": "high"},
                   "humidity_pct": {"state": "invalid", "value": null}},
  "summary": {"en": "Wait before spraying: ...", "ar": "انتظر قبل الرش: ..."},
  "items": [{"code": "wind", "status": "caution", "basis": "reference", "refs": ["ref-spray-wind"],
             "text": {"en": "...", "ar": "..."}}],
  "references": [{"n": 1, "id": "ref-spray-wind", "title": "...", "url": "https://...",
                  "claims": {"en": ["..."], "ar": ["..."]}}],
  "rules_version": "report-rules-v3"
}
```

(The example is shortened: `measurements` always has all five keys.) `observed_at` is always sent in UTC: PostgreSQL returns the database session's time zone and SQLite none, and both are normalised. Invalid values are sent as `null`, never as the raw reading.

**Legacy `recommendation` field.** Kept for older clients. `spraying_advice` now holds the English summary above, and `irrigation_advice` and `fertilizer_advice` are always `null`. The earlier texts ("favourable for spraying", "Delay irrigation", "nitrogen-heavy fertilizer") had no source and are no longer returned for any scan, old or new. A healthy prediction returns `recommendation: null`.

**Gemini (AI analysis).** The prompt (`gemini_client.py`) forbids weather-based spraying, irrigation or fertilizer advice and claims that the weather favours a disease; `environmental_risk` may only restate measured values. Because a model can ignore instructions, `ai_text_guard.py` also filters the stored analysis when the API is read. Any sentence or list item that pairs a weather term (weather, rain, wind, humidity, temperature, "these conditions" and similar, in English and Arabic) with advice or a risk claim (spray, irrigate, fertilize, favour, delay, avoid and similar) is removed. Symptom and severity text is kept, and the stored text is not changed (for audit). When anything was removed, `ai_analysis.weather_advice_removed` is `true` and the page shows a translated notice pointing to the sourced weather panel; the removed text and the filter's details are not shown. The prompt and the filter have been tested with synthetic AI text only, not with a real Gemini key.

**Tests.** They use synthetic readings and check the logic, not real-world agricultural accuracy.
- `backend/tests/unit/test_weather_guidance.py`:
  - all five verdicts; missing, invalid, non-numeric and conflicting readings; missing and unreadable timestamps;
  - exact wind boundaries (4.828031, 4.828032, 12.874752, 12.874753 and 12.9 km/h); rain at 59.999, 60, 60.0001, 0 and 100%; legacy km/h config;
  - every `reference` item cites a catalog entry; English and Arabic give the same verdicts, items and references; no old advice phrases; invalid values never appear in either language; time-zone normalisation;
  - the report v2 environment section and recommendation match the API texts.
- `backend/tests/unit/test_ai_text_guard.py`: weather advice removed and symptom text kept, in English and Arabic, for text and lists.
- `backend/tests/integration/test_weather_guidance_api.py`:
  - verdicts through the real scan endpoint, with the weather service stubbed; exactly 60% through the API; no location;
  - an older scan with stored unsourced advice; a healthy prediction; stored AI analysis filtered and flagged, with the stored text unchanged;
  - the per-scan PDF never prints "None" or an invalid value; the v2 report and the API agree in English and Arabic.
- `frontend/src/lib/weatherGuidanceUi.test.ts`: formatting only (numbers at the server's precision, Arabic digits, missing versus invalid, reference numbering).

Results on 2026-11-10 (Windows 11, Python 3.11.9, local PostgreSQL 16.14 test database):

| Check | Result |
|---|---|
| Backend, SQLite (`pytest -q`) | 418 passed, 3 skipped (2 PostgreSQL-only migration tests, 1 trained-model inference test) |
| Backend, PostgreSQL (`AGRIGUARD_TEST_DATABASE_URL=…/agriguard_test`) | 420 passed, 1 skipped (trained-model inference test) |
| Weather and AI-filter tests only, on each database | 116 passed |
| Frontend | `npm run lint` exit 0, `npm run typecheck` exit 0, `npm test` 19 passed (3 files), `npm run build` succeeded |
| Browser (synthetic scans on a throwaway database) | All four verdicts, missing and invalid readings, the AI-filter notice, English and Arabic (RTL, Arabic digits), 375 px mobile and desktop width: no horizontal overflow, no invalid value shown |

## References

A report cites a source only through a **claim**: AgriGuard's short statement of what that source supports. References are numbered in order of first use. Facts, statements, images and recommendations point to them.

### Built-in catalog (`configs/reports/references.json`)

Sources for the claims AgriGuard's own rules make. Each was checked by opening the page on the date shown. The claim text exists in English and Arabic; the sources themselves are in English.

| Id | Source | Cited for |
|---|---|---|
| `ref-gradcam` | Selvaraju et al., *Grad-CAM*, IJCV 2019 / ICCV 2017 (arXiv:1610.02391) | Grad-CAM gives a coarse map of the regions important for a prediction |
| `ref-calibration` | Guo et al., *On Calibration of Modern Neural Networks*, ICML 2017 (arXiv:1706.04599) | Network confidence is often poorly calibrated |
| `ref-field-gap` | Mohanty, Hughes & Salathé, *Front. Plant Sci.* 7:1419, 2016 | 99.35% on its own test set, about 31% on images from other sources |
| `ref-hutton` | AHDB, Hutton Criteria project page | The criteria and their adoption in 2017 |
| `ref-umn-prevention` | University of Minnesota Extension, *Preventing plant diseases on farms* | Irrigation, airflow, sanitation, removal, rotation, weekly scouting, resistant varieties |
| `ref-spray-wind` | Pesticide Environmental Stewardship, *Evaluate the Weather* | Spray at 3–8 mph without label directions; calm may mean an inversion |
| `ref-rainfast` | UF/IFAS EDIS PI238, *Rainfastness of Pesticides* (2011, archived) | Avoid application when rain is likely |
| `ref-cornell-sampling` | Cornell Plant Disease Diagnostic Clinic, *Sample collection and submission tips* | Sample before pesticide; damage stages; context to record |

Rules for adding a catalog entry:
- open the source yourself and record its title, organization, authors, URL, DOI and date exactly as shown;
- write a claim the source supports, and nothing more;
- give the claim in both languages and set `verified_on`.

`validate_catalog` rejects entries without these fields or with non-https URLs. An LLM is never a source.

### Knowledge-base references (migration `0008_knowledge_references`)

Disease- and treatment-specific sources are stored in the database:
- `knowledge_references` holds title, authors, organization, URL (unique), DOI, publication date as published, source type, language, notes, verification date and who verified it.
- `knowledge_reference_claims` holds what a reference supports, attached to:
  - a disease (stable key `<plant>/<disease name>`);
  - a treatment (its row id: a revised treatment needs its source checked again);
  - or a rule, guidance item or method.

References are deactivated, never deleted, so stored reports stay traceable. Every change is audit-logged.

| Method | Path | Who |
|---|---|---|
| GET | `/api/v1/references?q=&subject_type=&subject_key=&subject_id=&include_inactive=` | Any signed-in user |
| GET | `/api/v1/references/catalog` | Any signed-in user (the built-in catalog) |
| GET | `/api/v1/references/{id}` | Any signed-in user |
| POST / PATCH / DELETE | `/api/v1/references[/{id}]` | Agronomist, admin (DELETE deactivates) |
| POST / DELETE | `/api/v1/references/{id}/claims[/{claim_id}]` | Agronomist, admin |

The old free-text `treatments.source_citation` is still shown. When no structured reference backs it, the report says that the citation has not been linked to a checked source. There is no admin screen for references yet; use the API.

## How a report is built (`backend/app/application/reporting/`)

```
collect evidence -> build content -> recommendations -> references -> narrative -> validate -> store
(service.py)        (builders.py)    (recommendations.py) (references.py) (narrative.py) (content.py)
```

- **Evidence** is plain data read from the database, the model registry and the run's `metrics.json`. It is fingerprinted (`data_hash`), and its records are listed (`sources_json`), including the knowledge references used.
- **Builders** are pure, so the same evidence gives the same report. Tests build reports from synthetic evidence and check numbers exactly.
- **Storage**: an immutable row per version. Regenerating creates version *n + 1*, for all three types.

## LLM use (`narrative.py`)

Gemini words the executive summary only when `GEMINI_API_KEY` is set and `REPORTS_LLM_ENABLED=true`. It receives the report's own facts, numbered, and must cite fact ids.

The output is rejected, and the template summary used instead, when it:
- has unsupported numbers;
- contains doses, references or links;
- uses certainty words about predictions;
- names unknown diseases;
- has bad JSON or excessive length.

The LLM never changes facts, recommendations, references or provenance, and cannot add citations.

## Exports, sharing, privacy

- **PDF** (`app/infrastructure/reporting/report_pdf.py`, cached per version under the renderer version):
  - layout: the nine numbered chapters, typed and colour-coded statements, citation numbers, images side by side (overlays composed on the photo), treatment markers on charts, and a reference list;
  - Arabic: shaped and right to left, with Arabic digits;
  - version 1 reports keep their original layout.
- **Share links**: owner only, expiring after 1 to 30 days, revocable, token stored hashed. A shared copy carries no internal record ids: provenance records, row ids, subject ids and the scan id are removed.
- **Personal data**: names, emails and locations are never part of a report. Images use signed media URLs.

## Report API

Under `/api/v1/agri-reports` (authenticated; other users' reports return 404):
- POST to create;
- GET for the archive;
- GET `/{id}`, `/{id}/versions`;
- POST `/{id}/regenerate`;
- GET `/{id}/pdf`, `/{id}/map.png`;
- shares: POST / GET / DELETE `/{id}/shares[/{share_id}]`.

Public, under `/api/v1/shared-reports/{token}`: the report, `/pdf` and `/map.png`. The original per-scan PDF (`GET /api/v1/reports/{diagnosis_id}`) keeps its layout. PDFs generated from now on show the sourced spraying-conditions section instead of the old weather advice (see *Weather and spraying guidance*).

## Limitations

- Quality is bounded by the models, their test results and the knowledge base. Synthetic models are flagged on the cover. Test results describe the model's own test set; field photos usually score lower, and the report says so.
- The knowledge base has no "risks if untreated" or region fields, and ships with no disease-specific references. Reports say what is missing.
- Weather guidance:
  - it describes the moment of the scan only. Open-Meteo's current rain probability is not a forecast for the hours after spraying, and the texts say so;
  - temperature and humidity have no limit, because no general limit was verified;
  - the 60% "rain likely" threshold is AgriGuard's, not a published figure;
  - per-scan PDFs generated before this change are stored files and are served as they are, with the old weather advice. The API and the diagnosis page no longer show that advice for any scan;
  - the Gemini prompt and filter were tested with synthetic text only, not with a real API key;
  - source titles and organisations stay in English in Arabic views, because the sources are in English.
- Crop and disease names come from classifier labels and stay in English in Arabic reports.
- The region map image has no base map. The interactive map uses OpenStreetMap tiles.
