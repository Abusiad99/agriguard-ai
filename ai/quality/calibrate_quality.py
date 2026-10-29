"""
Measure how the image-quality gate behaves on real dataset images and on
synthetically degraded copies of them.

    python -m ai.quality.calibrate_quality --sample 1500 --out artifacts/quality_calibration.json

What this measures (and what it does not):
  * false-rejection rate: fraction of REAL dataset images (which a human already
    accepted into a disease dataset) that the gate would reject or warn about;
  * detection rate on synthetic degradations (Gaussian blur, darkening,
    overexposure, downscaling) of those same images.

Synthetic degradations are a sanity check of each detector's mechanics. They are not
a substitute for photos labelled by humans as "unusable for diagnosis", which this
project does not have, so the resulting thresholds remain heuristic operating points.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from ai.config import CONFIG
from ai.quality.image_quality import QUALITY_VERSION, QualityThresholds, assess_image_quality, compute_quality_metrics

_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _degrade(img: Image.Image, kind: str) -> Image.Image:
    w, h = img.size
    scale = 512.0 / max(w, h)
    if scale < 1:
        img = img.resize((round(w * scale), round(h * scale)), Image.BILINEAR)
    if kind == "blur_heavy":
        return img.filter(ImageFilter.GaussianBlur(radius=6))
    if kind == "blur_moderate":
        return img.filter(ImageFilter.GaussianBlur(radius=3))
    if kind == "very_dark":
        return ImageEnhance.Brightness(img).enhance(0.12)
    if kind == "overexposed":
        return ImageEnhance.Brightness(img).enhance(3.5)
    if kind == "tiny":
        return img.resize((64, max(1, round(64 * img.size[1] / img.size[0]))), Image.BILINEAR)
    raise ValueError(kind)


_EXPECTED_CODE = {
    "blur_heavy": {"too_blurry"},
    "blur_moderate": {"too_blurry", "slightly_blurry"},
    "very_dark": {"too_dark", "no_detail"},
    "overexposed": {"overexposed", "partly_overexposed", "no_detail"},
    "tiny": {"resolution_too_low"},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets-dir", default=str(CONFIG.paths.datasets_dir))
    ap.add_argument("--sample", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(CONFIG.paths.artifacts_dir / "quality_calibration.json"))
    args = ap.parse_args()

    paths = sorted(p for p in Path(args.datasets_dir).rglob("*") if p.suffix.lower() in _EXTS)
    random.Random(args.seed).shuffle(paths)
    paths = paths[: args.sample]
    t = QualityThresholds()

    metrics, statuses, codes = [], [], {}
    degraded = {k: {"n": 0, "detected": 0, "rejected": 0} for k in _EXPECTED_CODE}
    for p in paths:
        try:
            with Image.open(p) as im:
                im.load()
                img = im.convert("RGB")
        except Exception:  # noqa: BLE001 - corrupt files are reported by the training validator
            continue
        metrics.append(compute_quality_metrics(img))
        rep = assess_image_quality(img, t)
        statuses.append(rep.status)
        for issue in rep.issues:
            codes[issue.code] = codes.get(issue.code, 0) + 1
        for kind, expected in _EXPECTED_CODE.items():
            drep = assess_image_quality(_degrade(img, kind), t)
            got = {i.code for i in drep.issues}
            degraded[kind]["n"] += 1
            degraded[kind]["detected"] += int(bool(got & expected))
            degraded[kind]["rejected"] += int(drep.rejected)

    n = len(statuses)
    keys = metrics[0].keys() if metrics else []
    percentiles = {
        k: {f"p{q}": float(np.percentile([m[k] for m in metrics], q)) for q in (1, 5, 25, 50, 75, 95, 99)}
        for k in keys
    }
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "quality_version": QUALITY_VERSION,
        "datasets_dir": str(args.datasets_dir),
        "n_real_images": n,
        "thresholds": t.__dict__,
        "real_images": {
            "rejected_rate": statuses.count("rejected") / n if n else None,
            "warning_rate": statuses.count("warning") / n if n else None,
            "ok_rate": statuses.count("ok") / n if n else None,
            "issue_counts": codes,
        },
        "synthetic_degradations": {
            k: {"n": v["n"], "detection_rate": v["detected"] / v["n"] if v["n"] else None,
                "rejection_rate": v["rejected"] / v["n"] if v["n"] else None}
            for k, v in degraded.items()
        },
        "metric_percentiles_real_images": percentiles,
        "caveat": ("Real images come from a curated disease dataset, so their rejection rate "
                   "approximates a false-rejection rate. Degradations are synthetic."),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("n_real_images", "real_images", "synthetic_degradations")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
