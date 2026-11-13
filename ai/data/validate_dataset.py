"""
Check the plant-disease CLASSIFICATION dataset before training (read-only).

    python -m ai.data.validate_dataset            # quick: structure, labels, a sample of images
    python -m ai.data.validate_dataset --full     # also decodes every image and counts duplicates

It runs the same discovery and label normalization `train.py` uses, and reports what
training would see: dataset folders, classes, images per class, and problems such as
- Git LFS pointer files instead of images (the repository's images are stored with LFS),
- classes that would be dropped (fewer than AGRIGUARD_MIN_IMAGES_PER_CLASS images),
- labels whose plant is not recognised,
- no "healthy" class (a model trained without one can never answer "healthy").
Nothing is modified and nothing is trained. Exit code 0 = usable (warnings allowed),
1 = training would fail or be meaningless.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from ai.config import CONFIG
from ai.data.dataset_scanner import DatasetScanner
from ai.data.label_normalizer import HEALTHY_CONDITION, LabelNormalizer
from ai.data.validator import ImageValidator

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"
SAMPLE_PER_CLASS = 2  # images decoded per class in quick mode


def is_lfs_pointer(path: Path) -> bool:
    """A Git LFS pointer is a ~130-byte text file left in place of the real image when
    the repository was cloned without `git lfs pull`."""
    try:
        if path.stat().st_size > 1024:
            return False
        with open(path, "rb") as f:
            return f.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX
    except OSError:
        return False


def check_dataset(datasets_dir: Optional[Path] = None, full: bool = False) -> dict:
    datasets_dir = Path(datasets_dir) if datasets_dir else CONFIG.paths.datasets_dir
    min_per_class = CONFIG.data.min_images_per_class
    report: dict = {"datasets_dir": str(datasets_dir), "mode": "full" if full else "quick", "datasets": [],
                    "errors": [], "warnings": [], "classes": {}, "min_images_per_class": min_per_class}
    errors: List[str] = report["errors"]
    warnings: List[str] = report["warnings"]

    scanner = DatasetScanner(datasets_dir=datasets_dir)
    if not scanner.discover_dataset_roots():
        errors.append(f"No dataset folders found under {datasets_dir}. Put a folder of class-named sub-folders "
                      "there (for example datasets/plantwild_v2/<plant disease>/*.jpg).")
        return report
    audit = scanner.audit()
    report["datasets"] = [{"name": e.dataset_name, "adapter": e.adapter_name, "images": e.sample_count,
                           "raw_labels": e.class_count} for e in audit.entries]
    for e in audit.entries:
        if e.adapter_name is None:
            warnings.append(f"Folder '{e.dataset_name}' has no recognisable structure and is ignored.")
    if not audit.usable_entries:
        errors.append("No dataset folder has a recognisable structure (class-named sub-folders of images, or images "
                      "with a CSV/JSON/XML annotation file).")
        return report

    normalizer = LabelNormalizer()
    by_class: Dict[str, List[Path]] = defaultdict(list)
    raw_by_class: Dict[str, set] = defaultdict(set)
    for sample in scanner.iter_all_samples():
        label = normalizer.normalize(sample.raw_label)
        by_class[label.canonical].append(sample.image_path)
        raw_by_class[label.canonical].add(sample.raw_label)
    total = sum(len(v) for v in by_class.values())
    report["images"] = total

    # --- Git LFS pointers: checked on every file (cheap), since they make ALL of training fail.
    pointers = [p for paths in by_class.values() for p in paths if is_lfs_pointer(p)]
    report["lfs_pointer_files"] = len(pointers)
    if pointers:
        errors.append(f"{len(pointers)} of {total} image files are Git LFS pointers, not images "
                      f"(e.g. {pointers[0]}). Download the real images with:  git lfs install ; git lfs pull")

    # --- Image decoding: a sample per class (quick) or every image (full).
    validator = ImageValidator()
    pointer_set = set(pointers)
    unreadable: List[Path] = []
    checked = 0
    for paths in by_class.values():
        candidates = [p for p in paths if p not in pointer_set]
        for p in (candidates if full else candidates[:SAMPLE_PER_CLASS]):
            checked += 1
            if not validator.is_valid(p):
                unreadable.append(p)
    report["images_decoded"] = checked
    report["unreadable_images"] = len(unreadable)
    if unreadable:
        warnings.append(f"{len(unreadable)} of {checked} checked image(s) cannot be decoded and will be skipped "
                        f"(e.g. {unreadable[0]}).")

    # --- Duplicates (full mode only: it reads every file).
    if full and not pointers:
        from ai.data.dedup import DuplicateDetector

        _, duplicates = DuplicateDetector().deduplicate([p for paths in by_class.values() for p in paths])
        report["duplicate_images"] = len(duplicates)
        if duplicates:
            warnings.append(f"{len(duplicates)} exact or near-duplicate image(s) will be removed before splitting.")

    # --- Classes.
    counts = {c: len(v) for c, v in by_class.items()}
    report["classes"] = {c: {"images": n, "raw_labels": sorted(raw_by_class[c])} for c, n in sorted(counts.items())}
    report["class_count"] = len(counts)
    report["plants"] = sorted({c.split("___", 1)[0] for c in counts})
    dropped = sorted(c for c, n in counts.items() if n < min_per_class)
    kept = {c: n for c, n in counts.items() if n >= min_per_class}
    report["classes_dropped"] = dropped
    report["classes_used"] = len(kept)
    if dropped:
        warnings.append(f"{len(dropped)} class(es) have fewer than {min_per_class} images and will be dropped: "
                        f"{', '.join(dropped[:8])}{' ...' if len(dropped) > 8 else ''}")
    thin = sorted(c for c, n in kept.items() if n < 20)
    if thin:
        warnings.append(f"{len(thin)} class(es) have fewer than 20 images; their test results will rest on 1-3 images: "
                        f"{', '.join(thin[:8])}{' ...' if len(thin) > 8 else ''}")
    merged = {c: sorted(raw) for c, raw in raw_by_class.items() if len(raw) > 1}
    if merged:
        report["merged_labels"] = merged
        warnings.append(f"{len(merged)} class(es) combine several folder names (e.g. "
                        f"{next(iter(merged.items()))[1]}); check that this is intended.")
    unknown = sorted(set(normalizer.unmatched_plant_labels))
    report["unrecognised_plant_labels"] = unknown
    if unknown:
        warnings.append(f"{len(unknown)} label(s) have no recognised plant and are grouped under plant 'unknown' "
                        f"(e.g. {unknown[:3]}). Add the plant to PLANT_SYNONYMS in ai/data/label_normalizer.py.")
    if kept and not any(c.endswith("___" + HEALTHY_CONDITION) for c in kept):
        warnings.append("There is no 'healthy' class. A model trained on this data can never answer 'healthy': "
                        "every photo, including a healthy leaf, will be assigned a disease. Add folders of healthy "
                        "leaves (for example 'tomato healthy') if the app should recognise healthy plants.")
    if kept:
        smallest, largest = min(kept.values()), max(kept.values())
        report["images_per_class"] = {"min": smallest, "max": largest}
        if largest >= 10 * smallest:
            warnings.append(f"Classes are very unbalanced ({smallest} to {largest} images per class). Training "
                            "compensates with class weights, but rare classes will be less reliable.")
    if len(kept) < 2 and not errors:
        errors.append("Fewer than 2 usable classes: a classifier cannot be trained.")
    return report


def format_report(report: dict) -> str:
    lines = ["Classification dataset check (" + report["mode"] + ")", "=" * 64,
             f"Datasets folder : {report['datasets_dir']}"]
    for d in report["datasets"]:
        lines.append(f"  [{d['name']}] structure={d['adapter'] or 'NOT RECOGNISED'}, images={d['images']}, "
                     f"folder labels={d['raw_labels']}")
    if "images" in report:
        lines.append(f"Images          : {report['images']} (decoded {report.get('images_decoded', 0)}, "
                     f"unreadable {report.get('unreadable_images', 0)}, LFS pointers {report.get('lfs_pointer_files', 0)})")
        if "duplicate_images" in report:
            lines.append(f"Duplicates      : {report['duplicate_images']}")
        per = report.get("images_per_class")
        lines.append(f"Classes         : {report.get('class_count', 0)} found, {report.get('classes_used', 0)} usable"
                     + (f" ({per['min']} to {per['max']} images each)" if per else ""))
        lines.append(f"Plants          : {len(report.get('plants', []))}")
    for title, key in (("ERRORS", "errors"), ("WARNINGS", "warnings")):
        if report[key]:
            lines.append("-" * 64)
            lines.append(title + ":")
            lines += [f"  - {m}" for m in report[key]]
    lines.append("-" * 64)
    lines.append("RESULT: " + ("NOT USABLE - fix the errors above" if report["errors"] else
                               "usable" + (" (see warnings)" if report["warnings"] else "")))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check the classification dataset before training (read-only).")
    parser.add_argument("--full", action="store_true", help="decode every image and count duplicates (slow)")
    parser.add_argument("--datasets-dir", type=str, default=None, help="default: AGRIGUARD_DATASETS_DIR or <repo>/datasets")
    parser.add_argument("--json-out", type=str, default=None, help="also write the full report (per-class counts) as JSON")
    args = parser.parse_args(argv)

    report = check_dataset(Path(args.datasets_dir) if args.datasets_dir else None, full=args.full)
    print(format_report(report))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Full report written to {out}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
