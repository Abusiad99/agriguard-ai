"""
Preprocessing & Augmentation (FR-DATA-5, and general resize/normalize requirements).

- `build_eval_transform`: resize + normalize only. Used for validation, test, and
  production inference — MUST be identical at train-eval time and at inference time,
  which is why both `evaluate.py` and `inference.py` import this same function rather
  than each defining their own resize/normalize logic.
- `build_train_transform`: resize + the full augmentation stack (rotation, flip, crop,
  brightness/contrast/color jitter, Gaussian noise, zoom, blur) + normalize. Applied
  ONLY to the training split, never to validation/test/inference (per requirement:
  "Apply Data Augmentation ONLY to the training set").

The exact parameters used here are also saved into the PreprocessingConfig artifact
(see artifact_manager.py) so a loaded model always knows precisely how to preprocess
new images at inference time, even months later on a different machine.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

import torch
from torchvision import transforms

from ai.config import CONFIG


@dataclass
class PreprocessingConfig:
    image_size: int
    mean: tuple
    std: tuple

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "PreprocessingConfig":
        data = json.loads(path.read_text())
        return cls(image_size=data["image_size"], mean=tuple(data["mean"]), std=tuple(data["std"]))

    @classmethod
    def from_global_config(cls) -> "PreprocessingConfig":
        return cls(
            image_size=CONFIG.data.image_size,
            mean=CONFIG.data.normalization_mean,
            std=CONFIG.data.normalization_std,
        )


class GaussianNoise:
    """Additive Gaussian noise transform (torchvision has no built-in for this)."""

    def __init__(self, mean: float = 0.0, std: float = 0.02):
        self.mean = mean
        self.std = std

    def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
        noise = torch.randn_like(tensor) * self.std + self.mean
        return torch.clamp(tensor + noise, 0.0, 1.0)


def build_eval_transform(preproc: PreprocessingConfig | None = None) -> transforms.Compose:
    preproc = preproc or PreprocessingConfig.from_global_config()
    return transforms.Compose([
        transforms.Resize((preproc.image_size, preproc.image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=preproc.mean, std=preproc.std),
    ])


def build_train_transform(preproc: PreprocessingConfig | None = None) -> transforms.Compose:
    """Resize + full augmentation stack, applied to TRAIN split only (FR-DATA-5)."""
    preproc = preproc or PreprocessingConfig.from_global_config()
    return transforms.Compose([
        transforms.Resize((int(preproc.image_size * 1.15), int(preproc.image_size * 1.15))),
        transforms.RandomCrop((preproc.image_size, preproc.image_size)),      # Random Crop
        transforms.RandomHorizontalFlip(p=0.5),                               # Horizontal Flip
        transforms.RandomRotation(degrees=25),                                # Rotation
        transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.05),  # Brightness/Contrast/Color Jitter
        transforms.RandomApply([transforms.GaussianBlur(kernel_size=3)], p=0.2),  # Blur
        transforms.RandomApply(
            [transforms.RandomAffine(degrees=0, scale=(0.85, 1.15))], p=0.3
        ),                                                                    # Zoom (via scale)
        transforms.ToTensor(),
        GaussianNoise(std=0.015),                                             # Gaussian Noise
        transforms.Normalize(mean=preproc.mean, std=preproc.std),
    ])
