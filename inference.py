#!/usr/bin/env python3
"""
AgriGuard AI — Structured (JSON) inference CLI.

Usage:
    python inference.py --image path/to/leaf.jpg
    python inference.py --image-dir path/to/folder --out results.json
    python inference.py --image path/to/leaf.jpg --heatmap-dir artifacts/heatmaps

Unlike predict.py (human-readable single-image summary), this script is meant for
programmatic use: it emits machine-readable JSON to stdout (or a file with --out) and
supports batch directory processing. The FastAPI backend's AI integration client
(backend/app/infrastructure/external/ai_pipeline_client.py) wraps the same
`ai.inference.inference_service.InferenceService` class directly (in-process, not by
shelling out to this script) — this CLI exists for offline/manual/batch use and for
the operational workflow described in UC-13's sibling use case of ad-hoc verification
after training.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from PIL import Image

from ai.config import CONFIG
from ai.inference.inference_service import InferenceService
from ai.logging_setup import configure_logging


def parse_args():
    parser = argparse.ArgumentParser(description="Run AgriGuard AI inference and emit structured JSON.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", type=str, help="Path to a single image.")
    group.add_argument("--image-dir", type=str, help="Path to a directory of images (non-recursive).")
    parser.add_argument("--out", type=str, default=None, help="Write JSON output to this file instead of stdout.")
    parser.add_argument("--heatmap-dir", type=str, default=None,
                         help="If set, save an explainability heatmap overlay per image into this directory.")
    parser.add_argument("--run-dir", type=str, default=None,
                         help="Specific artifacts/runs/<timestamp>_<arch> directory (default: latest).")
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def _collect_images(image_dir: Path) -> List[Path]:
    return sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in CONFIG.data.image_extensions
    )


def main() -> int:
    logger = configure_logging("inference.log")
    args = parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else None
    service = InferenceService(run_dir=run_dir)

    heatmap_dir = Path(args.heatmap_dir) if args.heatmap_dir else None

    results = []
    if args.image:
        image_path = Path(args.image)
        if not image_path.exists():
            logger.error("Image not found: %s", image_path)
            return 1
        heatmap_path = (heatmap_dir / f"{image_path.stem}_heatmap.png") if heatmap_dir else None
        with Image.open(image_path) as img:
            diagnosis = service.diagnose(img, top_k=args.top_k, save_heatmap_to=heatmap_path)
        results.append({"image": str(image_path), **diagnosis.to_dict()})
    else:
        image_dir = Path(args.image_dir)
        if not image_dir.is_dir():
            logger.error("Not a directory: %s", image_dir)
            return 1
        image_paths = _collect_images(image_dir)
        logger.info("Found %d image(s) in %s", len(image_paths), image_dir)
        for image_path in image_paths:
            heatmap_path = (heatmap_dir / f"{image_path.stem}_heatmap.png") if heatmap_dir else None
            try:
                with Image.open(image_path) as img:
                    diagnosis = service.diagnose(img, top_k=args.top_k, save_heatmap_to=heatmap_path)
                results.append({"image": str(image_path), **diagnosis.to_dict()})
            except Exception as exc:  # noqa: BLE001 — one bad image must not abort the batch
                logger.warning("Skipping %s due to error: %s", image_path, exc)
                results.append({"image": str(image_path), "error": str(exc)})

    output = json.dumps(results, indent=2)
    if args.out:
        Path(args.out).write_text(output)
        logger.info("Wrote %d result(s) to %s", len(results), args.out)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
