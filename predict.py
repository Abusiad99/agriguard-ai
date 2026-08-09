#!/usr/bin/env python3
"""
AgriGuard AI — Quick single-image prediction CLI.

Usage:
    python predict.py path/to/leaf.jpg
    python predict.py path/to/leaf.jpg --top-k 5 --save-heatmap out/heatmap.png

Loads the most recently trained model (artifacts/runs/latest.json) and prints a
human-readable diagnosis summary to the console. For programmatic/JSON output
(used by the backend), see inference.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from ai.inference.inference_service import InferenceService
from ai.logging_setup import configure_logging


def parse_args():
    parser = argparse.ArgumentParser(description="Run AgriGuard AI diagnosis on a single image.")
    parser.add_argument("image_path", type=str, help="Path to the plant image.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of top predictions to show.")
    parser.add_argument("--save-heatmap", type=str, default=None,
                         help="Optional path to save the explainability heatmap overlay.")
    parser.add_argument("--run-dir", type=str, default=None,
                         help="Specific artifacts/runs/<timestamp>_<arch> directory (default: latest).")
    return parser.parse_args()


def main() -> int:
    logger = configure_logging("predict.log")
    args = parse_args()

    image_path = Path(args.image_path)
    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        return 1

    run_dir = Path(args.run_dir) if args.run_dir else None
    service = InferenceService(run_dir=run_dir)

    image = Image.open(image_path)
    heatmap_path = Path(args.save_heatmap) if args.save_heatmap else None
    result = service.diagnose(image, top_k=args.top_k, save_heatmap_to=heatmap_path)

    print("\n" + "=" * 60)
    print(f"AgriGuard AI — Diagnosis for: {image_path.name}")
    print("=" * 60)

    if result.unrecognized_plant:
        print(f"Result: UNRECOGNIZED PLANT (plant-mass confidence {result.confidence_score:.2f}%)")
        print("Please retake the photo with clearer framing of a single leaf/plant part.")
    else:
        print(f"Plant:              {result.plant}")
        print(f"Condition:          {result.condition}")
        print(f"Confidence:         {result.confidence_score:.2f}%"
              + ("  [LOW CONFIDENCE — recommend manual expert review]" if result.low_confidence_flag else ""))
        if result.severity_level:
            print(f"Severity:           {result.severity_level} "
                  f"(affected {result.affected_area_pct:.1f}% / healthy {result.healthy_area_pct:.1f}%)")
        if result.bounding_box:
            b = result.bounding_box
            print(f"Affected region:    x[{b['x_min']}:{b['x_max']}] y[{b['y_min']}:{b['y_max']}]")
        if result.heatmap_overlay_path:
            print(f"Heatmap saved to:   {result.heatmap_overlay_path}")

        print("\nTop-{} predictions:".format(args.top_k))
        for i, item in enumerate(result.top_k, 1):
            print(f"  {i}. {item['plant']} — {item['condition']}  ({item['confidence']:.2f}%)")

    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
