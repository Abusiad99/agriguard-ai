# Datasets

**Start with [DATASET_SETUP_GUIDE.md](../DATASET_SETUP_GUIDE.md).** It says what to put where,
how to check it, how to train, and how to confirm the app uses the result.

| Folder | Used for | Status in the repository |
|---|---|---|
| `plantwild_v2/` | Plant disease **classification** | 11,488 images in 115 disease folders, stored with Git LFS (`git lfs pull` downloads them). No "healthy" folders |
| any other folder you add | More classification images (`<your folder>/<plant> <condition>/*.jpg`) | Yours; ignored by Git |
| `segmentation/` | Disease **localization** model | Structure only; needs your annotated dataset |
| `outbreak/` | Outbreak **risk** model | Structure only; needs your inspection records |
| `recovery/` | Calibrating the **recovery** rules (optional) | Structure only; needs your longitudinal data |

Check the classification images (read-only):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\classification.ps1 -Action validate
```

The other three folders each have a README with their files and commands.

Real data files are never committed (see `.gitignore`); only READMEs, schemas, examples
and `.gitkeep` placeholders are. No fabricated data is stored here: the automated tests
generate their synthetic fixtures in temporary folders.
