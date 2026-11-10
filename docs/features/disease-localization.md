# Disease localization and affected-area segmentation

A **separate segmentation model** outlines visible symptoms pixel by pixel on every scan.
It sits next to the existing classifier and never changes the diagnosis.

| Milestone | Status |
|---|---|
| Software (pipeline, API, UI, migrations, tests) | Complete |
| Dataset integration | Waiting for a pixel-annotated dataset in `datasets/segmentation/` |
| Training | Not started. It needs that dataset, and training is never started automatically |
| Evaluation on real data | Not done |
| Production readiness | Not claimed |

Until a model is trained, every scan records `segmentation.status = "dataset_unavailable"`
(or `not_trained`), and the result page says localization is waiting for a model.

## Grad-CAM is not segmentation

The classifier's Grad-CAM heatmap shows *which pixels influenced the class decision*. It is
an explanation, not a measurement. The existing `severity_level` / `affected_area_pct` on a
diagnosis come from a thresholded Grad-CAM map. For that reason:

- the API now returns `severity_method: "explainability_heatmap"` with those fields
  (`null` for a healthy prediction: no heatmap is made for it, and its 0 % / 100 % are the
  classifier's healthy result, not an estimate);
- the result page captions the heatmap as an attention map and labels the percentage
  "Estimated from the attention heatmap, not measured";
- the measured value is `segmentation.affected_area_pct`, shown separately.

The existing fields are unchanged (backward compatible).

## How a scan is processed

1. The classifier runs as before.
2. `ai/image_quality.py` records size, brightness and sharpness (`diagnoses.image_quality_json`).
   Issues: `too_small` (< 224 px), `too_dark`, `overexposed`, `blurry`.
3. If the segmentation model is ready, `SegmentationService.segment()` predicts a class mask.
   The mask is limited to 2048 px per side. The service then computes:
   - `affected_pixels` (all `disease` classes) and `plant_pixels` (disease + `leaf` classes);
   - `affected_area_pct = affected / plant × 100`. This is **only** reported when the
     model has a `leaf` class and enough plant pixels were found. Otherwise the reason is
     given (`model_does_not_segment_leaf_tissue`, `too_little_plant_tissue_detected`);
   - connected regions (label, pixels, bounding box, mean confidence);
   - mean confidence and mean uncertainty (normalized entropy).
4. Three PNGs are written to `storage/segmentations/<uuid>/`: `mask.png` (binary),
   `overlay.png` (disease classes in color, transparent elsewhere) and `contours.png`.
5. One row is saved in `diagnosis_segmentations`. A failure is stored as `status = "failed"`
   and never fails the scan.

## Privacy

The segmentation PNGs are served by
`GET /api/v1/diagnoses/{id}/segmentation/{mask|overlay|contours}` to the owner or an admin
only, with `Cache-Control: private`. The frontend fetches them with the auth header as
blobs.

Scan photos and Grad-CAM heatmaps are private too. The public `/storage/scans` and
`/storage/heatmaps` mounts are **off** by default (`LEGACY_PUBLIC_MEDIA=false`). The API now
returns signed links, `/api/v1/media/<key>?exp=<unix time>&sig=<HMAC>`, only to a viewer
allowed to see the scan (the owner or an admin).
- Each link is bound to one file and expires after `MEDIA_URL_TTL_SECONDS` (default 3600).
- Files are served with `Cache-Control: private` (never cached past the link's expiry) and
  `Referrer-Policy: no-referrer`.
- A changed path, expiry or signature returns 403, and path traversal is rejected.

The JSON fields (`image_url`, `heatmap_url`) keep their names, so existing clients keep
working; they just receive the signed URL instead of `/storage/...`. Old bookmarked
`/storage/...` links stop working. `LEGACY_PUBLIC_MEDIA=true` brings them back and makes
every scan photo public again. It exists only as a temporary fallback.

Photos are stored upright: an EXIF orientation tag is applied before the image is saved, so
the classifier, the heatmap, the segmentation mask and the displayed photo use the same pixel
grid.

## API

`GET /api/v1/diagnoses/{id}` and `POST /api/v1/scans` now also return:

```json
"severity_method": "explainability_heatmap",
"image_quality": {"width": 1024, "height": 768, "mean_luma": 112.4, "sharpness": 431.0, "issues": [], "acceptable": true},
"segmentation": {
  "status": "ok",                       // or dataset_unavailable | not_trained | unavailable | failed
  "model_name": "disease-segmentation", "model_version": "20261103_214814_unet-resnet10t",
  "affected_pixels": 2619, "plant_pixels": 48211, "affected_area_pct": 5.43,
  "area_basis": "plant_pixels", "area_unavailable_reason": null,
  "mean_confidence": 0.81, "mean_uncertainty": 0.22,
  "classes": [{"id": 2, "name": "lesion", "kind": "disease", "color": [220, 38, 38]}],
  "regions": [{"label": "lesion", "class_id": 2, "pixels": 812, "bbox": {"x_min": 10, "y_min": 4, "x_max": 60, "y_max": 41}, "mean_confidence": 0.86}],
  "artifacts": {"mask": "/api/v1/diagnoses/<id>/segmentation/mask", "overlay": "...", "contours": "..."}
},
"viewer_is_owner": true
```

The example values are illustrative, not results.

## Frontend

On the diagnosis page, the *Affected-area localization* card offers Overlay / Original / Mask /
Outlines views, an opacity slider, zoom, and per-class toggles (recolored on a canvas, with no
extra requests). It also shows the area or the reason it is unavailable, pixel counts,
confidence, uncertainty, the model version and the region list. Without a ready model it shows
the readiness state instead. The photo-quality warning appears above it when a photo has issues.

## Pipeline commands

See [segmentation-dataset-guide.md](../datasets/segmentation-dataset-guide.md) for the
dataset format.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train      # long-running
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action evaluate
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action status
```

`-Extra` passes options through, for example `-Extra "--epochs 30 --device cuda"`. Quote the
whole value once: `-Extra "--split validation --allow-dataset-mismatch"`. The modules are
`ai.segmentation.{validate,preprocess,train,evaluate}`.

- **Models**: U-Net or DeepLabV3+ decoders on a timm encoder (`efficientnet_b0` by default,
  ImageNet weights when available; `encoder_pretrained: false` trains from scratch).
- **Loss**: cross-entropy + Dice, with median-frequency class weights (`class_weights: auto`).
- **Splits**: grouped by `group_id` and by exact and near-duplicate images, so the same
  plant never appears in two splits.
- **Outputs**: `artifacts/segmentation/runs/<timestamp>_<arch>-<encoder>/` holds `best.pt`,
  `last.pt`, `history.json`, `model_card.json` and the config. Each run is a new folder, so
  existing weights are never overwritten. Promotion to the served model writes
  `artifacts/segmentation/runs/latest.json` (`--no-promote` skips it).
- **Evaluation** writes `evaluation/<split>/` with `metrics.json` (IoU, Dice, precision, recall
  per class, pixel accuracy), `per_class.csv`, a confusion matrix, example overlays and the
  worst failures.
  - `metrics.json` also records `dataset_version`, `trained_dataset_version` and `resolution`.
  - The processed dataset version is a hash of every image, mask **and split assignment**. If
    it differs from the version the model was trained on, evaluate stops, because test images
    may have been training images.
  - `--allow-dataset-mismatch` overrides this and records `dataset_mismatch: true`.

The backend switches to a newly promoted model on the next scan; no restart is needed.

## Limitations

- The percentage is a 2-D pixel ratio on one photo. It depends on angle, distance and
  which leaves are in frame.
- Quality checks are heuristics (resolution, brightness, Laplacian variance). They don't
  detect wrong framing.
- A model is only as good as its annotations. Check the per-class metrics from `evaluate`
  before trusting area numbers.
