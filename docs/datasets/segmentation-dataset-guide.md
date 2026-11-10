# Segmentation dataset guide (disease localization)

The localization model needs photos of leaves with **pixel-level annotations**: which pixels
are lesion or disease, and ideally which are healthy leaf. Image-level labels (the
classification dataset) are not enough.

## What to provide

| Item | Required | Notes |
|---|---|---|
| Photos | Yes | `.jpg .jpeg .png .bmp .tif .tiff .webp`, any sub-folders under `raw/images/` |
| Annotations | Yes | One of three formats below |
| `manifests/class_mapping.json` | Yes | Copy `class_mapping.example.json` and edit |
| `raw/metadata.csv` | Strongly recommended | `image,group_id[,split]`. Photos of the same plant, the same original picture (crops or augmentations) or the same session share a `group_id` |

The pipeline enforces a minimum of 20 training images (`min_train_images`). A useful model
needs far more: plan on hundreds of annotated photos per disease, from several fields,
devices and lighting conditions. Have experts check annotations of a few images by
overlaying them before you annotate everything.

### Annotation formats

1. **Masks** (`raw/masks/`): one single-channel PNG per image, with the same relative path
   and name but a `.png` extension. Each pixel holds a raw class value listed in
   `source_values`. 8-bit `L` or palette `P` mode is accepted. RGB color masks are rejected:
   convert them to class values first.
2. **COCO** (`raw/annotations/*.json`): polygon `segmentation` only (RLE is reported as an
   error). Category names must match a class `name` or one of its `source_names`.
3. **YOLO-seg** (`raw/annotations/<image stem>.txt`): `class x1 y1 x2 y2 …` normalized to
   0–1. The class index is matched against `source_values`.

For polygon formats, leaf polygons are drawn first and disease polygons on top, so a lesion
inside a leaf keeps its lesion class.

**Photo orientation.** Photos are used upright: an EXIF orientation tag (common on phone
photos) is applied before validation and training, the same way the app treats scans. Your
masks and polygons must match the photo *as it is displayed*. Most annotation tools work that
way. Rotated photos are listed as `exif_orientation` warnings so you can spot-check them.

### Class mapping

```json
{
  "version": 1,
  "ignore_values": [255],
  "classes": [
    {"id": 0, "name": "background",   "kind": "background", "color": [0, 0, 0],      "source_values": [0], "source_names": ["background"]},
    {"id": 1, "name": "healthy_leaf", "kind": "leaf",       "color": [46, 139, 87],  "source_values": [1], "source_names": ["leaf"]},
    {"id": 2, "name": "late_blight",  "kind": "disease",    "color": [220, 38, 38],  "source_values": [2], "source_names": ["late_blight_lesion"]}
  ]
}
```

- `id`s are the training ids, `0..N-1` and contiguous. Exactly one `background` class.
- `kind` is `background`, `leaf` or `disease`. **Annotate healthy leaf tissue (`leaf`)** if
  you want "% of leaf affected". Without a leaf class the app shows lesion outlines but
  reports no percentage.
- `ignore_values` are raw values excluded from loss and metrics (for example uncertain
  borders).
- `color` is only used to draw overlays. Disease classes are shown in their color.
- Disease names should use the app's condition names (for example `late_blight`), so they
  read consistently across features. Existing classifier labels are not changed by this
  mapping.

## Folder layout

```
datasets/segmentation/
  raw/images/  raw/masks/  raw/annotations/  raw/metadata.csv
  manifests/class_mapping.json          (you)       dataset_manifest.json   (preprocessing)
  interim/                               your own conversion scratch space (never read)
  processed/images/  processed/masks/    written by preprocessing
  splits/train.txt validation.txt test.txt
  reports/validation_report.json  validation_summary.md
```

Only READMEs, the example mapping, header templates and `.gitkeep` files are tracked by Git.
Your data stays local.

## Step 1 — validate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
```

This writes `reports/validation_report.json` and a readable `validation_summary.md` with per-class
pixel and image counts.

| Errors (block preprocessing) | Warnings |
|---|---|
| `missing_class_mapping`, `invalid_class_mapping`, `dataset_empty`, `missing_image`, `corrupt_image`, `invalid_image_format`, `missing_mask`, `invalid_mask_format`, `dimension_mismatch`, `unexpected_class_id`, `invalid_polygon` | `duplicate_image`, `near_duplicate`, `extension_mismatch`, `exif_orientation`, `empty_mask`, `image_without_annotations`, `leaf_class_unused`, `class_absent`, `class_imbalance` |

## Step 2 — preprocess

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess -Extra "--exclude-invalid"
```

The step refuses to run while there are validation errors, unless `--exclude-invalid` is given.
In that case invalid samples are left out and listed in the manifest. It then:

- converts masks to training ids (nearest-neighbour only, no interpolated labels) and caps
  the long side at `max_side`;
- groups samples by `group_id`, exact duplicates and near-duplicates (perceptual hash), so a
  group never spans two splits. A `split` column in `metadata.csv` is respected;
- writes `processed/`, `splits/` and `manifests/dataset_manifest.json`. The manifest holds a
  content-hash `dataset_version`, split sizes and per-split class pixels.

Raw files are never modified. Only `*.png` files inside `processed/` are replaced on re-runs.

## Step 3 — train (long-running; never started automatically)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train -Extra "--epochs 30 --device cuda"
```

`configs/segmentation/default.json` controls architecture (`unet`, `deeplabv3plus`), encoder,
image size, augmentation, loss, class weights, early stopping and mixed precision.
`--resume <run>` continues an interrupted run. Downloading ImageNet encoder weights is a
network download handled by timm. Set `encoder_pretrained: false` to avoid it.

## Step 4 — evaluate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action evaluate
```

This writes `<run>/evaluation/test/`: `metrics.json` (IoU, Dice, precision and recall per class,
mean IoU and Dice with and without background, pixel accuracy), `per_class.csv`, a confusion
matrix, example overlays, the worst-scoring images (`failures/`) and dataset statistics.
Review per-class IoU for each disease before relying on area numbers.
