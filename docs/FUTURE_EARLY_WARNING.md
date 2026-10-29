# Early disease-risk prediction: deferred by design

**Status: not implemented.** No risk-prediction model exists in this codebase, and none should be added until the data below exists. Weather data alone is never evidence that a plant has a disease. The app uses weather only to time irrigation and spraying advice for a *confident* result, and it says so in the UI and the PDF report.

## Why it is deferred

A disease-risk model, whether gradient boosting, a random forest, a sequence model or a mechanistic infection model, learns how often a disease appears under given conditions. Training and validating one honestly requires **verified outcomes**. Image-model predictions are not verified outcomes, so training on them would just teach a second model to imitate the first one's errors.

## Data that has to accumulate first

The tracking schema introduced in migration `0003` already records most of this. Each record should carry:

1. **Plant identity over time:** `plant_profile_id`, `crop_type`, variety, planting date, growing environment, and location (with consent).
2. **Time-stamped observations:** `diagnosed_at`, `decision_status`, `predicted_label`, calibrated probability, `model_version`, and image-quality status.
3. **Verified outcomes:**
   - `expert_feedback` / `correction` notes, or laboratory confirmation, for a meaningful share of observations;
   - **negative observations**, meaning confirmed healthy plants (the current classifier cannot produce these);
   - onset dates.
4. **Environment as actually experienced at the plant:** hourly temperature, relative humidity, leaf wetness or rainfall, linked by location and time window (for example the 3–14 days before onset). Snapshots taken at scan time are not enough.
5. **Interventions:** `treatment_applied` notes with dates. Treated plants confound any risk model.
6. **Volume and balance:** several seasons and locations per crop–disease pair, with grouped (by field and season) train/validation/test splits to avoid leakage.

## Future architecture (for reference only)

```
observations + verified outcomes ─┐
hourly weather per field ─────────┼─► feature store (rolling windows: wet hours, temp bands)
crop calendar / phenology ────────┘          │
                                             ▼
                           per crop–disease risk model (calibrated; evaluated by season)
                                             │
                    risk alert with uncertainty + "why" (top weather drivers)
                    + recommended scouting action (not a diagnosis, not a spray order)
```

**Acceptance criteria before shipping:**
- Calibrated probabilities on held-out seasons.
- Lead time measured against confirmed onsets.
- False-alarm rate per field-season reported.
- An agronomist review of the alert wording.
