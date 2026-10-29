"""
Evaluate a trained segmentation run on its held-out TEST split (genuine masks only).

    python -m ai.segmentation.evaluate [--run-dir artifacts/segmentation/runs/<ts>_unet]

Writes evaluation_test.json with per-class IoU/Dice, mean IoU/Dice, pixel accuracy,
affected-area absolute error (percentage points), and the worst images by lesion IoU
for failure analysis (inspect them for poor lighting, overlapping leaves, complex
backgrounds and small lesions).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ai.config import CONFIG
from ai.logging_setup import configure_logging
from ai.models.architectures import resolve_device
from ai.segmentation.data import image_to_tensor, read_manifest
from ai.segmentation.metrics import SegmentationMeter
from ai.segmentation.service import load_segmentation_model, resolve_latest_seg_run


def main() -> int:
    logger = configure_logging("segmentation_evaluate.log")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--split", default="test", choices=["test", "val"])
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else resolve_latest_seg_run()
    if run_dir is None:
        logger.error("No segmentation run found. Train one with `python -m ai.segmentation.train`.")
        return 2
    device = resolve_device(CONFIG.train.device)
    model, meta = load_segmentation_model(run_dir, device)
    samples = read_manifest(run_dir / "split_manifest.csv").get(args.split, [])
    if not samples:
        logger.error("Split '%s' is empty in %s; nothing to evaluate.", args.split, run_dir)
        return 2

    size = int(meta["image_size"])
    meter = SegmentationMeter()
    with torch.no_grad():
        for s in samples:
            with Image.open(s.image_path) as im:
                image = im.convert("RGB")
            with Image.open(s.mask_path) as m:
                gt = np.asarray(m.convert("L"))
            logits = model(image_to_tensor(image.resize((size, size), Image.BILINEAR)).unsqueeze(0).to(device))
            pred_small = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
            pred = np.asarray(Image.fromarray(pred_small).resize(image.size, Image.NEAREST))
            meter.update(pred, gt, image_id=str(s.image_path))

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "weights_sha256": meta.get("weights_sha256"),
        "split": args.split,
        "metrics": meter.summary(),
        "worst_cases_by_lesion_iou": meter.worst_cases(10),
        "note": "Metrics computed at original image resolution against human-annotated masks.",
    }
    out = run_dir / f"evaluation_{args.split}.json"
    out.write_text(json.dumps(report, indent=2))
    logger.info("Segmentation evaluation written to %s: %s", out, json.dumps(report["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
