"""
Segmentation dataset: discovery, validation, deterministic splitting, and loading.

Expected layout (one directory per annotated dataset; see docs/SEGMENTATION.md):

    <seg_root>/<dataset_name>/
        images/<stem>.jpg|jpeg|png|webp
        masks/<stem>.png          # single-channel uint8, values 0/1/2/255 (masks.py)

Only images with a matching mask are used. Masks are validated (label values, size
equal to the image) before training; invalid pairs are reported and skipped, never
"repaired" silently. Image-level disease labels (e.g. PlantWild class folders) are
NOT segmentation annotations and are never used as such.
"""
from __future__ import annotations

import csv
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from ai.segmentation.masks import IGNORE, VALID_LABELS

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class SegSample:
    image_path: Path
    mask_path: Path
    dataset: str


@dataclass
class DiscoveryReport:
    samples: List[SegSample]
    images_without_mask: int
    invalid: List[Tuple[str, str]]  # (mask path, reason)


def discover_samples(seg_root: Path, validate: bool = True) -> DiscoveryReport:
    samples: List[SegSample] = []
    without_mask = 0
    invalid: List[Tuple[str, str]] = []
    if not seg_root.exists():
        return DiscoveryReport(samples, 0, [])
    for ds_dir in sorted(p for p in seg_root.iterdir() if p.is_dir()):
        img_dir, mask_dir = ds_dir / "images", ds_dir / "masks"
        if not img_dir.is_dir() or not mask_dir.is_dir():
            continue
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in IMAGE_EXTS:
                continue
            mask = mask_dir / f"{img.stem}.png"
            if not mask.exists():
                without_mask += 1
                continue
            if validate:
                reason = validate_pair(img, mask)
                if reason:
                    invalid.append((str(mask), reason))
                    continue
            samples.append(SegSample(img, mask, ds_dir.name))
    return DiscoveryReport(samples, without_mask, invalid)


def validate_pair(image_path: Path, mask_path: Path) -> Optional[str]:
    try:
        with Image.open(image_path) as im:
            size = im.size
        with Image.open(mask_path) as m:
            if m.mode not in ("L", "P", "I;16", "I"):
                return f"mask mode {m.mode} is not single-channel"
            if m.size != size:
                return f"mask size {m.size} != image size {size}"
            arr = np.asarray(m)
    except Exception as exc:  # noqa: BLE001
        return f"unreadable: {exc}"
    values = set(np.unique(arr).tolist())
    bad = values - VALID_LABELS
    if bad:
        return f"unexpected label values {sorted(bad)[:5]}"
    if not ({1, 2} & values):
        return "mask contains no leaf or lesion pixels"
    return None


def split_samples(samples: Sequence[SegSample], val_ratio: float = 0.15, test_ratio: float = 0.15,
                  seed: int = 42) -> dict:
    """Deterministic split by image (hash of the image bytes groups exact duplicates
    into the same split, avoiding train/test leakage from duplicated files)."""
    groups = {}
    for s in samples:
        digest = hashlib.sha256(s.image_path.read_bytes()).hexdigest()
        groups.setdefault(digest, []).append(s)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    n = len(keys)
    n_test = int(round(n * test_ratio))
    n_val = int(round(n * val_ratio))
    split_keys = {"test": keys[:n_test], "val": keys[n_test:n_test + n_val], "train": keys[n_test + n_val:]}
    return {name: [s for k in ks for s in groups[k]] for name, ks in split_keys.items()}


def write_manifest(splits: dict, path: Path) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "dataset", "image_path", "mask_path"])
        for name, items in splits.items():
            for s in items:
                w.writerow([name, s.dataset, str(s.image_path), str(s.mask_path)])


def read_manifest(path: Path) -> dict:
    splits: dict = {"train": [], "val": [], "test": []}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            splits.setdefault(row["split"], []).append(
                SegSample(Path(row["image_path"]), Path(row["mask_path"]), row["dataset"]))
    return splits


def load_pair(sample: SegSample, size: int) -> Tuple[Image.Image, Image.Image]:
    with Image.open(sample.image_path) as im:
        image = im.convert("RGB").resize((size, size), Image.BILINEAR)
    with Image.open(sample.mask_path) as m:
        mask = m.convert("L").resize((size, size), Image.NEAREST)
    return image, mask


_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def image_to_tensor(image: Image.Image) -> torch.Tensor:
    arr = (np.asarray(image, dtype=np.float32) / 255.0 - _MEAN) / _STD
    return torch.from_numpy(arr.transpose(2, 0, 1).copy())


class SegmentationDataset(Dataset):
    """Joint image/mask transforms: identical geometric augmentation for both, colour
    jitter for the image only; masks are always resized with NEAREST so labels are
    never interpolated into invalid values."""

    def __init__(self, samples: Sequence[SegSample], size: int = 256, augment: bool = False, seed: int = 0):
        self.samples = list(samples)
        self.size = size
        self.augment = augment
        self.rng = random.Random(seed)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        image, mask = load_pair(self.samples[idx], self.size)
        if self.augment:
            if self.rng.random() < 0.5:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
                mask = mask.transpose(Image.FLIP_LEFT_RIGHT)
            if self.rng.random() < 0.5:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
                mask = mask.transpose(Image.FLIP_TOP_BOTTOM)
            k = self.rng.randint(0, 3)
            if k:
                image = image.rotate(90 * k)
                mask = mask.rotate(90 * k, resample=Image.NEAREST, fillcolor=IGNORE)
            from PIL import ImageEnhance
            image = ImageEnhance.Brightness(image).enhance(self.rng.uniform(0.75, 1.25))
            image = ImageEnhance.Contrast(image).enhance(self.rng.uniform(0.8, 1.2))
        target = torch.from_numpy(np.asarray(mask, dtype=np.int64).copy())
        return image_to_tensor(image), target
