"""
InferenceService — the reusable AI pipeline engine (FR-AI-1..7) used by both
predict.py / inference.py (CLI) and the FastAPI backend's AI integration layer
(backend/app/infrastructure/external/ai_pipeline_client.py). Implemented once here so
CLI and API never diverge in behavior.

Loads the most recent (or an explicitly given) training run's artifacts — model
weights, label encoder, preprocessing config — and exposes `diagnose(image)` which
runs the full Steps 1-7 chain from the DFD Level 2 design:
  identify plant -> classify disease -> (pest detection via same classifier's
  pest-labeled classes) -> localize region -> estimate severity -> confidence score
  -> explainability heatmap.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
import torch.nn.functional as F
from PIL import Image

from ai.config import CONFIG
from ai.data.label_encoder import LabelEncoder
from ai.data.preprocessing import PreprocessingConfig, build_eval_transform
from ai.explainability.factory import get_explainer, render_heatmap_overlay
from ai.explainability.severity import estimate_severity, localize_region
from ai.models.architectures import build_classifier, resolve_device
from ai.training.artifact_manager import ArtifactManager

logger = logging.getLogger("agriguard.inference")


@dataclass
class DiagnosisOutput:
    unrecognized_plant: bool
    plant: Optional[str] = None
    condition: Optional[str] = None
    canonical_label: Optional[str] = None
    confidence_score: float = 0.0
    low_confidence_flag: bool = False
    severity_level: Optional[str] = None
    affected_area_pct: Optional[float] = None
    healthy_area_pct: Optional[float] = None
    bounding_box: Optional[dict] = None
    top_k: list = field(default_factory=list)
    heatmap_overlay_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "unrecognized_plant": self.unrecognized_plant,
            "plant": self.plant,
            "condition": self.condition,
            "canonical_label": self.canonical_label,
            "confidence_score": self.confidence_score,
            "low_confidence_flag": self.low_confidence_flag,
            "severity_level": self.severity_level,
            "affected_area_pct": self.affected_area_pct,
            "healthy_area_pct": self.healthy_area_pct,
            "bounding_box": self.bounding_box,
            "top_k": self.top_k,
            "heatmap_overlay_path": self.heatmap_overlay_path,
        }


class InferenceService:
    def __init__(self, run_dir: Optional[Path] = None):
        self.run_dir = run_dir or ArtifactManager.load_latest_run_dir()
        logger.info("Loading inference artifacts from: %s", self.run_dir)

        self.label_encoder = LabelEncoder.load(self.run_dir / "label_encoder.json")
        self.preprocessing_config = PreprocessingConfig.load(self.run_dir / "preprocessing_config.json")

        model_meta = json.loads((self.run_dir / "model_meta.json").read_text())
        self.architecture = model_meta["architecture"]
        num_classes = model_meta["num_classes"]

        self.device = resolve_device(CONFIG.train.device)
        self.model = build_classifier(self.architecture, num_classes=num_classes, pretrained=False)
        state_dict = torch.load(self.run_dir / "model.pt", map_location=self.device)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.model.eval()

        self.eval_transform = build_eval_transform(self.preprocessing_config)
        self.explainer = get_explainer(self.architecture)

    def _predict_logits(self, image: Image.Image) -> torch.Tensor:
        tensor = self.eval_transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
        return logits, tensor

    def diagnose(self, image: Image.Image, top_k: int = 3,
                 save_heatmap_to: Optional[Path] = None) -> DiagnosisOutput:
        logits, input_tensor = self._predict_logits(image)
        probs = F.softmax(logits, dim=1)[0]
        confidence, pred_idx = torch.max(probs, dim=0)
        confidence = float(confidence.item()) * 100.0
        pred_idx = int(pred_idx.item())

        decoded = self.label_encoder.decode_to_plant_condition(pred_idx)

        # Step 1 gate: plant identification confidence (FR-AI-12).
        # We approximate "plant identification confidence" as the summed probability
        # mass of all classes sharing the predicted plant, since the classifier is
        # trained jointly over "{plant}___{condition}" classes rather than as two
        # separate models (a valid simplification per MODEL_ARCHITECTURE_DECISIONS.md
        # — one multi-task head is more data-efficient on merged datasets than two
        # independently-trained classifiers).
        plant_mass = self._plant_probability_mass(probs, decoded["plant"])
        if plant_mass < CONFIG.inference.plant_id_confidence_threshold:
            return DiagnosisOutput(unrecognized_plant=True, confidence_score=round(plant_mass * 100, 2))

        top_k_indices = torch.topk(probs, k=min(top_k, probs.numel())).indices.tolist()
        top_k_results = [
            {**self.label_encoder.decode_to_plant_condition(i), "confidence": round(float(probs[i].item()) * 100, 2)}
            for i in top_k_indices
        ]

        low_confidence = confidence < (CONFIG.inference.disease_low_confidence_threshold * 100)

        # Explainability heatmap -> localization + severity (Steps 4, 5, 7).
        try:
            heatmap = self.explainer.explain(self.model, input_tensor, pred_idx)
            severity = estimate_severity(heatmap)
            region = localize_region(heatmap)
            bbox = {"x_min": region.x_min, "y_min": region.y_min, "x_max": region.x_max, "y_max": region.y_max}
            heatmap_path = None
            if save_heatmap_to is not None:
                overlay = render_heatmap_overlay(image, heatmap)
                save_heatmap_to.parent.mkdir(parents=True, exist_ok=True)
                overlay.save(save_heatmap_to)
                heatmap_path = str(save_heatmap_to)
        except Exception as exc:  # noqa: BLE001 — explainability failure must not break diagnosis
            logger.warning("Explainability step failed (%s); returning diagnosis without heatmap.", exc)
            severity = None
            bbox = None
            heatmap_path = None

        return DiagnosisOutput(
            unrecognized_plant=False,
            plant=decoded["plant"],
            condition=decoded["condition"],
            canonical_label=decoded["canonical"],
            confidence_score=round(confidence, 2),
            low_confidence_flag=low_confidence,
            severity_level=severity.severity_level if severity else None,
            affected_area_pct=severity.affected_area_pct if severity else None,
            healthy_area_pct=severity.healthy_area_pct if severity else None,
            bounding_box=bbox,
            top_k=top_k_results,
            heatmap_overlay_path=heatmap_path,
        )

    def _plant_probability_mass(self, probs: torch.Tensor, plant: str) -> float:
        mass = 0.0
        for i, class_name in enumerate(self.label_encoder.classes):
            if class_name.startswith(f"{plant}___"):
                mass += float(probs[i].item())
        return mass
