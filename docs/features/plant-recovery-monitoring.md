# Plant recovery and treatment monitoring

Users can follow a specific plant over time: attach scans to it, record what they did,
plan follow-ups, and see whether **measured** symptoms are going down.

| Milestone | Status |
|---|---|
| Software (API, UI, migrations, rules engine, tests) | Complete |
| Dataset integration | Optional: a longitudinal dataset in `datasets/recovery/` is only used to calibrate the rules |
| Training | Not applicable. Recovery status is rule-based (`rules-v1`), not a trained model |
| Evaluation on real data | Not done. Needs labeled scan pairs (see calibration) |
| Production readiness | Not claimed |

Measured change requires the segmentation model (see
[disease-localization.md](disease-localization.md)). Without one, every plant with two or
more scans is **Inconclusive**, and the page explains why.

## Concepts

- **Tracked plant**: owned by one user. Name, crop, species and notes. An optional location
  is private: it is never used on the outbreak map and never shown to others.
- **Scan link**: a diagnosis attached to a plant, with a treatment stage (`before_treatment`,
  `during_treatment`, `after_treatment`, `unknown`). A diagnosis belongs to at most one plant.
- **Treatment record**: what the user says they applied. It is always `source: "user_recorded"`.
  AgriGuard never suggests products or doses here. `dosage_text` is free text as the user
  applied it. The UI shows a disclaimer that a treatment followed by improvement does not
  prove the treatment caused it.
- **Reminder**: a next scan or treatment follow-up with a due date. States are
  `pending`, `overdue` (derived), `completed` and `dismissed`.
- **Timeline**: an append-only event log (plant created, scan added or removed, treatment
  recorded, reminder planned or done, assessment updated).

## Recovery assessment (`ai/recovery/engine.py`, `configs/recovery/rules.json`)

The assessment is rule-based and every result explains itself:

| Status | When |
|---|---|
| `insufficient_data` | Fewer than two scans |
| `inconclusive` | No two comparable affected-area measurements, measurements less than `min_days_between` apart, or a trend that disagrees with the endpoints |
| `stable` | The measured area changed by less than `stable_band_pct` (default 5 percentage points) |
| `improving` / `worsening` | The measured area went down or up by at least `stable_band_pct` |

Comparable measurements come from the same segmentation model version. Scans with
blocking quality issues (`blurry`, `too_dark`, `overexposed`) are excluded. A classifier
label changing to *healthy* is reported as an indicator only, with the limitation
`label_change_alone_insufficient`. It never produces "improving" by itself. Classifier
confidence is shown as "not a health measure".

Each assessment stores `indicators`, `limitations`, `area_series` and `method_version`.

### Scan comparison

`GET /tracked-plants/{id}/compare?first=&second=` returns days between, resolution ratio,
lighting difference, classification change, and an area change **only** when both scans
have measurements from the same model and acceptable quality. The limitation
`camera_angle_and_distance_not_verified` is always included.

### Calibration

`stable_band_pct` can be checked against labeled data:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action calibrate
```

This writes `datasets/recovery/reports/calibration_report.json` with accuracy and a confusion
matrix for each band value. It recommends a value but **does not edit** `rules.json`. If you
change the method, change `method_version` too.

When several band values tie for the best accuracy, the report lists them all
(`tied_best_bands`) and recommends their median rather than the smallest. A tie usually means
the labeled pairs can't tell those values apart, so look at the confusion matrices before
choosing.

## API (`/api/v1/tracked-plants`, login required, owner-only)

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `` | List (`status=active\|archived`, paging) / create (`initial_diagnosis_id` optional) |
| GET | `/reminders?state=open\|overdue\|completed\|all` | The user's reminders across plants |
| GET / PATCH | `/{id}` | Detail (plant, scans, assessment, treatments, reminders) / update or archive |
| POST | `/{id}/scans` | Attach an existing diagnosis (`diagnosis_id`, `treatment_stage`) |
| DELETE | `/{id}/scans/{diagnosis_id}` | Detach (the diagnosis itself is kept) |
| GET | `/{id}/compare` | Compare two scans |
| GET / POST | `/{id}/assessment` | Latest / recompute |
| GET | `/{id}/timeline` | Events, newest first |
| GET / POST | `/{id}/treatments` | List / record |
| DELETE | `/{id}/treatments/{tid}` | Delete a treatment record |
| GET / POST | `/{id}/reminders` | List / create |
| PATCH | `/{id}/reminders/{rid}` | `pending`, `completed` or `dismissed` |

Other users' plants answer **404**, not 403, so their existence isn't revealed.
`POST /api/v1/scans` also accepts `tracked_plant_id` and `treatment_stage` form fields for
follow-up scans. The plant must belong to the caller, and this is checked before the image is
processed.

## Frontend

- **My plants** (`/plants`): plant cards with latest status, scan count, last scan and next
  follow-up; open follow-ups across plants; archived filter; *Track a plant*.
- **Plant page** (`/plants/:id`): recovery status with explanation, indicators and limitations,
  and *Recheck*; an affected-area chart (only for comparable measurements); scan comparison
  (side by side or slider); the scan list; follow-up upload; attaching an existing scan;
  treatments with disclaimer; follow-ups; timeline; edit and archive.
- **Diagnosis page**: *Track this plant* (new plant, or add to an existing one). Shown to
  the diagnosis owner only.

## Database (migration `0005_plant_recovery`)

`tracked_plants`, `tracked_plant_scans` (unique `diagnosis_id`), `treatment_records`,
`follow_up_reminders`, `recovery_assessments`, `plant_timeline_events`. All are owner-scoped
with `ON DELETE CASCADE` from the plant. Diagnoses are referenced, never deleted.

## Limitations

- No push or email notifications. Reminders show in the app only.
- Overdue is judged by the server's date. Reminders have no per-user time zone.
- Recovery is measured from photos. It is not a diagnosis of plant health, and correlation
  with a treatment is not causation.
