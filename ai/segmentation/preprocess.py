"""
Segmentation preprocessing: raw/ -> processed/ + splits/ + manifests/dataset_manifest.json

    python -m ai.segmentation.preprocess [--dataset datasets/segmentation] [--config configs/segmentation/default.json]
                                         [--format auto] [--exclude-invalid]

1. Runs the validator. Errors stop preprocessing unless --exclude-invalid is given;
   then every excluded file is listed in the manifest (nothing is dropped silently).
2. Renders each annotation to a training-id mask (class_mapping.json), caps the
   longest side at `max_side` — bilinear for images, NEAREST for masks so class ids
   never blend — and writes processed/images/<id>.png and processed/masks/<id>.png.
3. Splits by group, not by image: images sharing metadata.csv group_id, exact
   duplicates and near-duplicates (perceptual hash) always land in the same split,
   so no plant/photo leaks between train and test. Seed and ratios come from config.
4. Writes splits/{train,validation,test}.txt and a manifest with a content-derived
   dataset_version.
Re-running is deterministic for the same inputs and config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image

from ai.segmentation.adapters import detect_format, iter_samples, open_upright, render_mask
from ai.segmentation.classes import ClassMapping
from ai.segmentation.config import SegmentationConfig, load_config
from ai.segmentation.validate import default_dataset_root, validate_dataset

SPLITS = ("train", "validation", "test")


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _sample_key(sample_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", sample_id.rsplit(".", 1)[0])[-60:]
    return f"{stem}_{hashlib.sha1(sample_id.encode()).hexdigest()[:8]}"


def resize_pair(image: Image.Image, mask: np.ndarray, max_side: int):
    """Downscale (never upscale) so the longest side <= max_side. Mask uses NEAREST."""
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    if scale >= 1.0:
        return image, mask
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized_mask = Image.fromarray(mask).resize(size, Image.NEAREST)
    return image.resize(size, Image.BILINEAR), np.asarray(resized_mask, dtype=np.uint8)


def assign_splits(groups: Dict[str, List[str]], forced: Dict[str, str], ratios, seed: int) -> Dict[str, str]:
    """Group-level split. Returns sample key -> split. Groups containing a forced
    split go there as a whole; the rest are shuffled (seeded) and filled to ratio."""
    total = sum(len(v) for v in groups.values())
    targets = {s: r * total for s, r in zip(SPLITS, ratios)}
    filled = {s: 0 for s in SPLITS}
    assignment: Dict[str, str] = {}
    free = []
    for gid, members in sorted(groups.items()):
        wanted = {forced[m] for m in members if m in forced}
        if wanted:
            split = sorted(wanted)[0]  # conflicting forced splits inside a group resolve deterministically
            for m in members:
                assignment[m] = split
            filled[split] += len(members)
        else:
            free.append(gid)
    rng = random.Random(seed)
    rng.shuffle(free)
    for gid in free:
        split = min(SPLITS, key=lambda s: filled[s] / targets[s] if targets[s] else float("inf"))
        for m in groups[gid]:
            assignment[m] = split
        filled[split] += len(groups[gid])
    return assignment


def preprocess(root: Path, config: SegmentationConfig, fmt: str = "auto", exclude_invalid: bool = False) -> dict:
    root = Path(root)
    report = validate_dataset(root, fmt)
    summary = report["summary"]
    errored = sorted({i["file"] for i in report["issues"] if i["severity"] == "error"})
    if summary["errors"] and not exclude_invalid:
        raise SystemExit(f"Validation found {summary['errors']} errors in {len(errored)} files; see "
                         f"{root / 'reports' / 'validation_summary.md'}. Fix them, or re-run with "
                         "--exclude-invalid to leave those files out (they will be listed in the manifest).")
    mapping = ClassMapping.load(root / "manifests" / "class_mapping.json")
    fmt = report["format"] or detect_format(root / "raw")
    excluded = set(errored)

    processed = root / "processed"
    for sub in ("images", "masks"):
        target = processed / sub
        target.mkdir(parents=True, exist_ok=True)
        for old in target.glob("*.png"):  # regenerate outputs; leave anything else (e.g. .gitkeep) alone
            old.unlink()

    records = []
    for sample in iter_samples(root / "raw", fmt):
        if sample.sample_id in excluded or not sample.image_path.is_file():
            continue
        image = open_upright(sample.image_path).convert("RGB")
        mask = render_mask(sample, mapping, image.size)
        image, mask = resize_pair(image, mask, config.max_side)
        key = _sample_key(sample.sample_id)
        image.save(processed / "images" / f"{key}.png")
        Image.fromarray(mask, mode="L").save(processed / "masks" / f"{key}.png")
        records.append({
            "key": key, "source": sample.sample_id, "group_id": sample.group_id,
            "forced_split": sample.forced_split, "width": image.size[0], "height": image.size[1],
            "image_sha1": hashlib.sha1(image.tobytes()).hexdigest(),
            "mask_sha1": hashlib.sha1(mask.tobytes()).hexdigest(),
            "class_pixels": {int(k): int(v) for k, v in zip(*np.unique(mask, return_counts=True))},
        })
    if not records:
        raise SystemExit("No valid samples to preprocess.")

    # Group: metadata group_id, else the sample itself; merge exact/near duplicates.
    by_source = {r["source"]: r["key"] for r in records}
    uf = _UnionFind([r["key"] for r in records])
    first_by_group: Dict[str, str] = {}
    first_by_hash: Dict[str, str] = {}
    for r in records:
        if r["group_id"]:
            uf.union(r["key"], first_by_group.setdefault(r["group_id"], r["key"]))
        uf.union(r["key"], first_by_hash.setdefault(r["image_sha1"], r["key"]))
    for a, b in report.get("near_duplicate_pairs", []):
        if a in by_source and b in by_source:
            uf.union(by_source[a], by_source[b])
    groups: Dict[str, List[str]] = {}
    for r in records:
        groups.setdefault(uf.find(r["key"]), []).append(r["key"])
    forced = {r["key"]: r["forced_split"] for r in records if r["forced_split"]}
    assignment = assign_splits(groups, forced, config.split_ratios, config.seed)

    splits_dir = root / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    split_members = {s: sorted(k for k, v in assignment.items() if v == s) for s in SPLITS}
    for split, keys in split_members.items():
        (splits_dir / f"{split}.txt").write_text("\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")

    def class_pixels(keys):
        totals = np.zeros(mapping.num_classes, dtype=np.int64)
        index = {r["key"]: r for r in records}
        for k in keys:
            for cid, px in index[k]["class_pixels"].items():
                if cid < mapping.num_classes:
                    totals[cid] += px
        return {c.name: int(totals[c.id]) for c in mapping.classes}

    # The split of each sample is part of the version: re-splitting (another seed, new
    # data) must change it, so evaluation can tell a model's test split from its training data.
    version_hash = hashlib.sha256()
    for r in sorted(records, key=lambda r: r["key"]):
        version_hash.update(f"{r['key']}:{r['image_sha1']}:{r['mask_sha1']}:{assignment.get(r['key'])};".encode())
    version_hash.update(json.dumps(mapping.to_dict(), sort_keys=True).encode())
    manifest = {
        "dataset": "segmentation",
        "dataset_version": version_hash.hexdigest()[:16],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_format": fmt,
        "num_samples": len(records),
        "num_groups": len(groups),
        "splits": {s: len(k) for s, k in split_members.items()},
        "class_pixels": {s: class_pixels(k) for s, k in split_members.items()},
        "has_leaf_annotation": mapping.has_leaf_annotation,
        "preprocessing": {"max_side": config.max_side, "seed": config.seed, "split_ratios": config.split_ratios,
                          "image_resample": "bilinear", "mask_resample": "nearest"},
        "excluded": [{"file": f, "reason": "validation error (see reports/validation_report.json)"} for f in sorted(excluded)],
        "validation": {"errors": summary["errors"], "warnings": summary["warnings"]},
        "samples": [{k: r[k] for k in ("key", "source", "group_id", "width", "height")} | {"split": assignment[r["key"]]}
                    for r in records],
    }
    (root / "manifests" / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preprocess the segmentation dataset")
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--format", default="auto", choices=["auto", "masks", "coco", "yolo"])
    parser.add_argument("--exclude-invalid", action="store_true",
                        help="leave out files with validation errors (listed in the manifest) instead of stopping")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)
    manifest = preprocess(args.dataset, load_config(args.config, seed=args.seed), args.format, args.exclude_invalid)
    print(f"dataset_version {manifest['dataset_version']}: {manifest['num_samples']} samples in "
          f"{manifest['num_groups']} groups -> {manifest['splits']}; excluded {len(manifest['excluded'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
