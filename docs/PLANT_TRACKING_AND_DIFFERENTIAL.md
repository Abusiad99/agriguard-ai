# Plant health records and differential diagnosis

## Plant profiles and observations

**Data model** (migration `0003`):
- **`plant_profiles`** are user-owned records of one tracked plant, tree or bed.
  - Only `name` is required.
  - Optional fields: `crop_type`, `variety`, `planting_date`, `location_label`, `growing_environment` (field, greenhouse, indoor, orchard, nursery, other), and `notes`.
  - Archiving is a soft delete: observations and photos are kept.
  - This is separate from the existing `plants` table, which is the species catalogue.
- **Each diagnosis is a time-stamped observation.** `diagnoses` gains these nullable columns:
  - `plant_profile_id`
  - `decision_status`, `predicted_label`, `candidates_json`, `decision_json` (thresholds and their source, margin, entropy, plant probability mass)
  - `image_quality_json`, `explanation_json`
  - `segmentation_json` plus mask and overlay references
  - `severity_method`, `model_version`, `pipeline_version`
  - `differential_json`

  Existing rows are kept unchanged and marked `decision_status='legacy'`, `pipeline_version='1.x'`. Their old heatmap-derived area is marked `severity_method='legacy_gradcam_threshold'`.
- **`observation_notes`** are **append-only**: `user_note`, `follow_up`, `treatment_applied`, `expert_feedback`, `correction`, `plant_link_change`.
  - A correction never edits the stored result; it is a new note.
  - Moving an observation to a different plant writes a `plant_link_change` note with the from and to ids.
- **Images** stay in the existing object storage; the database only stores references. Images are served only through **signed, expiring URLs** (`/api/v1/media/...`). The previous public `/storage` mount was removed because it exposed every user's photos and reports to anyone holding a path.

## Endpoints

All of these are owner-scoped; a foreign id returns 404.

| Endpoint | Purpose |
|---|---|
| `POST/GET /api/v1/plants` | Create and list plants (search, `include_archived`, `last_status`, pagination ≤ 100) |
| `GET/PATCH/DELETE /api/v1/plants/{id}` | Read, edit, archive |
| `GET /api/v1/plants/{id}/timeline` | Chronological observations with notes and a **measurement series that contains only genuine segmentation measurements**; filters: date range, status; pagination |
| `GET /api/v1/plants/{id}/compare?a=&b=` | Careful comparison of two observations of this plant |
| `POST /api/v1/scans` | Now accepts `plant_profile_id` *or* `new_plant_name`, plus `note` |
| `PUT /api/v1/diagnoses/{id}/plant` | Link or unlink an observation (audited) |
| `GET/POST /api/v1/diagnoses/{id}/notes` | Append-only notes (`expert_feedback`: admins only) |
| `POST /api/v1/diagnoses/{id}/follow-up` | Differential follow-up answers |

## Careful comparison

`app/application/services/observation_comparison.py`:
- **A different predicted label is never reported as improvement or deterioration.** It is reported as "predictions differ", with a caution about lighting, angle, framing and model uncertainty.
- **Numbers are compared only when both observations** have a segmentation measurement of the same method and model version, on the same plant. Legacy estimates are never compared.
- **The verdict depends on the measurement tolerance**, which comes from the segmentation model's held-out affected-area mean absolute error. A change is called "increased" or "decreased" only beyond that tolerance and without photo-quality warnings. Without a validated tolerance the change is "not established".
- **Comparability issues are listed:** different plant, legacy observation, different model versions, quality warnings, not both confident.

## Differential diagnosis

### What the model can and cannot recognise

The classifier is trained on **PlantWild v2: 115 disease classes on 34 plant types** (33 crops plus maple).
- The curated taxonomy groups the classes by cause: fungal 76, bacterial 14, viral 12, oomycete 12, physiological 1 (pepper blossom-end rot).
- There are **no classes for:**
  - healthy plants;
  - insect or mite damage;
  - nutrient deficiencies;
  - water, heat or cold stress;
  - herbicide or spray injury.

  The model therefore **cannot** classify any of these, and the system does not pretend to. None of the disease classes was renamed to cover them.

### How candidates are produced (`ai/knowledge/differential.py`)

1. **Model candidates:** the calibrated top-k classes, with their unchanged probabilities. They are shown only for `confident` and `uncertain` results. An `inconclusive` result shows none, and nothing derived from them either: no look-alike list, all eight follow-up questions, and no hints based on the hidden candidates' cause types.
2. Each candidate gets metadata from `ai/knowledge/taxonomy.py`: cause type, typical affected parts, symptom-pattern tags, and whether the pathogen is regulated in many jurisdictions (citrus greening, citrus canker, plum pox, banana bunchy top, banana Fusarium wilt).
   - **Provenance:** this taxonomy (version `1.0.0-unreviewed`) is general plant-pathology classification compiled for this project. It has **not** been reviewed by an external plant pathologist, and it says so in its version string and in the UI.
3. **"Also consider (not detectable by the model)":** look-alike non-disease causes, chosen from the leading candidate's symptom pattern (for example, mosaic or yellowing → nutrient deficiency, herbicide injury, mite feeding). These are never ranked against model classes and never given a probability.
4. **Expert review is recommended** when:
   - the result is not confident;
   - candidates with at least 10 % probability have different cause types (a 3 % runner-up does not count);
   - a regulated pathogen is among the candidates with at least 5 % probability.

### Follow-up questions

There are eight structured questions: affected parts, distribution, duration, pests seen, watering, weather, spread to neighbouring plants, and recent chemicals. Only the questions relevant to the candidates' symptom patterns are asked.
- Answers are validated against the allowed options and stored as append-only `follow_up` notes.
- They produce rule-of-thumb **hints**. Each hint is either "consistent with…" or "also check…", for example "Very dry or waterlogged soil can cause similar symptoms".
- Answers **never change model probabilities** (this is tested) and are never treated as proof.

### Evaluation status of the categories

- **The 115 disease classes:** per-class precision, recall and F1 are in the evaluation report (`docs/AI_RELIABILITY.md`). Classes with fewer than 10 test images are flagged as having unreliable metrics.
- **Pests, nutrient problems, water, heat and cold stress, chemical injury, and healthy plants:** 0 labelled images. **Automated classification is not implemented**, by design, for lack of data. Only the user-interaction and knowledge workflow above exists.
- **The hint rules** are heuristics and have not been validated against outcomes.
