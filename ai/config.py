"""
AgriGuard AI — Central configuration for the data & training pipeline.

Every path, threshold, and hyperparameter used anywhere in ai/ is defined here and
overridable via environment variables or a `.env` file. No module outside this file
should hardcode a dataset path, image size, or training hyperparameter.

Traceability: C1 (no hardcoded dataset paths), C9 (tunable to available hardware),
FR-DATA-1..8.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# Load .env if python-dotenv is available; never fail if it isn't.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Project root = two levels up from this file (ai/config.py -> ai/ -> repo root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PathConfig:
    """All filesystem locations. No dataset-specific names appear here (C1)."""

    project_root: Path = PROJECT_ROOT
    datasets_dir: Path = field(default_factory=lambda: Path(_env_str("AGRIGUARD_DATASETS_DIR", str(PROJECT_ROOT / "datasets"))))
    artifacts_dir: Path = field(default_factory=lambda: Path(_env_str("AGRIGUARD_ARTIFACTS_DIR", str(PROJECT_ROOT / "artifacts"))))
    cache_dir: Path = field(default_factory=lambda: Path(_env_str("AGRIGUARD_CACHE_DIR", str(PROJECT_ROOT / ".cache"))))
    logs_dir: Path = field(default_factory=lambda: Path(_env_str("AGRIGUARD_LOGS_DIR", str(PROJECT_ROOT / "logs"))))

    def ensure(self) -> None:
        for p in (self.artifacts_dir, self.cache_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class DataConfig:
    """Data pipeline behavior. FR-DATA-1..6."""

    image_extensions: tuple = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
    annotation_extensions: tuple = (".csv", ".json", ".xml", ".txt")
    min_images_per_class: int = _env_int("AGRIGUARD_MIN_IMAGES_PER_CLASS", 5)
    image_size: int = _env_int("AGRIGUARD_IMAGE_SIZE", 224)
    channels: int = 3
    train_ratio: float = _env_float("AGRIGUARD_TRAIN_RATIO", 0.70)
    val_ratio: float = _env_float("AGRIGUARD_VAL_RATIO", 0.15)
    test_ratio: float = _env_float("AGRIGUARD_TEST_RATIO", 0.15)
    duplicate_hash_threshold: int = _env_int("AGRIGUARD_DEDUP_HASH_THRESHOLD", 4)  # hamming distance
    random_seed: int = _env_int("AGRIGUARD_SEED", 42)
    normalization_mean: tuple = (0.485, 0.456, 0.406)  # ImageNet stats (pretrained backbones)
    normalization_std: tuple = (0.229, 0.224, 0.225)

    def __post_init__(self):
        total = round(self.train_ratio + self.val_ratio + self.test_ratio, 6)
        if total != 1.0:
            raise ValueError(
                f"train_ratio + val_ratio + test_ratio must equal 1.0, got {total} "
                f"({self.train_ratio} + {self.val_ratio} + {self.test_ratio})"
            )


@dataclass
class TrainConfig:
    """Training hyperparameters. Tunable per C9 (available compute)."""

    architecture: str = _env_str("AGRIGUARD_ARCHITECTURE", "efficientnet_b0")
    batch_size: int = _env_int("AGRIGUARD_BATCH_SIZE", 32)
    num_epochs: int = _env_int("AGRIGUARD_NUM_EPOCHS", 25)
    learning_rate: float = _env_float("AGRIGUARD_LR", 3e-4)
    weight_decay: float = _env_float("AGRIGUARD_WEIGHT_DECAY", 1e-4)
    early_stopping_patience: int = _env_int("AGRIGUARD_EARLY_STOP_PATIENCE", 5)
    num_workers: int = _env_int("AGRIGUARD_NUM_WORKERS", min(4, os.cpu_count() or 1))
    use_class_weighting: bool = _env_bool("AGRIGUARD_USE_CLASS_WEIGHTING", True)
    use_weighted_sampler: bool = _env_bool("AGRIGUARD_USE_WEIGHTED_SAMPLER", True)
    mixed_precision: bool = _env_bool("AGRIGUARD_MIXED_PRECISION", True)
    freeze_backbone_epochs: int = _env_int("AGRIGUARD_FREEZE_BACKBONE_EPOCHS", 2)
    device: str = _env_str("AGRIGUARD_DEVICE", "auto")  # auto|cpu|cuda|mps


@dataclass
class InferenceConfig:
    """Runtime inference thresholds. FR-AI-12, BR1."""

    plant_id_confidence_threshold: float = _env_float("AGRIGUARD_PLANT_CONF_THRESHOLD", 0.55)
    disease_low_confidence_threshold: float = _env_float("AGRIGUARD_DISEASE_LOW_CONF_THRESHOLD", 0.60)
    severity_mild_max_pct: float = _env_float("AGRIGUARD_SEVERITY_MILD_MAX", 15.0)
    severity_moderate_max_pct: float = _env_float("AGRIGUARD_SEVERITY_MODERATE_MAX", 40.0)


@dataclass
class AgriGuardConfig:
    paths: PathConfig = field(default_factory=PathConfig)
    data: DataConfig = field(default_factory=DataConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)


# Singleton config instance used across the pipeline.
CONFIG = AgriGuardConfig()
CONFIG.paths.ensure()
