"""
Segmentation inference: image -> training-id mask, affected-area statistics, regions.

Affected Area % = disease-affected plant pixels / all plant pixels x 100, where plant
pixels = healthy leaf pixels + disease pixels. It is only computed when the model was
trained with a "leaf" class (it can tell leaf from background) and enough plant
tissue is detected; otherwise `affected_area_pct` is None with the reason, never the
fraction of the whole photo.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from scipy import ndimage

from ai import registry
from ai.models.architectures import resolve_device
from ai.segmentation.classes import ClassMapping
from ai.segmentation.config import SegmentationConfig
from ai.segmentation.dataset import normalize
from ai.segmentation.models import build_segmentation_model

MAX_MASK_SIDE = 2048  # masks for larger photos are produced at this resolution (percentages are scale-free)
MIN_REGION_PIXELS = 16


@dataclass
class SegmentationResult:
    status: str
    image_width: int
    image_height: int
    mask_width: int
    mask_height: int
    affected_pixels: int
    plant_pixels: Optional[int]
    affected_area_pct: Optional[float]
    area_basis: Optional[str]
    area_unavailable_reason: Optional[str]
    class_pixels: dict
    regions: List[dict]
    mean_confidence: Optional[float]
    mean_uncertainty: Optional[float]
    model_name: Optional[str]
    model_version: Optional[str]
    inference_ms: int
    created_at: str
    mask: np.ndarray = field(repr=False, default=None)

    def summary(self) -> dict:
        data = asdict(self)
        data.pop("mask", None)
        return data


def compute_area_stats(mask: np.ndarray, mapping: ClassMapping, min_plant_pixels: int) -> dict:
    counts = np.bincount(mask.ravel().astype(np.int64), minlength=mapping.num_classes)
    disease_px = int(sum(counts[i] for i in mapping.disease_ids))
    class_pixels = {c.name: int(counts[c.id]) for c in mapping.classes}
    if not mapping.has_leaf_annotation:
        return {"affected_pixels": disease_px, "plant_pixels": None, "affected_area_pct": None, "area_basis": None,
                "area_unavailable_reason": "model_does_not_segment_leaf_tissue", "class_pixels": class_pixels}
    plant_px = disease_px + int(sum(counts[i] for i in mapping.leaf_ids))
    if plant_px < min_plant_pixels:
        return {"affected_pixels": disease_px, "plant_pixels": plant_px, "affected_area_pct": None, "area_basis": None,
                "area_unavailable_reason": "too_little_plant_tissue_detected", "class_pixels": class_pixels}
    return {"affected_pixels": disease_px, "plant_pixels": plant_px,
            "affected_area_pct": round(100.0 * disease_px / plant_px, 2), "area_basis": "plant_pixels",
            "area_unavailable_reason": None, "class_pixels": class_pixels}


def extract_regions(mask: np.ndarray, confidence: Optional[np.ndarray], mapping: ClassMapping,
                    max_regions: int = 50) -> List[dict]:
    """Connected disease regions with bounding boxes (in mask coordinates)."""
    regions = []
    for cid in mapping.disease_ids:
        labels, count = ndimage.label(mask == cid)
        if not count:
            continue
        sizes = np.bincount(labels.ravel())
        for index, box in enumerate(ndimage.find_objects(labels), start=1):
            if box is None or sizes[index] < MIN_REGION_PIXELS:
                continue
            region = {"label": mapping.classes[cid].name, "class_id": cid, "pixels": int(sizes[index]),
                      "bbox": {"x_min": box[1].start, "y_min": box[0].start, "x_max": box[1].stop - 1, "y_max": box[0].stop - 1}}
            if confidence is not None:
                region["mean_confidence"] = round(float(confidence[labels == index].mean()), 4)
            regions.append(region)
    return sorted(regions, key=lambda r: -r["pixels"])[:max_regions]


def load_run(run_dir: Path, device: torch.device):
    card = registry.read_model_card(run_dir)
    details = card.get("details", {})
    mapping = ClassMapping.from_dict(details["class_mapping"])
    config = SegmentationConfig(**{k: v for k, v in details.get("config", {}).items()
                                   if k in SegmentationConfig.__dataclass_fields__})
    model = build_segmentation_model(config.architecture, config.encoder, mapping.num_classes, pretrained=False)
    state = torch.load(run_dir / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(state["model_state"] if "model_state" in state else state)
    return model.to(device).eval(), card, mapping, config


class SegmentationService:
    """Loads one trained run once; `segment()` is called per image. Not thread-safe —
    the backend serializes calls (see segmentation_client.py)."""

    def __init__(self, run_dir: Optional[Path] = None, device: Optional[str] = None):
        self.run_dir = run_dir or registry.latest_run_dir("segmentation")
        if self.run_dir is None:
            raise FileNotFoundError("No trained segmentation model (artifacts/segmentation/runs/latest.json).")
        self.device = resolve_device(device or "auto")
        self.model, self.card, self.mapping, self.config = load_run(self.run_dir, self.device)

    @torch.no_grad()
    def segment(self, image: Image.Image) -> SegmentationResult:
        start = time.perf_counter()
        image = image.convert("RGB")
        width, height = image.size
        scale = min(1.0, MAX_MASK_SIDE / max(width, height))
        mask_w, mask_h = max(1, round(width * scale)), max(1, round(height * scale))

        x = normalize(image.resize((self.config.image_size, self.config.image_size), Image.BILINEAR), self.config)
        logits = self.model(x.unsqueeze(0).to(self.device))
        probs = F.interpolate(logits.float(), size=(mask_h, mask_w), mode="bilinear", align_corners=False).softmax(1)[0]
        conf, pred = probs.max(dim=0)
        mask = pred.to(torch.uint8).cpu().numpy()
        confidence = conf.cpu().numpy()
        entropy = -(probs * probs.clamp_min(1e-8).log()).sum(0) / np.log(max(2, self.mapping.num_classes))

        stats = compute_area_stats(mask, self.mapping, self.config.min_leaf_pixels)
        plant = np.isin(mask, self.mapping.disease_ids + self.mapping.leaf_ids) if self.mapping.has_leaf_annotation \
            else np.isin(mask, self.mapping.disease_ids)
        disease = np.isin(mask, self.mapping.disease_ids)
        return SegmentationResult(
            status="ok", image_width=width, image_height=height, mask_width=mask_w, mask_height=mask_h,
            regions=extract_regions(mask, confidence, self.mapping),
            mean_confidence=round(float(confidence[disease].mean()), 4) if disease.any() else None,
            mean_uncertainty=round(float(entropy.cpu().numpy()[plant].mean()), 4) if plant.any() else None,
            model_name=self.card.get("name"), model_version=self.card.get("version"),
            inference_ms=int((time.perf_counter() - start) * 1000),
            created_at=datetime.now(timezone.utc).isoformat(), mask=mask, **stats,
        )
