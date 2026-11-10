"""
SYNTHETIC TEST FIXTURES — generated on the fly into temporary folders by the tests.
None of this is real agricultural data, and nothing here is ever written to
datasets/ or presented as a real result. It exists only to exercise the pipelines
(validation, preprocessing, training, evaluation, inference) end to end.
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

SEG_MAPPING = {
    "version": 1,
    "ignore_values": [],
    "classes": [
        {"id": 0, "name": "background", "kind": "background", "color": [0, 0, 0], "source_values": [0], "source_names": ["background"]},
        {"id": 1, "name": "leaf", "kind": "leaf", "color": [46, 139, 87], "source_values": [1], "source_names": ["leaf"]},
        {"id": 2, "name": "lesion", "kind": "disease", "color": [220, 38, 38], "source_values": [2], "source_names": ["lesion"]},
    ],
}


def _leaf_and_spots(rng: random.Random, size: int):
    """A green ellipse 'leaf' with brown circular 'lesions' — returns the image, the
    raw class mask, and polygon annotations of the same shapes."""
    image = Image.new("RGB", (size, size), (rng.randint(170, 210),) * 3)
    mask = Image.new("L", (size, size), 0)
    di, dm = ImageDraw.Draw(image), ImageDraw.Draw(mask)
    leaf = [size * 0.1, size * 0.2, size * 0.9, size * 0.8]
    di.ellipse(leaf, fill=(50, 140 + rng.randint(-15, 15), 60))
    dm.ellipse(leaf, fill=1)
    leaf_poly = [(size / 2 + size * 0.4 * math.cos(t / 16 * 2 * math.pi), size / 2 + size * 0.3 * math.sin(t / 16 * 2 * math.pi))
                 for t in range(16)]
    spots = []
    for _ in range(rng.randint(1, 3)):
        cx, cy, r = rng.uniform(size * 0.3, size * 0.7), rng.uniform(size * 0.35, size * 0.65), rng.uniform(size * 0.05, size * 0.1)
        di.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 70, 30))
        dm.ellipse([cx - r, cy - r, cx + r, cy + r], fill=2)
        spots.append([(cx + r * math.cos(t / 12 * 2 * math.pi), cy + r * math.sin(t / 12 * 2 * math.pi)) for t in range(12)])
    return image, mask, leaf_poly, spots


def make_segmentation_dataset(root: Path, n: int = 24, size: int = 64, fmt: str = "masks", seed: int = 0) -> Path:
    rng = random.Random(seed)
    raw = root / "raw"
    (raw / "images").mkdir(parents=True, exist_ok=True)
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "class_mapping.json").write_text(json.dumps(SEG_MAPPING), encoding="utf-8")
    coco = {"images": [], "annotations": [], "categories": [{"id": 1, "name": "leaf"}, {"id": 2, "name": "lesion"}]}
    rows = []
    for i in range(n):
        image, mask, leaf_poly, spots = _leaf_and_spots(rng, size)
        name = f"img_{i:03d}.png"
        image.save(raw / "images" / name)
        rows.append({"image": name, "group_id": f"plant_{i // 2}"})  # two photos per synthetic "plant"
        if fmt == "masks":
            (raw / "masks").mkdir(exist_ok=True)
            mask.save(raw / "masks" / name)
        elif fmt == "coco":
            coco["images"].append({"id": i, "file_name": name, "width": size, "height": size})
            coco["annotations"].append({"id": 10 * i, "image_id": i, "category_id": 1,
                                        "segmentation": [[c for p in leaf_poly for c in p]]})
            for j, spot in enumerate(spots):
                coco["annotations"].append({"id": 10 * i + j + 1, "image_id": i, "category_id": 2,
                                            "segmentation": [[c for p in spot for c in p]]})
        elif fmt == "yolo":
            (raw / "annotations").mkdir(exist_ok=True)
            lines = ["1 " + " ".join(f"{x / size:.5f} {y / size:.5f}" for x, y in leaf_poly)]
            lines += ["2 " + " ".join(f"{x / size:.5f} {y / size:.5f}" for x, y in spot) for spot in spots]
            (raw / "annotations" / f"img_{i:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
    if fmt == "coco":
        (raw / "annotations").mkdir(exist_ok=True)
        (raw / "annotations" / "instances.json").write_text(json.dumps(coco), encoding="utf-8")
    with (raw / "metadata.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image", "group_id"])
        writer.writeheader()
        writer.writerows(rows)
    return root


def make_outbreak_dataset(root: Path, years: int = 2, areas=((10.1, 20.1), (10.4, 20.1), (10.1, 20.4), (10.4, 20.4)),
                          seed: int = 0) -> Path:
    """Weekly inspections of tomato/late_blight in a few grid cells, with daily weather.
    Positives are made more likely after humid, mild weeks so a model has a signal to
    learn — purely synthetic."""
    rng = random.Random(seed)
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    start = date.today() - timedelta(days=365 * years)
    days = (date.today() - start).days
    weather_rows, obs_rows = [], []
    for lat, lon in areas:
        humid = {}
        for d in range(days):
            day = start + timedelta(d)
            season = math.sin(2 * math.pi * day.timetuple().tm_yday / 365)
            rh = max(30.0, min(99.0, 70 + 20 * season + rng.gauss(0, 6)))
            temp = 18 + 8 * season + rng.gauss(0, 2)
            humid[day] = rh
            weather_rows.append({"date": day.isoformat(), "latitude": lat, "longitude": lon,
                                 "temperature_mean_c": round(temp, 1), "temperature_min_c": round(temp - 5, 1),
                                 "temperature_max_c": round(temp + 5, 1), "relative_humidity_mean_pct": round(rh, 1),
                                 "rh_hours_ge_90": max(0, min(24, round((rh - 75) * 1.2))),
                                 "precipitation_mm": round(max(0.0, rng.gauss(2 + 3 * season, 2)), 1)})
        for d in range(0, days, 7):
            day = start + timedelta(d)
            recent = sum(humid.get(day - timedelta(k), 60) for k in range(7)) / 7
            positive = rng.random() < (0.85 if recent > 80 else 0.08)
            obs_rows.append({"observed_on": day.isoformat(), "latitude": lat, "longitude": lon, "crop": "tomato",
                             "disease": "late_blight", "is_positive": int(positive)})
    for name, rows in (("observations.csv", obs_rows), ("weather_daily.csv", weather_rows)):
        with (raw / name).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return root
