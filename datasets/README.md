# Datasets

| Folder | Used for | Status |
|---|---|---|
| `plantwild_v2/` | Plant disease **classification** (`train.py`) | Present (Git LFS images) |
| `segmentation/` | Disease **localization** model | Structure only — awaiting your annotated dataset |
| `outbreak/` | Outbreak **risk** model | Structure only — awaiting your observation data |
| `recovery/` | Calibrating **recovery assessment** rules | Structure only — awaiting longitudinal data |

Each folder's README lists the exact files and the commands to validate, preprocess,
train and evaluate. The step-by-step guide is
[docs/datasets/dataset-preparation-guide.md](../docs/datasets/dataset-preparation-guide.md).

Real data files are never committed (see `.gitignore`); only READMEs, schemas, examples
and `.gitkeep` placeholders are. No fabricated data is stored here — the automated tests
generate their synthetic fixtures in temporary folders.
