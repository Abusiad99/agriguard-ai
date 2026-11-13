# Dataset setup guide

The software is ready. What is missing is **data and trained models**: no trained model is
shipped with this repository, and none has been trained on real field data. This guide
tells you which data to put where, how to check it, how to train, and how to confirm the
app uses the result.

Run every command from the repository folder (`agriguard-ai`) in Windows PowerShell, after
the first-time setup in [docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md).

## 1. What you need to provide

| # | AI feature | Folder | What goes in it | Without it |
|---|---|---|---|---|
| 1 | **Disease classification** (every scan) | `datasets\plantwild_v2\` (already in the repository) plus any folder you add under `datasets\` | Leaf photos sorted into one folder per plant and condition | Scans answer "model not available" (HTTP 503). No diagnosis is invented |
| 2 | **Disease localization** (affected area) | `datasets\segmentation\` | Leaf photos with pixel-level annotations | Scans still work; the localization card says it is waiting for a trained model |
| 3 | **Outbreak risk** | `datasets\outbreak\raw\` | Dated, located field inspection records (CSV) | The map shows observed cases only; risk estimates say *model not ready* |
| 4 | **Recovery rules calibration** (optional) | `datasets\recovery\raw\` | Repeated photos of the same plants with expert labels (CSV) | Plant tracking works with the built-in rules, which have not been calibrated on real data |

Only number 1 is needed for the app's main function. Do them in this order.

Nothing in this guide downloads a dataset for you, and no fake data is ever generated in
`datasets\`. Use only data you have the right to use for training.

---

## 2. Disease classification

### 2.1 The images already in the repository

`datasets\plantwild_v2\` holds 11,488 photos in 115 folders (one per plant disease, for
example `tomato late blight`). They are stored with Git LFS, so a normal checkout may contain
small placeholder files instead of photos. Download the real files once (about 1.7 GB):

```powershell
git lfs install
```

```powershell
git lfs pull
```

**Known limit of this dataset: it has no "healthy" folders.** A model trained only on it
gives every photo a disease, including a photo of a healthy leaf. If the app should be able
to answer "healthy", add healthy-leaf photos as described next.

### 2.2 Adding your own images

Create a folder under `datasets\` with any name, and inside it one folder per class:

```
datasets\
  plantwild_v2\                 (already there)
  my_field_photos\              (your folder; any name except segmentation, outbreak, recovery)
    tomato healthy\
      IMG_0001.jpg
      IMG_0002.jpg
    tomato late blight\
      ...
    potato healthy\
      ...
```

- **The folder name is the label.** No annotation file is needed. Write the plant first, then
  the condition: `tomato late blight`, `tomato healthy`. PlantVillage-style names such as
  `Tomato___Late_blight` are also understood. Folders with the same meaning in different
  datasets are merged into one class.
- **File types:** `.jpg .jpeg .png .bmp .webp .tif .tiff`. Put the image files directly in
  the class folder: a sub-folder inside it would be read as another class. Wrapper folders
  above the class folders (`train\`, `valid\`, `test\`, `images\`) are fine; the pipeline
  makes its own split.
- **The plant must be a known plant name.** Otherwise the class is grouped under plant
  `unknown` and the check below warns you. Add new plants to `PLANT_SYNONYMS` in
  `ai\data\label_normalizer.py`.
- **How many images:** classes with fewer than 5 images are dropped
  (`AGRIGUARD_MIN_IMAGES_PER_CLASS`). The check warns below 20, because such a class is
  tested on only one to three photos. More photos, from different fields, phones and light,
  give a more reliable model.
- Corrupted files and duplicate photos are skipped automatically during training.
- Folders you add under `datasets\` are ignored by Git, so they stay on your computer.

### 2.3 Validate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action validate
```

This is read-only. It lists the dataset folders, images and classes, and reports problems:
Git LFS placeholders, unreadable images, classes that will be dropped, unknown plants, a
missing healthy class, and unbalanced classes. `RESULT: usable` means training can start.
For a slower check that opens every image and counts duplicates:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action validate -Extra "--full"
```

### 2.4 Train

```powershell
powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action train
```

- Training splits the images 70 / 15 / 15 into training, validation and test sets, trains an
  `efficientnet_b0` classifier, and tests it on the held-out test set.
- The first run downloads ImageNet starting weights (internet needed, once).
- It takes a long time on a CPU. The standard installation uses CPU PyTorch; for an NVIDIA
  GPU install the CUDA build of PyTorch from https://pytorch.org/get-started/locally/ into
  `.venv`.
- Settings are environment variables (or lines in `.env`), for example:

  ```powershell
  $env:AGRIGUARD_NUM_EPOCHS = "25"; $env:AGRIGUARD_BATCH_SIZE = "32"; $env:AGRIGUARD_DEVICE = "auto"
  ```

  The full list is in `ai\config.py`.
- Result: `artifacts\runs\<date>_efficientnet_b0\` with the model (`model.pt`), the class
  list, `metrics.json`, a confusion matrix and training curves. `artifacts\runs\latest.json`
  points to the newest run. Earlier runs are kept.

### 2.5 Evaluate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action evaluate
```

Writes accuracy, precision, recall and F1 per class for the test set into
`artifacts\runs\<run>\evaluation_test\`. **These numbers come from your data. This repository
contains no measured accuracy.** Look at the per-class results, not only the average.

---

## 3. Disease localization (segmentation)

**Provide** (details and examples: [docs/datasets/segmentation-dataset-guide.md](docs/datasets/segmentation-dataset-guide.md)):

```
datasets\segmentation\
  raw\images\                    leaf photos
  raw\masks\                     EITHER one PNG mask per photo (same name, .png, one class value per pixel)
  raw\annotations\               OR COCO JSON (polygons) OR YOLO-seg .txt files
  raw\metadata.csv               recommended: image,group_id   (photos of the same plant share a group_id)
  manifests\class_mapping.json   REQUIRED: copy class_mapping.example.json and edit it
```

Annotate healthy leaf tissue as well as lesions if you want "% of leaf affected". At least 20
training images are required for the code to run; a useful model needs far more.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action validate
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action preprocess
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action train
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action evaluate
```

`validate` writes `datasets\segmentation\reports\validation_summary.md`; fix every error it
lists before `preprocess`. Training settings: `configs\segmentation\default.json`.

---

## 4. Outbreak risk

**Provide** (columns: [docs/datasets/outbreak-dataset-schema.md](docs/datasets/outbreak-dataset-schema.md);
header templates in `datasets\outbreak\samples\`):

```
datasets\outbreak\raw\
  observations.csv     REQUIRED: observed_on, latitude, longitude, crop, disease, is_positive, ...
  weather_daily.csv    optional: daily weather near the fields
```

Include real **negative** inspections (`is_positive=0`: checked and found clean). Never add
negatives for places nobody inspected. Training refuses to run below 200 labeled rows, 30
positives, 30 negatives and one year of history (`configs\outbreak\default.json`).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action validate
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action preprocess
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action train
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action evaluate
```

To show the inspections on the app's map, load them into the application database (this
adds rows to your real database; take a backup first, see
[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md) section 3.9):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action import
```

---

## 5. Recovery rules calibration (optional)

No model is trained here. The data is used to check the rules that decide *improving /
stable / worsening* and to recommend a threshold.

**Provide** (columns: [docs/datasets/recovery-dataset-schema.md](docs/datasets/recovery-dataset-schema.md);
header templates in `datasets\recovery\samples\`):

```
datasets\recovery\raw\
  plants\plants.csv                   REQUIRED: plant_id, crop
  scans\scans.csv                     REQUIRED: scan_id, plant_id, scan_date, image_file, ...
  scans\<image files>
  treatments\treatments.csv           optional
  annotations\recovery_labels.csv     needed for calibration: expert status for pairs of scans
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action validate
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recovery-data.ps1 -Action calibrate
```

`calibrate` writes `datasets\recovery\reports\calibration_report.json`. It never changes
`configs\recovery\rules.json`; review the report and change the file yourself if justified.

---

## 6. Confirm the app uses your models

1. Ask each pipeline. `"readiness": "ready"` means a trained model is in place:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action status
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action status
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action status
   ```

2. Restart the app so it loads the new models:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
   ```

3. Open http://127.0.0.1:8000/health. `"ai_service":"ok"` means the classifier is loaded
   (`"degraded"` means no trained classifier was found).
4. Sign in as an admin or agronomist and open **Admin → AI models**
   (http://127.0.0.1:5173/admin/models). Each model shows its readiness, version, the dataset
   version it was trained on and its evaluation metrics.
5. Upload a leaf photo under **Scan Plant** and check the diagnosis.

With Docker instead of the native setup, models live in the `artifacts_data` volume and are
trained with `docker compose --profile training run --rm training`
(see [docker/README.md](docker/README.md)).

---

## 7. Rules for all datasets

1. **Rights and consent.** Use only data you may use for training. Photos from farmers need
   their consent. Keep a note of the source and licence of every dataset.
2. **No personal data.** Ids are opaque. Strip GPS data from photos you share. Outbreak
   coordinates are reduced to grid cells and never shown.
3. **Keep your originals.** The pipelines read `raw\` and never change it. `processed\`,
   `splits\`, `manifests\dataset_manifest.json` and `reports\` are regenerated; do not edit
   them by hand.
4. **Training never starts by itself.** You start it after reading the validation report.
5. **Git.** Under `datasets\`, Git tracks only the READMEs, the example and schema files and
   the existing `plantwild_v2` images. Everything you add stays local. Trained models
   (`artifacts\`) are never committed.

## 8. What stays your responsibility

- The evaluation numbers describe your test set, not performance in real fields. Check a
  model on photos from fields that were not used in training before trusting it.
- AgriGuard AI is a prototype. Its diagnoses, severity estimates, treatment texts and risk
  estimates have not been validated by agricultural experts. Have an agronomist review the
  results before anyone acts on them.
