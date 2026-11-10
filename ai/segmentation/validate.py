"""
Segmentation dataset validator.

    python -m ai.segmentation.validate [--dataset datasets/segmentation] [--format auto|masks|coco|yolo]

Reads raw/ + manifests/class_mapping.json and writes
  reports/validation_report.json   (machine-readable: every issue with its file)
  reports/validation_summary.md    (human-readable)
Exit code 0 when there are no errors, 1 otherwise. Nothing is modified or discarded.

Errors block preprocessing; warnings don't but are listed (and kept in the manifest).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ai.config import CONFIG
from ai.segmentation.adapters import (AnnotationError, detect_format, exif_orientation, iter_samples, polygon_area,
                                      raw_mask_values, render_mask)
from ai.segmentation.classes import IGNORE_INDEX, ClassMapping

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "BMP", "TIFF", "WEBP", "MPO"}
NEAR_DUPLICATE_HAMMING = 4
MIN_CLASS_FRACTION = 0.005  # of labeled non-background pixels


def default_dataset_root() -> Path:
    return CONFIG.paths.datasets_dir / "segmentation"


class Report:
    def __init__(self):
        self.issues: List[dict] = []
        self.errors = 0

    def add(self, severity: str, code: str, file: str, message: str) -> None:
        self.issues.append({"severity": severity, "code": code, "file": file, "message": message})
        if severity == "error":
            self.errors += 1

    def error(self, code, file, message):
        self.add("error", code, file, message)

    def warning(self, code, file, message):
        self.add("warning", code, file, message)

    def count(self, severity: str) -> int:
        return sum(1 for i in self.issues if i["severity"] == severity)


def _phash(image: Image.Image) -> Optional[int]:
    """64-bit perceptual hash as an int, or None if imagehash isn't installed."""
    try:
        import imagehash
    except ImportError:  # optional dependency (ai/requirements.txt); near-duplicate check skipped
        return None
    return int(str(imagehash.phash(image)), 16)


def near_duplicate_pairs(hashes: List[tuple], max_distance: int = NEAR_DUPLICATE_HAMMING) -> List[tuple]:
    """Pairs of (name, name) whose 64-bit perceptual hashes differ in <= max_distance
    bits. Vectorized per row, so 10k images stay fast."""
    if len(hashes) < 2:
        return []
    names = [h[0] for h in hashes]
    values = np.array([h[1] for h in hashes], dtype=np.uint64)
    pairs = []
    for i in range(len(values) - 1):
        xor = values[i + 1:] ^ values[i]
        bits = np.unpackbits(xor.view(np.uint8).reshape(-1, 8), axis=1).sum(axis=1)
        pairs.extend((names[i], names[i + 1 + j]) for j in np.nonzero(bits <= max_distance)[0])
    return pairs


def validate_dataset(root: Path, fmt: str = "auto", write_reports: bool = True) -> dict:
    root = Path(root)
    raw = root / "raw"
    report = Report()
    mapping: Optional[ClassMapping] = None
    mapping_path = root / "manifests" / "class_mapping.json"
    try:
        mapping = ClassMapping.load(mapping_path)
    except FileNotFoundError:
        report.error("missing_class_mapping", str(mapping_path.relative_to(root)),
                     "manifests/class_mapping.json is required (copy class_mapping.example.json and edit it)")
    except (ValueError, KeyError, TypeError) as exc:
        report.error("invalid_class_mapping", str(mapping_path.relative_to(root)), str(exc))

    detected = detect_format(raw) if fmt == "auto" else fmt
    samples = list(iter_samples(raw, detected)) if detected else []
    if not samples:
        report.error("dataset_empty", "raw/", "no images/annotations found under raw/ (see datasets/segmentation/README.md)")

    pixel_counts = np.zeros(256, dtype=np.int64)
    sha_seen: Dict[str, str] = {}
    hashes = []
    valid_ids = []
    class_presence: Counter = Counter()

    for sample in samples:
        file = sample.sample_id
        errors_before = report.errors
        for code, message in sample.problems:
            report.error(code, file, message)
        if any(code == "missing_image" for code, _ in sample.problems):
            continue
        if not sample.image_path.is_file():
            report.error("missing_image", file, "image file listed in the annotations does not exist")
            continue
        try:
            data = sample.image_path.read_bytes()
            with Image.open(sample.image_path) as im:
                im.verify()
            with Image.open(sample.image_path) as im:
                im.load()
                img_format, orientation = im.format, exif_orientation(im)
                rgb = ImageOps.exif_transpose(im).convert("RGB")
                size = rgb.size
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            report.error("corrupt_image", file, f"cannot be decoded as an image ({exc.__class__.__name__})")
            continue
        if img_format not in ALLOWED_IMAGE_FORMATS:
            report.error("invalid_image_format", file, f"format {img_format} is not supported")
            continue
        suffix_fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}.get(sample.image_path.suffix.lower())
        if suffix_fmt and suffix_fmt != img_format and not (suffix_fmt == "JPEG" and img_format == "MPO"):
            report.warning("extension_mismatch", file, f"file extension says {suffix_fmt} but content is {img_format}")

        if orientation != 1:
            report.warning("exif_orientation", file, f"stored rotated (EXIF orientation {orientation}); it is used "
                           "upright, so its mask or polygons must match the upright photo")

        digest = hashlib.sha1(data).hexdigest()
        if digest in sha_seen:
            report.warning("duplicate_image", file, f"identical to {sha_seen[digest]} (kept in the same split)")
        else:
            sha_seen[digest] = file
        ph = _phash(rgb)
        if ph is not None:
            hashes.append((file, ph))

        if sample.fmt == "masks":
            if sample.mask_path is None:
                report.error("missing_mask", file, "no mask with the same name in raw/masks")
                continue
            try:
                values = raw_mask_values(sample.mask_path)
            except (UnidentifiedImageError, OSError) as exc:
                report.error("invalid_mask_format", file, f"mask cannot be read ({exc.__class__.__name__})")
                continue
            except AnnotationError as exc:
                report.error("invalid_mask_format", file, str(exc))
                continue
            if values.shape != (size[1], size[0]):
                report.error("dimension_mismatch", file,
                             f"mask is {values.shape[1]}x{values.shape[0]}, image is {size[0]}x{size[1]}")
                continue
            uniques = np.unique(values)
            if mapping is not None:
                lut = mapping.value_lut()
                unexpected = [int(v) for v in uniques if lut[v] < 0]
                if unexpected:
                    report.error("unexpected_class_id", file, f"mask values {unexpected[:10]} are not in class_mapping.json")
                else:
                    mapped = lut[values].astype(np.int64)
                    pixel_counts += np.bincount(mapped.ravel(), minlength=256)
                    present = {int(v) for v in np.unique(mapped) if v != IGNORE_INDEX}
                    class_presence.update(present)
                    if present <= {mapping.background_id}:
                        report.warning("empty_mask", file, "mask contains only background (no leaf or lesion pixels)")
        else:
            if not sample.polygons:
                report.warning("image_without_annotations", file, "no polygons; it will be treated as all background")
            for key, poly in sample.polygons:
                if len(poly) < 3:
                    report.error("invalid_polygon", file, f"polygon for '{key}' has fewer than 3 points")
                elif polygon_area(poly) <= 0:
                    report.error("invalid_polygon", file, f"polygon for '{key}' has zero area")
                elif any(x < -1 or y < -1 or x > size[0] + 1 or y > size[1] + 1 for x, y in poly):
                    report.error("invalid_polygon", file, f"polygon for '{key}' lies outside the {size[0]}x{size[1]} image")
                if mapping is not None:
                    found = mapping.class_for_name(key) if sample.fmt == "coco" else mapping.class_for_value(int(key))
                    if found is None:
                        report.error("unexpected_class_id", file, f"label '{key}' is not in class_mapping.json")
            if report.errors == errors_before and mapping is not None and sample.polygons:
                mask = render_mask(sample, mapping, size)
                pixel_counts += np.bincount(mask.ravel(), minlength=256)
                class_presence.update(int(v) for v in np.unique(mask))
        if report.errors == errors_before:
            valid_ids.append(file)

    # Near-duplicates (different files, almost identical pictures) must share a split.
    near_pairs = near_duplicate_pairs(hashes)
    for a, b in near_pairs[:500]:
        report.warning("near_duplicate", a, f"nearly identical to {b} (kept in the same split)")

    class_stats = {}
    if mapping is not None:
        labeled = int(sum(pixel_counts[c.id] for c in mapping.classes))
        foreground = int(sum(pixel_counts[c.id] for c in mapping.classes if c.kind != "background"))
        for c in mapping.classes:
            px = int(pixel_counts[c.id])
            class_stats[c.name] = {"kind": c.kind, "pixels": px, "images": int(class_presence[c.id]),
                                   "fraction_of_labeled": round(px / labeled, 6) if labeled else 0.0}
            if valid_ids and c.kind != "background" and px == 0:
                code = "leaf_class_unused" if c.kind == "leaf" else "class_absent"
                extra = (" — affected-area percentages need annotated leaf pixels" if c.kind == "leaf" else "")
                report.warning(code, "manifests/class_mapping.json", f"class '{c.name}' never appears{extra}")
            elif foreground and c.kind != "background" and px / foreground < MIN_CLASS_FRACTION:
                report.warning("class_imbalance", "manifests/class_mapping.json",
                               f"class '{c.name}' is only {100 * px / foreground:.2f}% of labeled plant pixels")

    result = {
        "dataset_root": str(root),
        "format": detected,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "samples_found": len(samples),
            "valid_samples": len(valid_ids),
            "errors": report.count("error"),
            "warnings": report.count("warning"),
            "has_leaf_annotation": bool(mapping and mapping.has_leaf_annotation),
            "ready_for_preprocessing": report.count("error") == 0 and bool(valid_ids),
        },
        "class_statistics": class_stats,
        "near_duplicate_pairs": near_pairs,
        "issues": report.issues,
    }
    if write_reports:
        reports = root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "validation_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (reports / "validation_summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    return result


def _summary_markdown(result: dict) -> str:
    s = result["summary"]
    lines = [
        "# Segmentation dataset validation", "",
        f"- Generated: {result['generated_at']}",
        f"- Format: {result['format'] or 'not detected'}",
        f"- Samples found: {s['samples_found']}, valid: {s['valid_samples']}",
        f"- Errors: {s['errors']}, warnings: {s['warnings']}",
        f"- Leaf pixels annotated (needed for affected-area %): {'yes' if s['has_leaf_annotation'] else 'no'}",
        f"- **Ready for preprocessing: {'yes' if s['ready_for_preprocessing'] else 'no'}**", "",
    ]
    if result["class_statistics"]:
        lines += ["## Classes", "", "| Class | Kind | Pixels | Images | Share |", "|---|---|---|---|---|"]
        for name, st in result["class_statistics"].items():
            lines.append(f"| {name} | {st['kind']} | {st['pixels']} | {st['images']} | {100 * st['fraction_of_labeled']:.2f}% |")
        lines.append("")
    by_code = defaultdict(list)
    for issue in result["issues"]:
        by_code[(issue["severity"], issue["code"])].append(issue)
    if by_code:
        lines += ["## Issues", ""]
        for (severity, code), items in sorted(by_code.items()):
            lines.append(f"### {severity.upper()}: {code} ({len(items)})")
            lines += [f"- `{i['file']}` — {i['message']}" for i in items[:50]]
            if len(items) > 50:
                lines.append(f"- … {len(items) - 50} more in validation_report.json")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=default_dataset_root())
    parser.add_argument("--format", default="auto", choices=["auto", "masks", "coco", "yolo"])
    args = parser.parse_args(argv)
    result = validate_dataset(args.dataset, args.format)
    s = result["summary"]
    print(f"{s['samples_found']} samples, {s['valid_samples']} valid, {s['errors']} errors, {s['warnings']} warnings")
    print(f"Report: {Path(args.dataset) / 'reports' / 'validation_summary.md'}")
    return 0 if s["ready_for_preprocessing"] else 1


if __name__ == "__main__":
    sys.exit(main())
