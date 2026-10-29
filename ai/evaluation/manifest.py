"""
Split manifest: the exact train/val/test assignment of every image used by a run,
saved next to the model weights (split_manifest.csv).

Why: evaluate.py previously *re-derived* the test split by re-running the whole data
pipeline, which silently changes if datasets/ changes, a dependency changes the
shuffle, or dedup behaves differently. Evaluating against a persisted manifest makes
results reproducible and lets us fingerprint the exact data evaluated.

Also provides a leakage check across splits: exact duplicates (SHA-256 of bytes) and
near duplicates (64-bit average hash within a Hamming radius).
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from PIL import Image

from ai.config import CONFIG

MANIFEST_FILENAME = "split_manifest.csv"


def _rel(path: str) -> str:
    p = Path(path).resolve()
    for base in (CONFIG.paths.datasets_dir.resolve(), CONFIG.paths.project_root.resolve()):
        try:
            return str(p.relative_to(base))
        except ValueError:
            continue
    return str(p)


def resolve_image_path(stored: str) -> Path:
    p = Path(stored)
    if p.is_absolute():
        return p
    for base in (CONFIG.paths.datasets_dir, CONFIG.paths.project_root):
        if (base / p).exists():
            return base / p
    return CONFIG.paths.datasets_dir / p


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _ahash64(path: Path) -> Optional[int]:
    try:
        import imagehash

        with Image.open(path) as img:
            h = imagehash.average_hash(img.convert("L"))
        return int.from_bytes(np.packbits(np.asarray(h.hash, dtype=np.uint8).flatten()).tobytes(), "big")
    except Exception:  # noqa: BLE001
        return None


def save_split_manifest(splits, run_dir: Path, label_col: str = "canonical_label") -> Path:
    rows = []
    for name in ("train", "val", "test"):
        df: pd.DataFrame = getattr(splits, name)
        for _, r in df.iterrows():
            path = Path(r["image_path"])
            ah = _ahash64(path)
            rows.append({
                "split": name,
                "image_path": _rel(str(path)),
                "label": r[label_col],
                "source_dataset": r.get("source_dataset", ""),
                "sha256": _file_sha256(path),
                "ahash": f"{ah:016x}" if ah is not None else "",
            })
    out = run_dir / MANIFEST_FILENAME
    pd.DataFrame(rows).to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
    return out


def load_split_manifest(run_dir: Path) -> Optional[pd.DataFrame]:
    path = run_dir / MANIFEST_FILENAME
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"ahash": str, "sha256": str}, keep_default_na=False)


def manifest_fingerprint(df: pd.DataFrame, split: Optional[str] = None) -> str:
    sub = df if split is None else df[df["split"] == split]
    h = hashlib.sha256()
    for _, r in sub.sort_values(["split", "image_path"]).iterrows():
        h.update(f"{r['split']}|{r['image_path']}|{r['label']}|{r['sha256']}\n".encode())
    return h.hexdigest()


def leakage_report(df: pd.DataFrame, hamming_threshold: Optional[int] = None) -> Dict[str, object]:
    """Count exact and near-duplicate images shared between different splits."""
    threshold = CONFIG.data.duplicate_hash_threshold if hamming_threshold is None else hamming_threshold
    report: Dict[str, object] = {"hamming_threshold": threshold}
    by_split = {s: df[df["split"] == s] for s in ("train", "val", "test")}

    exact: Dict[str, int] = {}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        exact[f"{a}-{b}"] = len(set(by_split[a]["sha256"]) & set(by_split[b]["sha256"]))
    report["exact_duplicates_across_splits"] = exact

    def _arr(sub: pd.DataFrame) -> np.ndarray:
        vals = [int(h, 16) for h in sub["ahash"] if isinstance(h, str) and h]
        return np.array(vals, dtype=np.uint64)

    near: Dict[str, int] = {}
    examples: List[Dict[str, str]] = []
    train_hashes = _arr(by_split["train"])
    for name in ("val", "test"):
        sub = by_split[name]
        count = 0
        for _, r in sub.iterrows():
            if not r["ahash"] or train_hashes.size == 0:
                continue
            x = np.bitwise_xor(train_hashes, np.uint64(int(r["ahash"], 16)))
            d = np.unpackbits(x.view(np.uint8).reshape(-1, 8), axis=1).sum(axis=1)
            if (d <= threshold).any():
                count += 1
                if len(examples) < 10:
                    examples.append({"split": name, "image_path": r["image_path"]})
        near[f"train-{name}"] = count
    report["near_duplicates_vs_train"] = near
    report["near_duplicate_examples"] = examples
    return report
