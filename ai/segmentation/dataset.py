"""Torch dataset over processed/ + splits/, with augmentation applied identically to
image and mask (geometry) and to the image only (color). Masks are always resampled
with NEAREST so class ids are never interpolated."""
from __future__ import annotations

import random
from pathlib import Path
from typing import List

import numpy as np
import torch
import torchvision.transforms.functional as TF
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms as T

from ai.segmentation.config import SegmentationConfig


def read_split(root: Path, split: str) -> List[str]:
    path = Path(root) / "splits" / f"{split}.txt"
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(image: Image.Image, config: SegmentationConfig) -> torch.Tensor:
    return TF.normalize(TF.to_tensor(image), config.mean, config.std)


class JointTransform:
    def __init__(self, config: SegmentationConfig, train: bool):
        self.config, self.train = config, train
        self.size = (config.image_size, config.image_size)
        aug = config.augment or {}
        jitter = float(aug.get("color_jitter", 0) or 0)
        self.color = T.ColorJitter(jitter, jitter, jitter, min(jitter, 0.1)) if jitter else None
        self.scale = tuple(aug.get("scale", [1.0, 1.0]))

    def __call__(self, image: Image.Image, mask: Image.Image):
        aug = self.config.augment or {}
        if self.train:
            i, j, h, w = T.RandomResizedCrop.get_params(image, scale=self.scale, ratio=(3 / 4, 4 / 3))
            image = TF.resized_crop(image, i, j, h, w, self.size, interpolation=T.InterpolationMode.BILINEAR)
            mask = TF.resized_crop(mask, i, j, h, w, self.size, interpolation=T.InterpolationMode.NEAREST)
            if aug.get("hflip") and random.random() < 0.5:
                image, mask = TF.hflip(image), TF.hflip(mask)
            if aug.get("vflip") and random.random() < 0.5:
                image, mask = TF.vflip(image), TF.vflip(mask)
            if aug.get("rotate90"):
                k = random.randint(0, 3)
                if k:
                    image, mask = image.rotate(90 * k, expand=True), mask.rotate(90 * k, expand=True)
            if self.color is not None:
                image = self.color(image)
        else:
            image = TF.resize(image, self.size, interpolation=T.InterpolationMode.BILINEAR)
            mask = TF.resize(mask, self.size, interpolation=T.InterpolationMode.NEAREST)
        return normalize(image, self.config), torch.from_numpy(np.asarray(mask, dtype=np.int64).copy())


class SegmentationDataset(Dataset):
    def __init__(self, root: Path, split: str, config: SegmentationConfig, train: bool):
        self.root = Path(root)
        self.keys = read_split(self.root, split)
        self.transform = JointTransform(config, train)

    def __len__(self) -> int:
        return len(self.keys)

    def load_pair(self, index: int):
        key = self.keys[index]
        with Image.open(self.root / "processed" / "images" / f"{key}.png") as im:
            image = im.convert("RGB")
        with Image.open(self.root / "processed" / "masks" / f"{key}.png") as m:
            mask = m.copy()
        return image, mask

    def __getitem__(self, index: int):
        image, mask = self.load_pair(index)
        return self.transform(image, mask)
