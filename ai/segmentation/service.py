"""
SegmentationService — runtime leaf/lesion segmentation and affected-area measurement.

If no trained segmentation run exists (the default in this repository, because no
pixel-level annotations are available yet), `measure()` returns an explicit
`status="unavailable", reason="no_segmentation_model"` result. It never falls back to
a heuristic such as thresholding a Grad-CAM map and presenting that as a measurement.

When a model exists, outputs are written as separate artifacts; the original photo is
never modified:
  * class map PNG (0/1/2) at the original resolution,
  * an RGBA overlay visualisation (leaf green, lesion magenta).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch
from PIL import Image

from ai.config import CONFIG
from ai.segmentation.data import image_to_tensor
from ai.segmentation.masks import AreaMeasurement, colorize_class_map, measure_from_class_map
from ai.segmentation.model import UNet
from ai.segmentation.severity_scales import categorize_severity

logger = logging.getLogger("agriguard.segmentation")

SEG_RUNS_DIR = CONFIG.paths.artifacts_dir / "segmentation" / "runs"
METHOD = "unet_semantic_segmentation"


@dataclass
class SegmentationResult:
    status: str  # "measured" | "unavailable"
    reason: Optional[str] = None
    measurement: Optional[AreaMeasurement] = None
    method: Optional[str] = None
    model_version: Optional[str] = None
    mask_path: Optional[str] = None
    overlay_path: Optional[str] = None
    severity: dict = field(default_factory=lambda: {"level": None, "basis": None})

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "measurement": self.measurement.to_dict() if self.measurement else None,
            "method": self.method,
            "model_version": self.model_version,
            "mask_path": self.mask_path,
            "overlay_path": self.overlay_path,
            "severity": self.severity,
        }


def resolve_latest_seg_run(base_dir: Optional[Path] = None) -> Optional[Path]:
    base_dir = base_dir or SEG_RUNS_DIR
    marker = base_dir / "latest.json"
    if not marker.exists():
        return None
    run_dir = Path(json.loads(marker.read_text())["run_dir"])
    return run_dir if (run_dir / "model.pt").exists() else None


def load_segmentation_model(run_dir: Path, device: torch.device) -> Tuple[UNet, dict]:
    meta = json.loads((run_dir / "model_meta.json").read_text())
    model = UNet(base_channels=int(meta.get("base_channels", 32)), num_classes=int(meta.get("num_classes", 3)))
    state = torch.load(run_dir / "model.pt", map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.to(device).eval()
    if "weights_sha256" not in meta:
        meta["weights_sha256"] = hashlib.sha256((run_dir / "model.pt").read_bytes()).hexdigest()
    return model, meta


class SegmentationService:
    def __init__(self, run_dir: Optional[Path] = None, device: Optional[torch.device] = None):
        self.run_dir = run_dir or resolve_latest_seg_run()
        self.device = device or torch.device("cpu")
        self.model = None
        self.meta: dict = {}
        self._lock = threading.Lock()
        if self.run_dir is not None:
            try:
                self.model, self.meta = load_segmentation_model(self.run_dir, self.device)
                logger.info("Segmentation model loaded from %s", self.run_dir)
            except Exception as exc:  # noqa: BLE001 - a broken seg run must not break diagnosis
                logger.warning("Segmentation run at %s could not be loaded: %s", self.run_dir, exc)
                self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    @property
    def model_version(self) -> Optional[str]:
        if not self.available:
            return None
        return f"{self.run_dir.name}:{self.meta.get('weights_sha256', '')[:12]}"

    def segment(self, image: Image.Image) -> np.ndarray:
        size = int(self.meta.get("image_size", 256))
        rgb = image.convert("RGB")
        tensor = image_to_tensor(rgb.resize((size, size), Image.BILINEAR)).unsqueeze(0).to(self.device)
        with self._lock, torch.no_grad():
            pred = self.model(tensor).argmax(dim=1)[0].cpu().numpy().astype(np.uint8)
        return np.asarray(Image.fromarray(pred).resize(rgb.size, Image.NEAREST))

    def measure(self, image: Image.Image, *, plant: Optional[str] = None, condition: Optional[str] = None,
                save_mask_to: Optional[Path] = None, save_overlay_to: Optional[Path] = None) -> SegmentationResult:
        if not self.available:
            return SegmentationResult(status="unavailable", reason="no_segmentation_model")
        try:
            class_map = self.segment(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Segmentation inference failed: %s", exc)
            return SegmentationResult(status="unavailable", reason="segmentation_failed",
                                      method=METHOD, model_version=self.model_version)

        measurement = measure_from_class_map(class_map)
        mask_path = overlay_path = None
        if save_mask_to is not None:
            save_mask_to.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(class_map).save(save_mask_to)
            mask_path = str(save_mask_to)
        if save_overlay_to is not None:
            save_overlay_to.parent.mkdir(parents=True, exist_ok=True)
            base = image.convert("RGBA")
            overlay = Image.alpha_composite(base, Image.fromarray(colorize_class_map(class_map), "RGBA"))
            overlay.convert("RGB").save(save_overlay_to)
            overlay_path = str(save_overlay_to)

        severity = {"level": None, "basis": "no_validated_scale"}
        if measurement.status == "measured":
            severity = categorize_severity(measurement.affected_area_pct, plant=plant, condition=condition)
        return SegmentationResult(
            status=measurement.status, reason=measurement.reason, measurement=measurement,
            method=METHOD, model_version=self.model_version, mask_path=mask_path,
            overlay_path=overlay_path, severity=severity,
        )
