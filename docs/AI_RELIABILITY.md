# Diagnosis reliability: audit, method and measured results

This page records how the disease classifier was audited and changed, how its confidence is calibrated, how decision thresholds are chosen, and what was actually measured. Every number here comes from a command that was run on this repository. Where the evaluation report is the source, its path is given.

> **Scope of the evidence.** All accuracy and calibration numbers are for a held-out split of **the same dataset the model was trained on** (PlantWild v2, web photos). They are **not** field-validation results. They say nothing about how the model behaves on diseases it was never trained on, on healthy plants, or on photos taken under very different conditions.

## 1. Audit of the original pipeline

These problems were found in the code on `main` before this work. Each is fixed or removed.

| # | Problem | Effect | Fix |
|---|---|---|---|
| A1 | **Label normalisation.** Plant names were matched by substring against an 11-plant list. | 75 of the 115 class folders were filed under the plant `unknown`. The three different wheat rusts (leaf, stem, stripe) were merged into one class. | `ai/data/label_normalizer.py` rewritten: whole-token, longest-first matching over 41 plant names, exact-only condition synonyms. PlantWild v2 now gives **115 distinct labels on 34 plant types, 0 unknown**. Tested in `ai/tests`. |
| A2 | **Affected area from the attention map.** `severity.py` thresholded the Grad-CAM map at 0.5 and divided by the *whole image*, background included, then mapped that to mild/moderate/severe. | The "affected %" and severity level were not measurements of anything. They changed with framing and background. | Removed. Affected area is now only reported from a segmentation model that separates leaf from lesion (`ai/segmentation/`, see [SEGMENTATION.md](SEGMENTATION.md)). Without one, the UI says "not measured". Old rows are labelled `legacy_gradcam_threshold` and never compared. |
| A3 | **Fixed, uncalibrated cut-offs.** Plant-identified ≥ 0.55 and "low confidence" < 0.60 on raw softmax output. | Raw softmax scores of a fine-tuned network are usually over- or under-confident, so a fixed 0.60 has no known error rate. | Temperature scaling fitted on the validation split, and thresholds chosen on validation against explicit accuracy targets (§3). The source of the thresholds is returned with every result. |
| A4 | **Always one answer.** Every image got a single disease label. | Low-confidence guesses looked like diagnoses. | Three decision statuses: `confident`, `uncertain` (candidates only), `inconclusive` (nothing named). |
| A5 | **No image-quality check.** | Blurry, dark or tiny photos were classified like any other. | Quality gate (§5). Clearly unusable photos are rejected before the model runs, with a reason the user can act on. |
| A6 | **Grad-CAM hooks leaked.** Two new hooks were registered on the shared model at every call and never removed. | Each request made the next one slower and used more memory. Concurrent requests could read each other's activations. | Hooks are registered per call and removed in `finally`. The inference service holds a lock around model use. |
| A7 | **Double class balancing.** A class-balanced sampler and class-weighted loss were both active. | Rare classes were over-weighted twice, which hurts calibration and the common classes. | Loss weighting is skipped when the balanced sampler is on (`ai/training/trainer.py`). |
| A8 | **No reproducible evaluation.** Only overall test metrics from the training run. | No per-class view, no calibration, no record of which images were in which split. | `evaluate.py` (§4) and a split manifest with a fingerprint and a leakage check. |

## 2. Training run

<!-- RESULTS_PENDING: training -->

## 3. Calibration and decision thresholds

**Calibration.** After training, `calibrate.py` (run automatically by `train.py`) fits one temperature `T` on the **validation** split by minimising negative log-likelihood. Calibrated probabilities are `softmax(logits / T)`. Temperature scaling does not change which class ranks first, so accuracy is unchanged; it only makes the probabilities more honest.

**Thresholds** are chosen on the same validation split against two targets in `ai/config.py`:

- `confident_threshold`: the lowest calibrated top-1 probability at which the predictions above it still reach **90 % accuracy** (`AGRIGUARD_TARGET_SELECTIVE_ACCURACY`). This maximises how many images get a confident answer while keeping the error rate among them near the target.
- `reject_threshold`: the lowest probability at which the **top-3 candidate list** contains the true class at least **75 %** of the time (`AGRIGUARD_TARGET_CANDIDATE_TOPK_ACCURACY`) *for images at that confidence*. That local rate is estimated with a non-decreasing (isotonic) fit of "true class in top 3" against confidence, so no bin edges have to be chosen. Below the threshold even the shortlist is unreliable, so the result is `inconclusive` and no disease is named.
  - The first version averaged the whole band below the confident threshold instead. On this model that average was exactly 75 %, so the rule marked **nothing** inconclusive, even though images below a confidence of about 0.35 had the true class in their top 3 only 20–67 % of the time. The local rule fixed this; it is covered by a regression test in `ai/tests/test_calibration_and_decision.py`.
- `plant_mass_threshold`: the share of probability on the predicted plant's classes above which the *plant* is named correctly at least 90 % of the time. An inconclusive result below this threshold does not name the plant either; an inconclusive result above it names the plant but no disease.

Both thresholds, the temperature, the targets, whether the targets were met, and the split they were chosen on are saved to `calibration.json` in the run directory. The API returns `thresholds.source`:

- `validation` — loaded from `calibration.json`;
- `env_override` — set by an operator with `AGRIGUARD_CONFIDENT_THRESHOLD` / `AGRIGUARD_REJECT_THRESHOLD`;
- `unvalidated_default` — no calibration file; the UI says the thresholds are not validated.

The thresholds are then checked on the **test** split, which played no part in choosing them (§4).

**What the thresholds do not do.** They are validated only for images of the 115 trained classes. A photo of an unsupported disease, a pest, a deficiency or a healthy plant may still get a high probability for some trained class. No out-of-distribution test set exists in this repository, so open-set rejection has **not** been measured.

<!-- RESULTS_PENDING: calibration -->

## 4. Held-out evaluation

```bash
python evaluate.py                 # test split of the latest run
python evaluate.py --split val     # any split from the manifest
```

The script reloads the exact images of the chosen split from `split_manifest.csv`, so the result does not depend on re-running the split. It writes to `artifacts/runs/<run>/evaluation_<split>/`:

- `report.json`, `report.md`
- `per_class_metrics.csv` (precision, recall, F1, support; classes with fewer than 10 test images are flagged)
- `confusion_matrix.csv`, `confusion_matrix.png`
- `reliability_diagram.png` (before and after temperature scaling)
- `risk_coverage.png` (selective accuracy against the share of images answered)

The report also records the model version, git commit, split fingerprint, leakage check and single-image CPU latency.

<!-- RESULTS_PENDING: evaluation -->

## 5. Image-quality gate

`ai/quality/image_quality.py` runs before the classifier on the decoded photo. The backend also checks the decoded format (JPEG, PNG, WebP), the file size and a 50-megapixel limit against decompression bombs (`backend/app/application/services/image_validation.py`).

| Check | Measure | Reject | Warn |
|---|---|---|---|
| Resolution | shorter side | < 96 px | < 224 px |
| Blur | variance of the Laplacian on a grey copy at most 512 px on the long side | < 12 | < 40 |
| Too dark | mean luminance < 25 or > 75 % of pixels near black (< 16), **and** the mid-tone subject is small (< 8 % of pixels) or itself dark (mean < 45) | yes | mean < 50 and subject mean < 70 |
| Overexposed | > 60 % of pixels near white (> 245), **and** the subject is small or washed out (mean > 185) | yes | > 30 % near white and subject mean > 160 |
| No detail | luminance standard deviation < 6 | yes | < 18 |
| Little plant tissue | fewer than 3 % of non-black pixels have an excess-green index above 0.05 | never | yes |

The subject-aware exposure rule exists because many real leaf photos are taken on a white sheet or a black cloth. A plain "too much white" rule rejected those good photos.

**Calibration on real and degraded photos** (`python -m ai.quality.calibrate_quality`, saved to `artifacts/quality_calibration.json`). 1,500 real PlantWild images were checked as they are, and again after five synthetic degradations of each (applied after downsizing to at most 512 px on the long side):

| Input | Flagged by the expected check | Rejected (any reason) |
|---|---|---|
| Real photos, unmodified | — | **0.4 %** (5 too small, 1 too blurry); 8.9 % warned; 90.7 % passed |
| Heavy blur (Gaussian, radius 6) | 100 % | 100 % |
| Moderate blur (radius 3) | 99.9 % | 99.9 % |
| Very dark (brightness × 0.12) | 99.5 % | 99.8 % |
| Overexposed (brightness × 3.5) | 80.0 % | 42.5 % |
| Tiny (64 px wide) | 100 % | 100 % |

"Flagged" counts the checks meant for that degradation (for darkness: too dark or no detail; for overexposure: overexposed, partly overexposed or no detail). "Rejected" can be higher because an image can be rejected by another check, such as blur. Overexposure is the weakest check: 20 % of the over-brightened photos were not flagged, and most flagged ones get a warning rather than a rejection, because rejecting harder also rejected good white-background photos. The non-plant hint is a warning only: no labelled set of non-plant photos exists here to set a rejection threshold.

## 6. Explanations

Grad-CAM (`ai/explainability/gradcam.py`) is computed for the top class and shown next to the original photo, labelled **"model attention"**. The UI and PDF state that it shows which regions influenced the model, not where the disease is, and that it is not a measurement. For transformer backbones attention rollout is not implemented and the result says the explanation is unavailable rather than showing a substitute.

## 7. Limitations

- **Same-distribution test.** Test images come from the same web-photo collection as the training images. Field accuracy will be lower and is unknown.
- **No healthy class.** PlantWild v2 has no healthy-plant images, so the model cannot say a plant is healthy. The dashboard never counts a disease-model result as healthy.
- **Closed set.** Pests, nutrient deficiencies, water, heat and cold stress, chemical injury and diseases outside the 115 classes cannot be recognised. Open-set rejection was not measured.
- **Small classes.** Many classes have only a handful of test images, so their per-class metrics have wide uncertainty. The report flags them.
- **No expert review.** No plant pathologist has reviewed the predictions, the thresholds or the knowledge taxonomy.
- **Duplicates.** Exact and near-duplicate images (64-bit average hash, Hamming distance ≤ 4) were removed before splitting. Near-duplicates that differ more than that (crops, re-encodes with edits) can remain.
