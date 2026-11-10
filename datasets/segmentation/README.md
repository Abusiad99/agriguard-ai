# Segmentation dataset (disease localization)

Place a pixel-annotated leaf dataset here to train the disease-localization model.
Full guide: [docs/datasets/segmentation-dataset-guide.md](../../docs/datasets/segmentation-dataset-guide.md).

```
raw/
  images/            photos (.jpg .png .bmp .tif .webp), any sub-folders
  masks/             EITHER one PNG per image (same relative name, .png), one class value per pixel
  annotations/       OR COCO JSON (polygons) OR YOLO-seg .txt files (one per image)
  metadata.csv       optional: image,group_id[,split] — photos of the same plant/session share a group_id
manifests/
  class_mapping.json REQUIRED — copy class_mapping.example.json and edit
interim/             scratch space for your own conversions (not read by the pipeline)
processed/           written by preprocessing (images/, masks/) — do not edit
splits/              written by preprocessing (train.txt, validation.txt, test.txt)
reports/             validation_report.json, validation_summary.md
samples/             header templates
```

Rules that matter:
- **Annotate healthy leaf tissue** (a `leaf` class) as well as lesions if you want affected-area
  percentages. With only background/lesion the model can localize lesions but the app will
  not report "% of leaf affected".
- Masks must be single-channel (8-bit L/P) with the raw values listed in `source_values`.
  RGB color masks are rejected — convert them first.
- COCO: polygon `segmentation` only (RLE is reported as an error). Category names must match
  `name` or `source_names`. YOLO: `class x1 y1 x2 y2 ...` normalized 0-1; class index =
  `source_values`.
- Give every photo of the same plant / original picture / session the same `group_id` in
  `metadata.csv`, so they never end up in both training and test.

Commands (Windows PowerShell, from the repo root):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train      # long-running; not started automatically
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action evaluate
```

Nothing in this folder is committed except this README, the example mapping, headers and
`.gitkeep` files.
