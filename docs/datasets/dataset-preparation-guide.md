# Dataset preparation guide

AgriGuard's AI features each need different data. This page is the overview. The linked
pages hold the exact formats.

| Feature | Folder | Data | Needed for | Guide |
|---|---|---|---|---|
| Disease classification (existing) | `datasets/<your dataset>/<plant>___<condition>/` | Labeled photos | `train.py` | README → *The AI model* |
| Disease localization | `datasets/segmentation/` | Photos + pixel annotations | Training the segmentation model | [segmentation-dataset-guide.md](segmentation-dataset-guide.md) |
| Outbreak risk | `datasets/outbreak/` | Dated, located inspections with real negatives; optional daily weather | Training the risk model; filling the map | [outbreak-dataset-schema.md](outbreak-dataset-schema.md) |
| Recovery monitoring | `datasets/recovery/` | Repeated photos of the same plants + expert pair labels | Calibrating the rules (optional) | [recovery-dataset-schema.md](recovery-dataset-schema.md) |

The classification scanner ignores the `segmentation/`, `outbreak/` and `recovery/` folders,
so adding feature data never changes the classifier's classes.

## General rules

1. **Rights and consent.** Use only data you may use for training. Photos from farmers need
   their consent. Record the source and licence of public datasets in your own notes (for
   example in `interim/`).
2. **No personal data.** Ids are opaque. Locations are only as precise as needed, and the
   outbreak pipeline snaps them to grid cells. Strip EXIF GPS from photos you share.
3. **Keep raw data raw.** Put originals in `raw/`, your conversions in `interim/`, and never
   edit `processed/`, `splits/`, `manifests/dataset_manifest.json` or `reports/` by hand.
   They are regenerated.
4. **No leakage.** Photos of the same plant, the same original picture or the same session
   must share a `group_id` (segmentation) so they stay in one split. Outbreak data is split
   by date.
5. **Version your data.** Preprocessing writes a content hash (`dataset_version`). Every
   trained model card records it, so results trace back to the data.
6. **Nothing large is downloaded automatically.** No script fetches datasets. Encoder
   pretrained weights are the only download, and only when training starts with
   `encoder_pretrained: true`.
7. **Training never starts by itself.** Run it explicitly when you have reviewed the
   validation report.

## Typical workflow

```powershell
# 1. Put the files in datasets\<feature>\raw\ (+ class_mapping.json for segmentation)
# 2. Validate and read reports\validation_summary.md
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
# 3. Fix errors, then preprocess
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess
# 4. Train (long) and evaluate
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action evaluate
# 5. Check readiness (also visible under Admin → AI models)
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action status
```

`scripts\outbreak.ps1` and `scripts\recovery-data.ps1` follow the same pattern. See the
feature pages for their extra actions (`import`, `backfill`, `calibrate`).

## What is tracked by Git

Under `datasets/` only `README.md` files, `.gitkeep` placeholders,
`segmentation/manifests/class_mapping.example.json`, `*/schemas/*.json` and
`*/samples/*.header.csv` are tracked. The existing tracked classification images are unchanged.
Everything else you add stays local (see `.gitignore`).
