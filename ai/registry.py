"""
Model registry — one place that answers "which AI models exist, what are they, and
are they ready?" for every AI task (see docs/ai/model-registry.md).

Each training pipeline writes its runs under the artifacts directory and points a
`latest.json` marker at the run to serve:

    artifacts/runs/latest.json                  classification (train.py)
    artifacts/segmentation/runs/latest.json     disease localization (ai.segmentation.train)
    artifacts/outbreak/runs/latest.json         outbreak risk (ai.outbreak.train)

A run directory holds the weights plus `model_card.json` (name, version, architecture,
dataset version, classes, metrics, training status). The registry only READS these
files; it never loads weights, so describing the models is cheap and safe at startup.

Readiness is reported honestly: a task with no model is NOT ready, and the reason is
explicit (no dataset, dataset present but not trained, ...). Nothing here returns a
placeholder model.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from ai.config import CONFIG


class Readiness(str, Enum):
    NOT_CONFIGURED = "not_configured"          # task disabled / no artifacts location
    DATASET_UNAVAILABLE = "dataset_unavailable"  # no prepared dataset and no model
    NOT_TRAINED = "not_trained"                # dataset prepared, no trained model yet
    TRAINING_REQUIRED = "training_required"    # a model exists but is unusable (e.g. incompatible / incomplete run)
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"    # dataset too small to train responsibly
    UNAVAILABLE = "unavailable"                # model exists but failed to load
    ERROR = "error"


TASKS = ("classification", "segmentation", "outbreak")

# Where each task keeps its runs (relative to the artifacts dir) and its dataset
# readiness marker (relative to the datasets dir).
_RUNS_SUBDIR = {"classification": "runs", "segmentation": "segmentation/runs", "outbreak": "outbreak/runs"}
_DATASET_MARKER = {
    "classification": None,  # any images under datasets/ (see _classification_dataset_present)
    "segmentation": "segmentation/manifests/dataset_manifest.json",
    "outbreak": "outbreak/manifests/dataset_manifest.json",
}


@dataclass
class ModelCard:
    task: str
    readiness: Readiness
    message: str
    name: Optional[str] = None
    version: Optional[str] = None
    architecture: Optional[str] = None
    dataset_version: Optional[str] = None
    training_status: Optional[str] = None
    trained_at: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)
    details: Dict = field(default_factory=dict)
    # Local only — never serialized to API responses (public_dict drops it).
    run_dir: Optional[Path] = None

    @property
    def is_ready(self) -> bool:
        return self.readiness == Readiness.READY

    def public_dict(self) -> dict:
        data = asdict(self)
        data.pop("run_dir", None)
        data["readiness"] = self.readiness.value
        return data


def runs_dir(task: str) -> Path:
    return CONFIG.paths.artifacts_dir / _RUNS_SUBDIR[task]


def latest_run_dir(task: str) -> Optional[Path]:
    """Run directory recorded in the task's latest.json, or None if there is no
    usable marker. Relative paths in the marker are resolved against the runs dir."""
    marker = runs_dir(task) / "latest.json"
    if not marker.is_file():
        return None
    try:
        recorded = Path(json.loads(marker.read_text(encoding="utf-8"))["run_dir"])
    except (ValueError, KeyError, TypeError):
        return None
    run_dir = recorded if recorded.is_absolute() else runs_dir(task) / recorded
    return run_dir if run_dir.is_dir() else None


def mark_latest(task: str, run_dir: Path) -> None:
    base = runs_dir(task)
    base.mkdir(parents=True, exist_ok=True)
    try:
        value = str(run_dir.resolve().relative_to(base.resolve()))
    except ValueError:
        value = str(run_dir.resolve())
    (base / "latest.json").write_text(json.dumps({"run_dir": value}, indent=2), encoding="utf-8")


def read_model_card(run_dir: Path) -> dict:
    path = run_dir / "model_card.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _dataset_present(task: str) -> bool:
    if task == "classification":
        from ai.data.dataset_scanner import NON_CLASSIFICATION_DIRS

        datasets = CONFIG.paths.datasets_dir
        roots = [p for p in datasets.iterdir() if p.is_dir() and p.name not in NON_CLASSIFICATION_DIRS]             if datasets.is_dir() else []
        return any(p.suffix.lower() in CONFIG.data.image_extensions
                   for root in roots for p in root.rglob("*") if p.is_file())
    marker = _DATASET_MARKER[task]
    return (CONFIG.paths.datasets_dir / marker).is_file()


def _card_from_run(task: str, run_dir: Path) -> ModelCard:
    card = read_model_card(run_dir)
    if task == "classification" and not card:
        # Runs from train.py predate model cards; derive the card from their files.
        meta = _read_json(run_dir / "model_meta.json")
        classes = _read_json(run_dir / "label_encoder.json").get("classes", [])
        metrics = _read_json(run_dir / "metrics.json")
        card = {
            "name": "plant-disease-classifier", "version": run_dir.name,
            "architecture": meta.get("architecture"), "classes": classes,
            "metrics": {**{k: metrics[k] for k in ("accuracy", "macro_f1", "weighted_f1") if k in metrics},
                        **{alias: metrics[k] for k, alias in (("f1_macro", "macro_f1"), ("f1_weighted", "weighted_f1"))
                           if k in metrics and alias not in metrics}},
            "training_status": "completed" if meta else "unknown",
            # Test/development stubs say so in their metadata; reports flag them.
            "details": {"synthetic": True} if "SYNTHETIC" in str(meta.get("note", "")).upper() else {},
        }
    if not card:
        return ModelCard(task=task, readiness=Readiness.TRAINING_REQUIRED, run_dir=run_dir,
                         message="The recorded model run has no model card; retrain or re-export it.")
    return ModelCard(
        task=task, readiness=Readiness.READY, message="Model is trained and available.", run_dir=run_dir,
        name=card.get("name"), version=card.get("version"), architecture=card.get("architecture"),
        dataset_version=card.get("dataset_version"), training_status=card.get("training_status", "completed"),
        trained_at=card.get("trained_at"), classes=list(card.get("classes", [])),
        metrics=dict(card.get("metrics", {})), details=dict(card.get("details", {})),
    )


def describe(task: str, run_dir: Optional[Path] = None) -> ModelCard:
    """Card for `run_dir` when given (e.g. a run pinned by the backend's
    AI_ARTIFACTS_RUN_DIR), otherwise for the run in the task's latest.json."""
    if task not in TASKS:
        raise ValueError(f"Unknown AI task '{task}'. Known: {TASKS}")
    run_dir = run_dir if run_dir is not None and run_dir.is_dir() else latest_run_dir(task)
    if run_dir is not None:
        return _card_from_run(task, run_dir)
    if _dataset_present(task):
        return ModelCard(task=task, readiness=Readiness.NOT_TRAINED,
                         message="A dataset is prepared but no model has been trained yet.")
    return ModelCard(task=task, readiness=Readiness.DATASET_UNAVAILABLE,
                     message="No dataset has been prepared and no trained model exists yet.")


def describe_all() -> List[ModelCard]:
    return [describe(task) for task in TASKS]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
