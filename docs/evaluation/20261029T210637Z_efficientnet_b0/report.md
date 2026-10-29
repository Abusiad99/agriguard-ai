# Evaluation report — 20261029T210637Z_efficientnet_b0:443d399c836c

- Evaluated: 2026-10-29T23:40:15.550223+00:00 (git 34d321d6c3)
- Split: **test** — 1535 images, 115 classes present (fingerprint `2ee97bcf13e131c3`)
- Architecture: efficientnet_b0; temperature: 1.2281764786282499

## Classification (top-1 prediction, no abstention)

| metric | value |
|---|---|
| accuracy | 0.6072 |
| top-3 accuracy | 0.8215 |
| top-5 accuracy | 0.8866 |
| macro precision | 0.5678 |
| macro recall | 0.5644 |
| macro F1 | 0.5455 |
| weighted F1 | 0.6012 |

## Calibration

| | ECE | MCE | Brier | NLL | mean confidence |
|---|---|---|---|---|---|
| raw softmax | 0.0930 | 0.1736 | 0.5429 | 1.4896 | 0.6993 |
| temperature-scaled | 0.0457 | 0.0763 | 0.5334 | 1.4448 | 0.6209 |

## Selective classification (calibrated confidence)

AURC: 0.1908

| coverage | accuracy on answered | confidence threshold |
|---|---|---|
| 1.00 | 0.6072 | 0.0522 |
| 0.90 | 0.6527 | 0.2514 |
| 0.80 | 0.6897 | 0.3487 |
| 0.70 | 0.7247 | 0.4498 |
| 0.60 | 0.7655 | 0.5253 |
| 0.50 | 0.8125 | 0.6155 |

## Validation-selected decision thresholds applied to this split

confident ≥ 0.8106, inconclusive < 0.3771 (selected on val, target selective accuracy 90%)

| status | share of images | accuracy |
|---|---|---|
| confident | 0.3212 | top-1 0.8803 |
| uncertain | 0.4495 | top-1 0.5754, top-3 0.8580 |
| inconclusive | 0.2293 | (top-1 if forced: 0.2869) |

## Classes needing attention

- Classes with < 10 test images (metrics unreliable): 53
- Classes with F1 < 0.5: 42 (first 30 shown; all in per_class_metrics.csv): broccoli___ring_spot, carrot___cercospora_leaf_blight, cauliflower___alternaria_leaf_spot, coffee___black_rot, peach___anthracnose, peach___rust, pepper___frogeye_leaf_spot, plum___bacterial_spot, bean___rust, tomato___mosaic_virus, bean___mosaic_virus, tobacco___blue_mold, raspberry___fire_blight, blueberry___botrytis_blight, cabbage___alternaria_leaf_spot, cherry___powdery_mildew, wheat___bacterial_leaf_streak_black_chaff, eggplant___phytophthora_blight, tobacco___frogeye_leaf_spot, wheat___septoria_blotch, broccoli___downy_mildew, eggplant___cercospora_leaf_spot, apple___black_rot, squash___powdery_mildew, tobacco___brown_spot, bean___halo_blight, broccoli___alternaria_leaf_spot, raspberry___leaf_spot, zucchini___downy_mildew, grape___leaf_spot

## Leakage check

```
{
  "hamming_threshold": 4,
  "exact_duplicates_across_splits": {
    "train-val": 0,
    "train-test": 0,
    "val-test": 0
  },
  "near_duplicates_vs_train": {
    "train-val": 0,
    "train-test": 0
  },
  "near_duplicate_examples": []
}
```

## Latency (single image, batch 1)

```
{
  "device": "cpu",
  "torch_threads": 4,
  "n_images": 50,
  "p50_ms": 21.505181999998513,
  "p95_ms": 40.28358364996618,
  "mean_ms": 25.010270620011852,
  "parameters": 4154863,
  "weights_file_mb": 16.89,
  "peak_rss_mb": 1531.1,
  "note": "Excludes Grad-CAM (one extra backward pass) and the quality gate."
}
```

## Limitations

- Test images come from the same web-collected source distribution as training; this is not an independent field validation.
- The dataset contains no healthy-plant images and no non-plant / unsupported-disease images, so the model cannot output 'healthy' and its ability to reject unknown conditions is NOT measured here.
- Classes with few test images have unreliable per-class metrics (see per_class_flags).
- Calibration (temperature) and thresholds were fitted on the validation split; numbers here are held-out only if this report is for the test split.
