"""Segmentation pipeline configuration (configs/segmentation/default.json).

Every field has a default; a JSON file overrides any subset, and CLI flags override
the file. The resolved config is saved with each training run.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, List, Optional

from ai.config import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "segmentation" / "default.json"


@dataclass
class SegmentationConfig:
    # --- model
    architecture: str = "unet"               # unet | deeplabv3plus (ai/segmentation/models.py)
    encoder: str = "efficientnet_b0"         # any timm model that supports features_only
    encoder_pretrained: bool = True          # ImageNet weights (~20 MB download on first use)
    # --- data
    image_size: int = 384                    # training/inference resolution (square)
    max_side: int = 1024                     # preprocessing caps the longest image side
    split_ratios: List[float] = field(default_factory=lambda: [0.70, 0.15, 0.15])
    near_duplicate_hamming: int = 4
    seed: int = 42
    mean: List[float] = field(default_factory=lambda: [0.485, 0.456, 0.406])
    std: List[float] = field(default_factory=lambda: [0.229, 0.224, 0.225])
    augment: dict = field(default_factory=lambda: {
        "hflip": True, "vflip": True, "rotate90": True, "scale": [0.5, 1.0], "color_jitter": 0.2})
    # --- training
    batch_size: int = 8
    epochs: int = 60
    optimizer: str = "adamw"                 # adamw | sgd
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    scheduler: str = "cosine"                # cosine | plateau | none
    loss: str = "ce_dice"                    # ce | dice | ce_dice
    class_weights: Any = "auto"              # auto (median-frequency) | none | [w0, w1, ...]
    early_stopping_patience: int = 10
    mixed_precision: bool = True             # CUDA only
    device: str = "auto"                     # auto | cpu | cuda | mps
    num_workers: int = 2
    min_train_images: int = 20               # refuse to train on less (readiness: insufficient_data)
    # --- inference
    min_leaf_pixels: int = 500               # below this leaf area no percentage is reported

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: Optional[Path] = None, **overrides) -> SegmentationConfig:
    data = {}
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(SegmentationConfig)}
    unknown = set(data) - known - {"_comment"}
    if unknown:
        raise ValueError(f"unknown segmentation config keys: {sorted(unknown)}")
    data.update({k: v for k, v in overrides.items() if v is not None})
    data.pop("_comment", None)
    return SegmentationConfig(**data)
