# AI model registry

`ai/registry.py` answers one question for every AI task: *which model is installed, what
is it, and is it ready?* It only reads files. It never loads weights, so it is cheap to
call and safe at startup. It never returns a placeholder model.

## Tasks and where their runs live

| Task | Trained by | Runs | Served run marker |
|---|---|---|---|
| `classification` | `train.py` (existing) | `artifacts/runs/<run>/` | `artifacts/runs/latest.json`, or a run pinned with `AI_ARTIFACTS_RUN_DIR` |
| `segmentation` | `ai.segmentation.train` | `artifacts/segmentation/runs/<run>/` | `artifacts/segmentation/runs/latest.json` |
| `outbreak` | `ai.outbreak.train` | `artifacts/outbreak/runs/<run>/` | `artifacts/outbreak/runs/latest.json` |

`AGRIGUARD_ARTIFACTS_DIR` moves the whole `artifacts/` tree (and `AGRIGUARD_DATASETS_DIR`
the `datasets/` tree). Paths are never hard-coded to a machine.

Every training run writes a **new** timestamped folder, so existing weights are never
overwritten. Promotion (on by default, `--no-promote` to skip) only rewrites the
`latest.json` marker. To roll back, point `latest.json` at an older run folder:
`{"run_dir": "<absolute path or folder name>"}`. The segmentation and outbreak models
switch on the next request. The classifier (existing `AiPipelineClient`) needs a backend
restart.

## Model card (`model_card.json` in the run folder)

```json
{
  "name": "disease-segmentation",
  "version": "20261103_214814_unet-resnet10t",
  "architecture": "unet/resnet10t",
  "dataset_version": "9f9ae8609dbf5144",
  "training_status": "completed",
  "trained_at": "2026-11-03T21:48:19+00:00",
  "classes": ["background", "leaf", "lesion"],
  "metrics": {"validation": {"mean_iou": 0.0}, "evaluation_test": {"mean_iou": 0.0}},
  "details": {"config": {}, "class_mapping": {}}
}
```

The values above show the shape only. `dataset_version` is a content hash written by
preprocessing (`manifests/dataset_manifest.json`), so a card always says which data the
model saw. Evaluation adds its metrics to the card (`evaluation_<split>` for segmentation,
`evaluation` for outbreak).

Classification runs from the existing `train.py` have no model card. The registry
derives one from `model_meta.json`, `label_encoder.json` and `metrics.json`. The classifier
pipeline itself is unchanged.

## Readiness

| Value | Meaning |
|---|---|
| `ready` | A run is marked as served and has a card |
| `dataset_unavailable` | No prepared dataset and no model |
| `not_trained` | A dataset is prepared, but no model has been trained |
| `training_required` | The marked run has no usable card (incomplete or incompatible run) |
| `unavailable` | The run exists but failed to load in the backend (set by the backend's model clients) |
| `insufficient_data`, `not_configured`, `error` | Reserved for pipelines and clients that need them |

Order of checks: served run → prepared dataset → nothing. For classification, "dataset
present" means any image under `datasets/` outside the `segmentation/`, `outbreak/` and
`recovery/` folders. Those folders are excluded from the classification dataset scanner too.

## Where readiness is used

- `GET /api/v1/models` and `GET /api/v1/models/{task}` (login required) return the public card.
  Run paths are never included (`public_dict()` drops `run_dir`).
- The backend's `SegmentationClient` and `OutbreakModelClient` load lazily on first use,
  keep the model in memory and serialize inference with a lock. On every request they check
  the registry, and they load a newly promoted run automatically (no restart). When loading
  fails they report `unavailable` with the error, and the load is retried on the next request.
- Scans store the segmentation readiness when no model ran. Outbreak estimates return
  `model_unavailable` with the reason.
- **Admin → AI models** (`/admin/models`) shows each card: readiness, version, architecture,
  dataset version, training date, classes and numeric metrics.

## Checking from the command line

```powershell
powershell -ExecutionPolicy Bypass -File scripts\segmentation.ps1 -Action status
powershell -ExecutionPolicy Bypass -File scripts\outbreak.ps1 -Action status
```
