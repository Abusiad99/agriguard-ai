"""
ArtifactManager — creates a timestamped run directory and saves every required
training artifact into it (requirements: "Save trained models", "Save preprocessing
objects", "Save label encoders", "Save training history", "Save confusion matrix",
"Save Precision, Recall, F1-Score", "Save training graphs"; FR-DATA-8).

Run directory layout:
  artifacts/runs/<timestamp>_<architecture>/
    model.pt                     -- trained model weights (state_dict)
    model_meta.json               -- architecture name, num_classes, image_size
    label_encoder.json            -- class list (LabelEncoder.save)
    preprocessing_config.json     -- resize/normalize params (PreprocessingConfig.save)
    training_history.json         -- per-epoch train/val loss & accuracy
    metrics.json                  -- final accuracy/precision/recall/F1 (macro/weighted/per-class)
    confusion_matrix.png
    training_curves.png
    unified_dataset_index.csv     -- copy of the exact data the run trained on (audit trail)
    run_config.json               -- full resolved AgriGuardConfig used for this run
  artifacts/runs/latest -> symlink (or copy on platforms without symlink support)
    to the most recent run directory, so inference.py always loads the newest model
    without needing to know the timestamp.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import torch

from ai.config import CONFIG
from ai.data.label_encoder import LabelEncoder
from ai.data.preprocessing import PreprocessingConfig
from ai.training.metrics import EvaluationMetrics
from ai.training.visualization import plot_confusion_matrix, plot_training_curves


class ArtifactManager:
    def __init__(self, architecture: str, base_dir: Path | None = None):
        self.architecture = architecture
        self.base_dir = base_dir or (CONFIG.paths.artifacts_dir / "runs")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = self.base_dir / f"{timestamp}_{architecture}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save_model(self, model: torch.nn.Module, num_classes: int, image_size: int) -> Path:
        model_path = self.run_dir / "model.pt"
        torch.save(model.state_dict(), model_path)
        meta = {"architecture": self.architecture, "num_classes": num_classes, "image_size": image_size}
        (self.run_dir / "model_meta.json").write_text(json.dumps(meta, indent=2))
        return model_path

    def save_label_encoder(self, encoder: LabelEncoder) -> Path:
        path = self.run_dir / "label_encoder.json"
        encoder.save(path)
        return path

    def save_preprocessing_config(self, preproc: PreprocessingConfig) -> Path:
        path = self.run_dir / "preprocessing_config.json"
        preproc.save(path)
        return path

    def save_training_history(self, history: Dict[str, List[float]]) -> Path:
        path = self.run_dir / "training_history.json"
        path.write_text(json.dumps(history, indent=2))
        plot_training_curves(history, self.run_dir / "training_curves.png")
        return path

    def save_metrics(self, metrics: EvaluationMetrics) -> Path:
        path = self.run_dir / "metrics.json"
        path.write_text(json.dumps(metrics.to_json_dict(), indent=2))
        plot_confusion_matrix(metrics.confusion_matrix, metrics.class_names, self.run_dir / "confusion_matrix.png")
        return path

    def copy_dataset_index(self, index_csv_path: Path) -> None:
        if index_csv_path.exists():
            shutil.copy2(index_csv_path, self.run_dir / "unified_dataset_index.csv")

    def save_run_config(self) -> None:
        path = self.run_dir / "run_config.json"
        cfg_dict = {
            "paths": {k: str(v) for k, v in dataclasses.asdict(CONFIG.paths).items()},
            "data": dataclasses.asdict(CONFIG.data),
            "train": dataclasses.asdict(CONFIG.train),
            "inference": dataclasses.asdict(CONFIG.inference),
        }
        path.write_text(json.dumps(cfg_dict, indent=2, default=str))

    def mark_as_latest(self) -> None:
        """Point artifacts/runs/latest at this run directory. Uses a copied marker
        file (not a symlink) for cross-platform reliability (NFR-PORT-1: Windows/
        WSL2 hosts don't always support symlinks without elevated privileges)."""
        latest_marker = self.base_dir / "latest.json"
        latest_marker.write_text(json.dumps({"run_dir": str(self.run_dir)}, indent=2))

    @staticmethod
    def load_latest_run_dir(base_dir: Path | None = None) -> Path:
        base_dir = base_dir or (CONFIG.paths.artifacts_dir / "runs")
        marker = base_dir / "latest.json"
        if not marker.exists():
            raise FileNotFoundError(
                f"No trained model run found at '{base_dir}'. Run `python train.py` first."
            )
        data = json.loads(marker.read_text())
        run_dir = Path(data["run_dir"])
        if not run_dir.exists():
            raise FileNotFoundError(f"Recorded latest run directory '{run_dir}' no longer exists.")
        return run_dir
