"""
Shared helpers for calibrate.py / evaluate.py: load a trained run and compute logits
for a list of images, caching them on disk keyed by (weights hash, data fingerprint)
so calibration and evaluation never recompute the same forward passes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from ai.config import CONFIG
from ai.data.label_encoder import LabelEncoder
from ai.data.preprocessing import PreprocessingConfig, build_eval_transform
from ai.models.architectures import build_classifier, resolve_device

logger = logging.getLogger("agriguard.evaluation")


@dataclass
class ModelBundle:
    run_dir: Path
    model: torch.nn.Module
    label_encoder: LabelEncoder
    preprocessing: PreprocessingConfig
    architecture: str
    weights_sha256: str
    device: torch.device

    @property
    def model_version(self) -> str:
        return f"{self.run_dir.name}:{self.weights_sha256[:12]}"


def load_bundle(run_dir: Path) -> ModelBundle:
    meta = json.loads((run_dir / "model_meta.json").read_text())
    encoder = LabelEncoder.load(run_dir / "label_encoder.json")
    preproc = PreprocessingConfig.load(run_dir / "preprocessing_config.json")
    device = resolve_device(CONFIG.train.device)
    model = build_classifier(meta["architecture"], num_classes=meta["num_classes"], pretrained=False)
    model.load_state_dict(torch.load(run_dir / "model.pt", map_location=device, weights_only=True))
    model.to(device).eval()
    sha = hashlib.sha256((run_dir / "model.pt").read_bytes()).hexdigest()
    return ModelBundle(run_dir, model, encoder, preproc, meta["architecture"], sha, device)


class _PathDataset(Dataset):
    def __init__(self, paths: Sequence[Path], transform):
        self.paths = list(paths)
        self.transform = transform

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        with Image.open(self.paths[i]) as img:
            return self.transform(img.convert("RGB"))


def compute_logits(bundle: ModelBundle, paths: Sequence[Path], cache_key: str,
                   batch_size: int = 64) -> np.ndarray:
    cache = bundle.run_dir / "cache" / f"logits_{cache_key}_{bundle.weights_sha256[:12]}.npy"
    if cache.exists():
        arr = np.load(cache)
        if arr.shape[0] == len(paths):
            return arr
    loader = DataLoader(_PathDataset(paths, build_eval_transform(bundle.preprocessing)),
                        batch_size=batch_size, shuffle=False, num_workers=CONFIG.train.num_workers)
    out: List[np.ndarray] = []
    with torch.no_grad():
        for i, batch in enumerate(loader):
            out.append(bundle.model(batch.to(bundle.device)).cpu().numpy())
            if i % 10 == 0:
                logger.info("Forward pass %d/%d batches", i + 1, len(loader))
    logits = np.concatenate(out, axis=0) if out else np.zeros((0, bundle.label_encoder.num_classes))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, logits)
    return logits


def split_arrays(bundle: ModelBundle, manifest, split: str) -> Tuple[List[Path], np.ndarray]:
    from ai.evaluation.manifest import resolve_image_path

    sub = manifest[manifest["split"] == split]
    known = set(bundle.label_encoder.classes)
    unknown = sorted(set(sub["label"]) - known)
    if unknown:
        raise ValueError(f"Manifest labels not in the model's label encoder: {unknown[:5]}")
    paths = [resolve_image_path(p) for p in sub["image_path"]]
    labels = np.array([bundle.label_encoder.encode(lbl) for lbl in sub["label"]], dtype=np.int64)
    return paths, labels


def measure_latency(bundle: ModelBundle, paths: Sequence[Path], n: int = 50) -> dict:
    """Single-image, end-to-end-ish latency (decode + preprocess + forward) on the
    current device, batch size 1 — the production request path."""
    import resource
    import time

    transform = build_eval_transform(bundle.preprocessing)
    timings = []
    sample = list(paths)[: max(1, n + 5)]
    with torch.no_grad():
        for i, p in enumerate(sample):
            t0 = time.perf_counter()
            with Image.open(p) as img:
                x = transform(img.convert("RGB")).unsqueeze(0).to(bundle.device)
            bundle.model(x)
            dt = (time.perf_counter() - t0) * 1000
            if i >= 5:  # warm-up excluded
                timings.append(dt)
    arr = np.array(timings) if timings else np.array([np.nan])
    params = sum(p.numel() for p in bundle.model.parameters())
    return {
        "device": str(bundle.device),
        "torch_threads": torch.get_num_threads(),
        "n_images": int(len(timings)),
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "mean_ms": float(arr.mean()),
        "parameters": int(params),
        "weights_file_mb": round((bundle.run_dir / "model.pt").stat().st_size / 1e6, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "note": "Excludes Grad-CAM (one extra backward pass) and the quality gate.",
    }
