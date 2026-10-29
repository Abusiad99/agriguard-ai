"""
DuplicateDetector — removes exact and near-duplicate images across merged datasets
(FR-DATA-3), which matters a great deal here because the "New Plant Diseases Dataset"
on Kaggle is itself a re-export of PlantVillage, so naively merging both would double-
count a huge fraction of the unified dataset and bias the train/val/test split.

Strategy:
  1. Exact duplicates: SHA-256 of file bytes.
  2. Near duplicates: perceptual hash (average hash, via the `imagehash` library) with
     a configurable Hamming-distance threshold (CONFIG.data.duplicate_hash_threshold).

Within a duplicate cluster, the first-seen sample is kept and the rest are dropped;
"first-seen" follows the dataset iteration order, which is deterministic given a fixed
directory listing order, so repeated runs produce the same unified dataset.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import imagehash
import numpy as np
from PIL import Image

from ai.config import CONFIG

logger = logging.getLogger("agriguard.data.dedup")


def _sha256_of_file(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


class DuplicateDetector:
    def __init__(self, hamming_threshold: int | None = None):
        self.hamming_threshold = hamming_threshold if hamming_threshold is not None \
            else CONFIG.data.duplicate_hash_threshold

    def deduplicate(self, image_paths: List[Path]) -> Tuple[List[Path], Dict[Path, Path]]:
        """Return (kept_paths, duplicate_map) where duplicate_map maps a dropped path
        to the path it was considered a duplicate of.

        Near-duplicate search compares each new 64-bit average hash against all kept
        hashes with a vectorized XOR + popcount (same semantics as comparing
        `imagehash.ImageHash` objects pairwise, but fast enough for ~10^4 images)."""
        seen_exact: Dict[str, Path] = {}
        kept: List[Path] = []
        kept_hash_paths: List[Path] = []
        hash_array = np.zeros(max(16, len(image_paths)), dtype=np.uint64)
        n_hashes = 0
        duplicate_map: Dict[Path, Path] = {}

        for path in image_paths:
            try:
                exact_hash = _sha256_of_file(path)
            except OSError:
                continue

            if exact_hash in seen_exact:
                duplicate_map[path] = seen_exact[exact_hash]
                continue

            try:
                with Image.open(path) as img:
                    phash = imagehash.average_hash(img.convert("L"))
                bits = np.packbits(np.asarray(phash.hash, dtype=np.uint8).flatten())
                hash_int = int.from_bytes(bits.tobytes(), "big")
            except Exception:
                # If perceptual hashing fails for any reason, fall back to keeping the
                # image (exact-hash dedup already ran) rather than dropping valid data.
                seen_exact[exact_hash] = path
                kept.append(path)
                continue

            duplicate_of = None
            if n_hashes:
                distances = _popcount64(np.bitwise_xor(hash_array[:n_hashes], np.uint64(hash_int)))
                hit = np.flatnonzero(distances <= self.hamming_threshold)
                if hit.size:
                    duplicate_of = kept_hash_paths[int(hit[0])]

            if duplicate_of is not None:
                duplicate_map[path] = duplicate_of
                continue

            seen_exact[exact_hash] = path
            hash_array[n_hashes] = np.uint64(hash_int)
            n_hashes += 1
            kept_hash_paths.append(path)
            kept.append(path)

        logger.info(
            "Deduplication: kept %d / %d images (%d duplicates removed)",
            len(kept), len(image_paths), len(duplicate_map),
        )
        return kept, duplicate_map


def _popcount64(values: np.ndarray) -> np.ndarray:
    """Vectorized popcount for uint64 arrays."""
    v = values.view(np.uint8).reshape(-1, 8)
    return np.unpackbits(v, axis=1).sum(axis=1)
