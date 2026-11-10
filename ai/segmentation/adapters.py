"""
Annotation-format adapters. The rest of the pipeline sees only `SegSample`s and
`render_mask()`, never the source format, so adding a format means adding an adapter.

Supported layouts under <dataset>/raw/ (see datasets/segmentation/README.md):

  masks   images/<name>.<ext>  +  masks/<name>.png      (binary or multi-class PNG)
  coco    images/...           +  annotations/*.json    (COCO instances, polygon segmentation)
  yolo    images/<name>.<ext>  +  annotations/<name>.txt (YOLO-seg: "cls x1 y1 x2 y2 ..." normalized)

Optional raw/metadata.csv (columns: image, group_id[, split]) records which images
come from the same plant / photograph / session, so they stay in the same split.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from ai.segmentation.classes import IGNORE_INDEX, ClassMapping

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
EXIF_ORIENTATION_TAG = 0x0112


def open_upright(path: Path) -> Image.Image:
    """Load a photo as it is displayed: EXIF orientation applied. Annotation tools show
    (and label) the upright photo, and the app analyses scans upright too."""
    with Image.open(path) as im:
        im.load()
        return ImageOps.exif_transpose(im)


def exif_orientation(image: Image.Image) -> int:
    try:
        return int(image.getexif().get(EXIF_ORIENTATION_TAG, 1) or 1)
    except Exception:  # noqa: BLE001 - unreadable EXIF counts as "no rotation"
        return 1
FORMATS = ("masks", "coco", "yolo")

Polygon = List[Tuple[float, float]]  # absolute pixel coordinates


@dataclass
class SegSample:
    sample_id: str            # image path relative to raw/images, '/'-separated
    image_path: Path
    fmt: str
    mask_path: Optional[Path] = None                          # masks format
    polygons: List[Tuple[str, Polygon]] = field(default_factory=list)  # (class key, polygon) for coco/yolo
    annotation_path: Optional[Path] = None
    group_id: Optional[str] = None
    forced_split: Optional[str] = None
    problems: List[Tuple[str, str]] = field(default_factory=list)  # (code, message) found while reading


class AnnotationError(Exception):
    pass


# ---------------------------------------------------------------------- discovery
def detect_format(raw_dir: Path) -> Optional[str]:
    masks = raw_dir / "masks"
    if masks.is_dir() and any(p.is_file() and p.name != ".gitkeep" for p in masks.rglob("*")):
        return "masks"
    ann = raw_dir / "annotations"
    if ann.is_dir():
        if any(ann.rglob("*.json")):
            return "coco"
        if any(ann.rglob("*.txt")):
            return "yolo"
    return None


def list_images(images_dir: Path) -> List[Path]:
    if not images_dir.is_dir():
        return []
    return sorted(p for p in images_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)


def load_metadata(raw_dir: Path) -> Dict[str, dict]:
    path = raw_dir / "metadata.csv"
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["image"].replace("\\", "/"): row for row in csv.DictReader(fh) if row.get("image")}


def iter_samples(raw_dir: Path, fmt: str) -> Iterator[SegSample]:
    if fmt not in FORMATS:
        raise ValueError(f"unknown annotation format '{fmt}', expected one of {FORMATS}")
    metadata = load_metadata(raw_dir)
    images_dir = raw_dir / "images"
    reader = {"masks": _iter_masks, "coco": _iter_coco, "yolo": _iter_yolo}[fmt]
    for sample in reader(raw_dir, images_dir):
        meta = metadata.get(sample.sample_id) or metadata.get(Path(sample.sample_id).name) or {}
        sample.group_id = (meta.get("group_id") or "").strip() or None
        split = (meta.get("split") or "").strip().lower()
        sample.forced_split = split if split in ("train", "validation", "test") else None
        yield sample


def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _iter_masks(raw_dir: Path, images_dir: Path) -> Iterator[SegSample]:
    masks_dir = raw_dir / "masks"
    masks = {}
    if masks_dir.is_dir():
        masks = {_rel(p, masks_dir).rsplit(".", 1)[0]: p
                 for p in masks_dir.rglob("*") if p.is_file() and p.name != ".gitkeep"}
    for image in list_images(images_dir):
        sid = _rel(image, images_dir)
        mask = masks.pop(sid.rsplit(".", 1)[0], None)
        yield SegSample(sample_id=sid, image_path=image, fmt="masks", mask_path=mask)
    for orphan in masks.values():  # masks without an image
        yield SegSample(sample_id=_rel(orphan, masks_dir), image_path=images_dir / _rel(orphan, masks_dir),
                        fmt="masks", mask_path=orphan,
                        problems=[("missing_image", f"mask {orphan.name} has no matching image in raw/images")])


def _iter_coco(raw_dir: Path, images_dir: Path) -> Iterator[SegSample]:
    by_image: Dict[str, SegSample] = {}
    for ann_file in sorted((raw_dir / "annotations").rglob("*.json")):
        try:
            coco = json.loads(ann_file.read_text(encoding="utf-8"))
            categories = {c["id"]: str(c["name"]) for c in coco["categories"]}
            images = {img["id"]: img for img in coco["images"]}
        except (ValueError, KeyError, TypeError) as exc:
            yield SegSample(sample_id=ann_file.name, image_path=ann_file, fmt="coco", annotation_path=ann_file,
                            problems=[("invalid_annotation_file", f"{ann_file.name}: not a COCO file ({exc})")])
            continue
        for img in images.values():
            name = str(img.get("file_name", "")).replace("\\", "/")
            img["_sample"] = by_image.setdefault(name, SegSample(sample_id=name, image_path=images_dir / name,
                                                                 fmt="coco", annotation_path=ann_file))
        for ann in coco.get("annotations", []):
            img = images.get(ann.get("image_id"))
            if img is None:
                continue
            sample = img["_sample"]
            label = categories.get(ann.get("category_id"))
            seg = ann.get("segmentation")
            if label is None:
                sample.problems.append(("unknown_category", f"annotation {ann.get('id')} uses category id "
                                                            f"{ann.get('category_id')} not listed in categories"))
            elif isinstance(seg, dict):
                sample.problems.append(("unsupported_rle", f"annotation {ann.get('id')} uses RLE; convert it to "
                                                           "polygons or a PNG mask"))
            elif isinstance(seg, list):
                for flat in seg:
                    pts = [(float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
                    sample.polygons.append((label, pts))
    yield from by_image.values()


def _iter_yolo(raw_dir: Path, images_dir: Path) -> Iterator[SegSample]:
    ann_dir = raw_dir / "annotations"
    labels = {_rel(p, ann_dir).rsplit(".", 1)[0]: p for p in ann_dir.rglob("*.txt")} if ann_dir.is_dir() else {}
    for image in list_images(images_dir):
        sid = _rel(image, images_dir)
        label_file = labels.pop(sid.rsplit(".", 1)[0], None)
        sample = SegSample(sample_id=sid, image_path=image, fmt="yolo", annotation_path=label_file)
        if label_file is not None:
            try:
                width, height = open_upright(image).size
            except Exception:  # noqa: BLE001 - reported by the validator as corrupt_image
                width = height = 0
            for line_no, line in enumerate(label_file.read_text(encoding="utf-8").splitlines(), 1):
                parts = line.split()
                if not parts:
                    continue
                try:
                    cls_id, coords = int(parts[0]), [float(x) for x in parts[1:]]
                except ValueError:
                    sample.problems.append(("invalid_polygon", f"{label_file.name}:{line_no} is not 'class x y x y ...'"))
                    continue
                if len(coords) % 2:
                    sample.problems.append(("invalid_polygon", f"{label_file.name}:{line_no} has an odd number of coordinates"))
                    continue
                if any(c < 0 or c > 1 for c in coords):
                    sample.problems.append(("invalid_polygon", f"{label_file.name}:{line_no} has coordinates outside 0-1"))
                pts = [(coords[i] * width, coords[i + 1] * height) for i in range(0, len(coords), 2)]
                sample.polygons.append((str(cls_id), pts))
        yield sample
    for orphan in labels.values():
        yield SegSample(sample_id=_rel(orphan, ann_dir), image_path=images_dir / _rel(orphan, ann_dir), fmt="yolo",
                        annotation_path=orphan,
                        problems=[("missing_image", f"annotation {orphan.name} has no matching image in raw/images")])


# ---------------------------------------------------------------------- masks
def polygon_area(poly: Polygon) -> float:
    if len(poly) < 3:
        return 0.0
    xs, ys = zip(*poly)
    return 0.5 * abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i] for i in range(len(poly))))


def raw_mask_values(mask_path: Path) -> np.ndarray:
    """Raw mask as a 2-D uint8 array. Accepts single-channel masks (L/P/I) and RGB
    masks whose channels are identical; anything else is an AnnotationError."""
    with Image.open(mask_path) as im:
        if im.mode in ("L", "P"):
            return np.asarray(im, dtype=np.uint8)
        if im.mode in ("I", "I;16"):
            arr = np.asarray(im)
            if arr.max(initial=0) > 255:
                raise AnnotationError(f"{mask_path.name}: mask values above 255 are not supported")
            return arr.astype(np.uint8)
        arr = np.asarray(im.convert("RGB"))
        if not (np.array_equal(arr[..., 0], arr[..., 1]) and np.array_equal(arr[..., 1], arr[..., 2])):
            raise AnnotationError(f"{mask_path.name}: color (RGB) masks are not supported; use one channel "
                                  "where each pixel value is a class value")
        return arr[..., 0].copy()


def render_mask(sample: SegSample, mapping: ClassMapping, size: Tuple[int, int]) -> np.ndarray:
    """Training-id mask (H x W, uint8) for a sample at image size (width, height).
    Raises AnnotationError for unmapped values / labels — never guesses."""
    width, height = size
    if sample.fmt == "masks":
        if sample.mask_path is None:
            raise AnnotationError("no mask file")
        raw = raw_mask_values(sample.mask_path)
        if raw.shape != (height, width):
            raise AnnotationError(f"mask is {raw.shape[1]}x{raw.shape[0]} but image is {width}x{height}")
        lut = mapping.value_lut()
        mapped = lut[raw]
        if (mapped < 0).any():
            bad = sorted(int(v) for v in np.unique(raw[mapped < 0]))
            raise AnnotationError(f"unmapped mask values {bad[:10]}")
        return mapped.astype(np.uint8)

    canvas = Image.new("L", (width, height), color=mapping.background_id)
    draw = ImageDraw.Draw(canvas)
    resolved = []
    for key, poly in sample.polygons:
        seg_class = mapping.class_for_name(key) if sample.fmt == "coco" else mapping.class_for_value(int(key))
        if seg_class is None:
            raise AnnotationError(f"label '{key}' is not in class_mapping.json")
        resolved.append((seg_class, poly))
    # Leaf tissue first, then lesions on top, so overlapping lesions are never hidden.
    for seg_class, poly in sorted(resolved, key=lambda item: item[0].kind == "disease"):
        if len(poly) >= 3:
            draw.polygon(poly, fill=seg_class.id)
    return np.asarray(canvas, dtype=np.uint8)


__all__ = ["SegSample", "AnnotationError", "FORMATS", "IGNORE_INDEX", "detect_format", "iter_samples",
           "list_images", "render_mask", "raw_mask_values", "polygon_area"]
