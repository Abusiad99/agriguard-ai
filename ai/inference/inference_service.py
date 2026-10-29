"""
InferenceService — the reusable AI pipeline engine (FR-AI-1..7) used by both
predict.py / inference.py (CLI) and the FastAPI backend's AI integration layer
(backend/app/infrastructure/external/ai_pipeline_client.py). Implemented once here so
CLI and API never diverge in behavior.

Pipeline (version PIPELINE_VERSION):
  1. Image-quality gate (ai/quality) — unsuitable photos are rejected with
     actionable feedback BEFORE the classifier runs, so a blurry or black image can
     never come back as a confident disease (or "healthy") result.
  2. Classification with temperature-calibrated probabilities (calibration.json,
     fitted on the validation split; uncalibrated runs are reported as such).
  3. Decision status — confident / uncertain / inconclusive — using thresholds
     selected on validation data (ai/inference/decision.py). Nothing is forced into
     a single class when the evidence is insufficient.
  4. Explanation — Grad-CAM for CNNs ("model attention", NOT a lesion mask).
  5. Affected-area measurement — ONLY from a trained leaf/lesion segmentation model
     (ai/segmentation). Without one, severity is reported as unavailable. (Earlier
     versions thresholded the Grad-CAM map and reported that as "affected area" and
     severity; that was not a measurement and has been removed.)

Thread safety: FastAPI runs sync handlers in a thread pool and this service is a
process-wide singleton, so model forward passes and Grad-CAM (which temporarily
registers hooks on the shared model) are serialized with a lock.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image, ImageOps

from ai.config import CONFIG
from ai.data.label_encoder import LabelEncoder
from ai.data.preprocessing import PreprocessingConfig, build_eval_transform
from ai.explainability.base import ExplanationUnavailableError
from ai.explainability.factory import get_explainer, render_heatmap_overlay
from ai.inference.calibration import CalibrationArtifact, softmax
from ai.inference.decision import CONFIDENT, INCONCLUSIVE, decide, resolve_thresholds
from ai.models.architectures import build_classifier, resolve_device
from ai.quality.image_quality import assess_image_quality
from ai.training.artifact_manager import ArtifactManager

logger = logging.getLogger("agriguard.inference")

PIPELINE_VERSION = "2.0.0"


@dataclass
class DiagnosisOutput:
    # "completed" when the classifier ran; "rejected_quality" when the quality gate
    # stopped the pipeline before classification.
    status: str = "completed"
    unrecognized_plant: bool = False
    plant: Optional[str] = None
    condition: Optional[str] = None
    canonical_label: Optional[str] = None
    confidence_score: float = 0.0           # calibrated top-1 probability, in %
    low_confidence_flag: bool = False        # True for every status except "confident"
    decision_status: Optional[str] = None    # confident | uncertain | inconclusive
    decision: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    plant_probability_mass: Optional[float] = None
    raw_top1_probability: Optional[float] = None  # uncalibrated softmax, for audit
    severity_level: Optional[str] = None
    affected_area_pct: Optional[float] = None
    healthy_area_pct: Optional[float] = None
    severity_method: Optional[str] = None
    segmentation: dict = field(default_factory=dict)
    top_k: list = field(default_factory=list)
    heatmap_overlay_path: Optional[str] = None
    explanation: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    model_version: Optional[str] = None
    pipeline_version: str = PIPELINE_VERSION
    inference_ms: Optional[float] = None

    @property
    def bounding_box(self):  # kept for backward compatibility; no longer derived from Grad-CAM
        return None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "unrecognized_plant": self.unrecognized_plant,
            "plant": self.plant,
            "condition": self.condition,
            "canonical_label": self.canonical_label,
            "confidence_score": self.confidence_score,
            "low_confidence_flag": self.low_confidence_flag,
            "decision_status": self.decision_status,
            "decision": self.decision,
            "thresholds": self.thresholds,
            "plant_probability_mass": self.plant_probability_mass,
            "raw_top1_probability": self.raw_top1_probability,
            "severity_level": self.severity_level,
            "affected_area_pct": self.affected_area_pct,
            "healthy_area_pct": self.healthy_area_pct,
            "severity_method": self.severity_method,
            "segmentation": self.segmentation,
            "top_k": self.top_k,
            "heatmap_overlay_path": self.heatmap_overlay_path,
            "explanation": self.explanation,
            "quality": self.quality,
            "model_version": self.model_version,
            "pipeline_version": self.pipeline_version,
            "inference_ms": self.inference_ms,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class InferenceService:
    def __init__(self, run_dir: Optional[Path] = None, segmentation_service=None):
        self.run_dir = run_dir or ArtifactManager.load_latest_run_dir()
        logger.info("Loading inference artifacts from: %s", self.run_dir)

        self.label_encoder = LabelEncoder.load(self.run_dir / "label_encoder.json")
        self.preprocessing_config = PreprocessingConfig.load(self.run_dir / "preprocessing_config.json")

        model_meta = json.loads((self.run_dir / "model_meta.json").read_text())
        self.architecture = model_meta["architecture"]
        num_classes = model_meta["num_classes"]

        self.device = resolve_device(CONFIG.train.device)
        self.model = build_classifier(self.architecture, num_classes=num_classes, pretrained=False)
        state_dict = torch.load(self.run_dir / "model.pt", map_location=self.device, weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.model.eval()
        self.model_version = f"{self.run_dir.name}:{_sha256(self.run_dir / 'model.pt')[:12]}"

        self.calibration = CalibrationArtifact.load(self.run_dir)
        self.thresholds = resolve_thresholds(self.calibration)
        if self.calibration is None:
            logger.warning("No calibration.json in %s — confidences are raw softmax scores and the decision "
                           "thresholds are unvalidated defaults. Run `python calibrate.py`.", self.run_dir)

        self.eval_transform = build_eval_transform(self.preprocessing_config)
        self.explainer = get_explainer(self.architecture)
        self._lock = threading.Lock()

        if segmentation_service is None:
            try:
                from ai.segmentation.service import SegmentationService
                segmentation_service = SegmentationService(device=self.device)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Segmentation service unavailable: %s", exc)
                segmentation_service = None
        self.segmentation = segmentation_service

    # ------------------------------------------------------------------
    @property
    def supported_classes(self) -> list:
        return list(self.label_encoder.classes)

    def _predict_logits(self, image: Image.Image):
        tensor = self.eval_transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
        return logits, tensor

    def _plant_probability_mass(self, probs: np.ndarray, plant: str) -> float:
        prefix = f"{plant}___"
        return float(sum(probs[i] for i, c in enumerate(self.label_encoder.classes) if c.startswith(prefix)))

    def diagnose(self, image: Image.Image, top_k: int = 3,
                 save_heatmap_to: Optional[Path] = None,
                 save_seg_mask_to: Optional[Path] = None,
                 save_seg_overlay_to: Optional[Path] = None,
                 run_quality_gate: bool = True) -> DiagnosisOutput:
        start = time.perf_counter()
        image = ImageOps.exif_transpose(image).convert("RGB")

        quality = assess_image_quality(image)
        if run_quality_gate and quality.rejected:
            return DiagnosisOutput(status="rejected_quality", quality=quality.to_dict(),
                                   model_version=self.model_version, low_confidence_flag=True,
                                   inference_ms=round((time.perf_counter() - start) * 1000, 1))

        with self._lock:
            logits, input_tensor = self._predict_logits(image)
        logits_np = logits.detach().cpu().numpy().astype(np.float64)
        raw_probs = softmax(logits_np, 1.0)[0]
        probs = softmax(logits_np, self.thresholds.temperature)[0]

        order = np.argsort(-probs)
        pred_idx = int(order[0])
        decoded = self.label_encoder.decode_to_plant_condition(pred_idx)
        plant_mass = self._plant_probability_mass(probs, decoded["plant"])
        decision = decide(probs, plant_mass, self.thresholds)

        k = max(1, min(top_k, len(probs)))
        top_k_results = [
            {**self.label_encoder.decode_to_plant_condition(int(i)),
             "confidence": round(float(probs[int(i)]) * 100, 2)}
            for i in order[:k]
        ]

        status = decision.status
        plant = decoded["plant"] if (status != INCONCLUSIVE or decision.plant_identified) else None
        condition = decoded["condition"] if status != INCONCLUSIVE else None
        canonical = decoded["canonical"] if status != INCONCLUSIVE else None

        # --- Explanation (model attention for the leading class) ---
        explanation = {"method": getattr(self.explainer, "method_name", None), "available": False,
                       "target_label": decoded["canonical"], "reason": None}
        heatmap_path = None
        if status == INCONCLUSIVE:
            explanation["reason"] = "not_generated_for_inconclusive_result"
        else:
            try:
                with self._lock:
                    heatmap = self.explainer.explain(self.model, input_tensor, pred_idx)
                if save_heatmap_to is not None:
                    overlay = render_heatmap_overlay(image, heatmap)
                    save_heatmap_to.parent.mkdir(parents=True, exist_ok=True)
                    overlay.save(save_heatmap_to)
                    heatmap_path = str(save_heatmap_to)
                explanation["available"] = True
            except ExplanationUnavailableError as exc:
                explanation["reason"] = str(exc)
            except Exception as exc:  # noqa: BLE001 — explainability failure must not break diagnosis
                logger.warning("Explainability step failed (%s); returning diagnosis without heatmap.", exc)
                explanation["reason"] = "explanation_failed"

        # --- Segmentation-based affected area (only from a trained segmentation model) ---
        segmentation = {"status": "unavailable", "reason": "no_segmentation_model"}
        severity_level = affected = healthy = severity_method = None
        if self.segmentation is not None and status != INCONCLUSIVE:
            seg = self.segmentation.measure(
                image, plant=decoded["plant"], condition=decoded["condition"],
                save_mask_to=save_seg_mask_to, save_overlay_to=save_seg_overlay_to)
            segmentation = seg.to_dict()
            if seg.status == "measured" and seg.measurement is not None:
                affected = seg.measurement.affected_area_pct
                healthy = seg.measurement.healthy_area_pct
                severity_method = seg.method
                severity_level = seg.severity.get("level")
        elif status == INCONCLUSIVE:
            segmentation = {"status": "unavailable", "reason": "not_run_for_inconclusive_result"}

        return DiagnosisOutput(
            status="completed",
            unrecognized_plant=(status == INCONCLUSIVE and not decision.plant_identified),
            plant=plant,
            condition=condition,
            canonical_label=canonical,
            confidence_score=round(decision.top1_probability * 100, 2),
            low_confidence_flag=(status != CONFIDENT),
            decision_status=status,
            decision=decision.to_dict(),
            thresholds=self.thresholds.to_dict(),
            plant_probability_mass=round(plant_mass, 4),
            raw_top1_probability=round(float(raw_probs[pred_idx]), 4),
            severity_level=severity_level,
            affected_area_pct=affected,
            healthy_area_pct=healthy,
            severity_method=severity_method,
            segmentation=segmentation,
            top_k=top_k_results,
            heatmap_overlay_path=heatmap_path,
            explanation=explanation,
            quality=quality.to_dict(),
            model_version=self.model_version,
            inference_ms=round((time.perf_counter() - start) * 1000, 1),
        )
