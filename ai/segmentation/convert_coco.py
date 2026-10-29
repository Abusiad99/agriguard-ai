"""
Convert COCO-format polygon annotations (as exported by CVAT, Label Studio, or
LabelMe -> labelme2coco) into AgriGuard's class-map PNG masks.

    python -m ai.segmentation.convert_coco \
        --coco annotations.json --images-dir raw_images/ \
        --out datasets_segmentation/my_field_set \
        --leaf-categories leaf --lesion-categories lesion,spot,blight

Rasterization order: leaf polygons are drawn first (value 1), lesion polygons on top
(value 2), so a lesion inside a leaf overrides it. Lesion pixels that fall outside
every leaf polygon are written as IGNORE (255) rather than lesion, because the
affected-area formula is defined relative to visible leaf tissue; the count of such
pixels is reported so annotators can fix inconsistent annotations.

Only polygon segmentations are supported. COCO RLE masks are reported and skipped.
Images with no leaf annotation at all are skipped (an un-annotated image is not a
"no leaf" ground truth).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ai.segmentation.masks import BACKGROUND, IGNORE, LEAF, LESION


def _rasterize(size, polygons) -> np.ndarray:
    canvas = Image.new("L", size, 0)
    draw = ImageDraw.Draw(canvas)
    for poly in polygons:
        if len(poly) >= 6:
            draw.polygon([(poly[i], poly[i + 1]) for i in range(0, len(poly), 2)], fill=1)
    return np.asarray(canvas, dtype=bool)


def convert(coco_path: Path, images_dir: Path, out_dir: Path, leaf_names, lesion_names) -> dict:
    coco = json.loads(coco_path.read_text())
    cats = {c["id"]: c["name"].strip().lower() for c in coco.get("categories", [])}
    leaf_ids = {i for i, n in cats.items() if n in leaf_names}
    lesion_ids = {i for i, n in cats.items() if n in lesion_names}
    if not leaf_ids:
        raise SystemExit(f"None of the leaf categories {sorted(leaf_names)} exist in {coco_path} "
                         f"(available: {sorted(set(cats.values()))}).")
    anns = defaultdict(list)
    for a in coco.get("annotations", []):
        anns[a["image_id"]].append(a)

    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "masks").mkdir(parents=True, exist_ok=True)
    stats = {"converted": 0, "skipped_no_leaf": 0, "skipped_missing_image": 0,
             "rle_skipped": 0, "lesion_pixels_outside_leaf": 0}
    for img in coco.get("images", []):
        src = images_dir / img["file_name"]
        if not src.exists():
            stats["skipped_missing_image"] += 1
            continue
        size = (int(img["width"]), int(img["height"]))
        leaf_polys, lesion_polys = [], []
        for a in anns.get(img["id"], []):
            seg = a.get("segmentation")
            if not isinstance(seg, list):
                stats["rle_skipped"] += 1
                continue
            if a["category_id"] in leaf_ids:
                leaf_polys.extend(seg)
            elif a["category_id"] in lesion_ids:
                lesion_polys.extend(seg)
        if not leaf_polys:
            stats["skipped_no_leaf"] += 1
            continue
        leaf = _rasterize(size, leaf_polys)
        lesion = _rasterize(size, lesion_polys)
        mask = np.full((size[1], size[0]), BACKGROUND, dtype=np.uint8)
        mask[leaf] = LEAF
        mask[lesion & leaf] = LESION
        outside = lesion & ~leaf
        mask[outside] = IGNORE
        stats["lesion_pixels_outside_leaf"] += int(outside.sum())
        stem = Path(img["file_name"]).stem
        shutil.copy2(src, out_dir / "images" / f"{stem}{src.suffix.lower()}")
        Image.fromarray(mask, mode="L").save(out_dir / "masks" / f"{stem}.png")
        stats["converted"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coco", required=True)
    ap.add_argument("--images-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--leaf-categories", default="leaf")
    ap.add_argument("--lesion-categories", default="lesion")
    args = ap.parse_args()
    stats = convert(Path(args.coco), Path(args.images_dir), Path(args.out),
                    {s.strip().lower() for s in args.leaf_categories.split(",") if s.strip()},
                    {s.strip().lower() for s in args.lesion_categories.split(",") if s.strip()})
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
