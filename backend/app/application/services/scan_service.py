"""
ScanOrchestrator — orchestrates the full Scan Plant use case (UC-03, FR-SCAN,
FR-AI, FR-TREAT, FR-WEATHER, FR-REPORT), following the sequence diagram
`docs/02-system-design/07a-sequence-scan-plant.mermaid`, extended by pipeline 2.0:

  1. Validate the upload by its decoded content (format, size, pixel count).
  2. Image-quality gate BEFORE anything is stored: unsuitable photos are rejected with
     actionable feedback and never reach the classifier.
  3. Resolve/verify the target plant profile (owned by the caller) if one was given.
  4. Run the AI pipeline (calibrated classification, decision status, Grad-CAM,
     segmentation if a trained model exists).
  5. Persist the result as an immutable, time-stamped observation with full
     provenance (decision status, candidates, quality report, model & pipeline
     versions, severity method). Uncertain and inconclusive results are stored too —
     they are real observations — but no disease is asserted for them.
  6. Differential-diagnosis context, weather (best-effort), recommendations,
     optional Gemini explanation (confident results only), PDF report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from PIL import Image

from app.application.services.gemini_analysis_service import GeminiAnalysisService
from app.application.services.image_validation import validate_image_bytes
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.domain.entities.diagnosis import Diagnosis, Recommendation, SeverityLevel, WeatherSnapshot
from app.domain.entities.tracking import PlantProfile
from app.domain.labels import display_label, is_healthy_label
from app.domain.repositories.interfaces import IDiagnosisRepository, IDiseaseRepository, IPlantRepository, ITreatmentRepository
from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
from app.infrastructure.external.gemini_client import GeminiRequestContext
from app.infrastructure.external.weather_client import WeatherService
from app.infrastructure.reporting.pdf_report_generator import PdfReportGenerator, ReportData
from app.infrastructure.storage.object_storage import IObjectStorage, generate_storage_key

logger = logging.getLogger("agriguard.scan_orchestrator")
settings = get_settings()

REPORT_LIMITATIONS = [
    "This is an automated, image-based assessment of one photo, not a laboratory or field diagnosis.",
    "The model only recognizes the disease classes it was trained on. It cannot recognize pests, "
    "nutrient deficiencies, water or heat stress, or diseases outside its training data.",
    "The training data contain no healthy-plant images, so the model cannot confirm that a plant is healthy.",
    "Model confidence is a calibrated probability on held-out data from the same source as training, "
    "not a guarantee for a field photo.",
]


@dataclass
class ScanResult:
    status: str  # "completed" | "rejected_image_quality"
    diagnosis: Optional[Diagnosis] = None
    message: Optional[str] = None
    quality: Optional[dict] = None


class ScanOrchestrator:
    def __init__(
        self,
        storage: IObjectStorage,
        ai_client: AiPipelineClient,
        plant_repo: IPlantRepository,
        disease_repo: IDiseaseRepository,
        treatment_repo: ITreatmentRepository,
        diagnosis_repo: IDiagnosisRepository,
        weather_service: WeatherService,
        pdf_generator: PdfReportGenerator,
        gemini_service: Optional[GeminiAnalysisService] = None,
        plant_profile_repo=None,
        note_repo=None,
    ):
        self.storage = storage
        self.ai_client = ai_client
        self.plant_repo = plant_repo
        self.disease_repo = disease_repo
        self.treatment_repo = treatment_repo
        self.diagnosis_repo = diagnosis_repo
        self.weather_service = weather_service
        self.pdf_generator = pdf_generator
        # Optional: constructing ScanOrchestrator without a gemini_service simply means
        # the AI Agricultural Analysis section is skipped, same as if GEMINI_API_KEY
        # were unset — never a hard dependency.
        self.gemini_service = gemini_service or GeminiAnalysisService()
        self.plant_profile_repo = plant_profile_repo
        self.note_repo = note_repo

    # ------------------------------------------------------------------
    def process_scan(self, user_id: UUID, image_bytes: bytes, content_type: str,
                      latitude: Optional[float] = None, longitude: Optional[float] = None,
                      attach_location: bool = False, plant_profile_id: Optional[UUID] = None,
                      new_plant_name: Optional[str] = None, user_note: Optional[str] = None) -> ScanResult:
        # --- FR-SCAN-2: validate the image by its decoded content ---
        validated = validate_image_bytes(image_bytes)
        image = validated.image

        # --- Quality gate: before storing anything or running the classifier ---
        from ai.quality.image_quality import assess_image_quality  # ai/ is on sys.path via ai_pipeline_client

        quality = assess_image_quality(image)
        if quality.rejected:
            return ScanResult(status="rejected_image_quality", quality=quality.to_dict(),
                              message="The photo is not suitable for analysis. Please retake it.")

        # --- Resolve the plant profile (ownership verified server-side) ---
        profile = self._resolve_plant_profile(user_id, plant_profile_id, new_plant_name, dry_run=True)

        # --- FR-SCAN-3: strip EXIF unless the user opted in to attaching location ---
        original_ref = self._save_original_image(image)
        image_local_path = self.storage.resolve_path(original_ref)
        heatmap_ref = generate_storage_key("heatmaps", "png")
        seg_mask_ref = generate_storage_key("segmentation", "png")
        seg_overlay_ref = generate_storage_key("segmentation", "jpg")

        try:
            out = self.ai_client.diagnose(
                image_local_path,
                heatmap_output_path=self.storage.resolve_path(heatmap_ref),
                seg_mask_output_path=self.storage.resolve_path(seg_mask_ref),
                seg_overlay_output_path=self.storage.resolve_path(seg_overlay_ref),
            )
        except AiPipelineUnavailableError as exc:
            raise ServiceUnavailableError(str(exc))

        if getattr(out, "status", "completed") == "rejected_quality":
            return ScanResult(status="rejected_image_quality", quality=out.quality,
                              message="The photo is not suitable for analysis. Please retake it.")

        decision_status = getattr(out, "decision_status", None) or ("uncertain" if out.low_confidence_flag else "confident")
        confident = decision_status == "confident"
        candidates = list(getattr(out, "top_k", []) or [])

        # --- Knowledge-base records: only a CONFIDENT non-healthy result is linked to
        # a disease record. Uncertain/inconclusive results never assert a disease. ---
        plant_entity = self.plant_repo.get_or_create(out.plant) if out.plant else None
        disease_entity = None
        if confident and plant_entity and out.condition and out.condition != "healthy":
            disease_entity = self.disease_repo.get_current_by_plant_and_name(plant_entity.id, out.condition)

        # --- Differential diagnosis context (candidates + non-model look-alikes) ---
        differential = self._build_differential(candidates, decision_status)

        # --- Step 9: weather (best-effort, never blocks the pipeline — NFR-AVAIL-2) ---
        weather_snapshot = self._weather(latitude, longitude)

        # --- Step 10: recommendations ---
        recommendation = self._build_recommendation(out, decision_status, weather_snapshot)

        # --- Gemini explanation layer: only for a confident result, because its prompt
        # treats the CV result as the diagnosis to explain. ---
        ai_analysis = None
        if confident:
            ai_analysis = self._run_gemini_analysis(validated, out, plant_entity, disease_entity, weather_snapshot)

        explanation = dict(getattr(out, "explanation", {}) or {})
        segmentation = dict(getattr(out, "segmentation", {}) or {})
        heatmap_exists = self.storage.exists(heatmap_ref)
        mask_exists = self.storage.exists(seg_mask_ref)
        overlay_exists = self.storage.exists(seg_overlay_ref)
        for key in ("mask_path", "overlay_path"):
            segmentation.pop(key, None)  # never persist server filesystem paths

        severity = SeverityLevel(out.severity_level) if getattr(out, "severity_level", None) else None
        profile = self._resolve_plant_profile(user_id, plant_profile_id, new_plant_name, dry_run=False,
                                              resolved=profile, crop_type=out.plant)
        diagnosis = Diagnosis(
            id=None, user_id=user_id, plant_id=plant_entity.id if plant_entity else None,
            disease_id=disease_entity.id if disease_entity else None,
            confidence_score=out.confidence_score, severity_level=severity,
            affected_area_pct=out.affected_area_pct, healthy_area_pct=out.healthy_area_pct,
            original_image_ref=original_ref, heatmap_image_ref=heatmap_ref if heatmap_exists else None,
            low_confidence_flag=out.low_confidence_flag, unrecognized_plant=bool(out.unrecognized_plant),
            location_lat=latitude if attach_location else None, location_lon=longitude if attach_location else None,
            weather_snapshot=weather_snapshot, recommendation=recommendation, ai_analysis=ai_analysis,
            plant_profile_id=profile.id if profile else None,
            decision_status=decision_status,
            predicted_label=getattr(out, "canonical_label", None) or (candidates[0].get("canonical") if candidates else None),
            candidates=candidates,
            decision={**(getattr(out, "decision", {}) or {}), "thresholds": getattr(out, "thresholds", {}),
                      "plant_probability_mass": getattr(out, "plant_probability_mass", None),
                      "raw_top1_probability": getattr(out, "raw_top1_probability", None)},
            image_quality=getattr(out, "quality", None) or quality.to_dict(),
            explanation=explanation,
            segmentation=segmentation,
            segmentation_mask_ref=seg_mask_ref if mask_exists else None,
            segmentation_overlay_ref=seg_overlay_ref if overlay_exists else None,
            severity_method=getattr(out, "severity_method", None),
            model_version=getattr(out, "model_version", None),
            pipeline_version=getattr(out, "pipeline_version", None),
            differential=differential,
        )
        saved = self.diagnosis_repo.create(diagnosis)

        if user_note and self.note_repo is not None:
            from app.domain.entities.tracking import ObservationNote
            self.note_repo.add(ObservationNote(id=None, diagnosis_id=saved.id, author_user_id=user_id,
                                               note_type="user_note", body=user_note.strip()[:4000]))

        # --- Step 11: generate PDF report (BR5) and attach it ---
        try:
            report_key = self._generate_report(saved, plant_entity, disease_entity, image_local_path)
            self.diagnosis_repo.attach_report(saved.id, file_ref=report_key, qr_code_ref=report_key)
        except Exception as exc:  # noqa: BLE001 - a report failure must not lose the observation
            logger.warning("PDF report generation failed for %s: %s", saved.id, exc)

        return ScanResult(status="completed", diagnosis=self.diagnosis_repo.get_by_id(saved.id))

    # ------------------------------------------------------------------
    def _resolve_plant_profile(self, user_id: UUID, plant_profile_id: Optional[UUID], new_plant_name: Optional[str],
                               dry_run: bool, resolved: Optional[PlantProfile] = None,
                               crop_type: Optional[str] = None) -> Optional[PlantProfile]:
        if plant_profile_id is not None and new_plant_name:
            raise ValidationError("Choose an existing plant or a new plant name, not both.")
        if plant_profile_id is not None:
            if resolved is not None:
                return resolved
            if self.plant_profile_repo is None:
                raise ValidationError("Plant tracking is not available.")
            profile = self.plant_profile_repo.get_owned(plant_profile_id, user_id)
            if profile is None or profile.archived_at is not None:
                raise NotFoundError("Plant not found.")
            return profile
        if new_plant_name:
            name = new_plant_name.strip()
            if not name or len(name) > 100:
                raise ValidationError("Plant name must be 1–100 characters.")
            if dry_run or self.plant_profile_repo is None:
                return None
            return self.plant_profile_repo.create(PlantProfile(
                id=None, owner_user_id=user_id, name=name, crop_type=crop_type))
        return None

    def _weather(self, latitude, longitude) -> Optional[WeatherSnapshot]:
        if latitude is None or longitude is None:
            return None
        conditions = self.weather_service.get_conditions(latitude, longitude)
        if conditions is None:
            return None
        return WeatherSnapshot(
            id=None, diagnosis_id=None, temperature_c=conditions.temperature_c,
            humidity_pct=conditions.humidity_pct, wind_speed_kmh=conditions.wind_speed_kmh,
            rain_probability_pct=conditions.rain_probability_pct, uv_index=conditions.uv_index,
            retrieved_at=conditions.retrieved_at,
        )

    @staticmethod
    def _build_differential(candidates: list, decision_status: str) -> dict:
        try:
            from ai.knowledge.differential import build_differential
            return build_differential(candidates, decision_status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Differential diagnosis context unavailable: %s", exc)
            return {}

    def _run_gemini_analysis(self, validated, out, plant_entity, disease_entity, weather_snapshot):
        # Belt-and-suspenders: GeminiAnalysisService/GeminiClient already never raise,
        # but an unforeseen bug in that layer must not take down the scan pipeline.
        try:
            weather_summary = self._weather_summary(weather_snapshot)
            from io import BytesIO
            buf = BytesIO()
            validated.image.convert("RGB").save(buf, format="JPEG", quality=90)  # EXIF-free copy
            ctx = GeminiRequestContext(
                image_bytes=buf.getvalue(), image_mime_type="image/jpeg",
                plant_name=plant_entity.canonical_name if plant_entity else None,
                cv_condition=disease_entity.name if disease_entity else out.condition,
                cv_confidence_score=out.confidence_score,
                cv_severity_level=out.severity_level,
                cv_affected_area_pct=out.affected_area_pct,
                disease_description=disease_entity.description if disease_entity else None,
                disease_symptoms=disease_entity.symptoms if disease_entity else [],
                weather_summary=weather_summary,
            )
            return self.gemini_service.analyze(ctx, self.plant_repo, self.disease_repo, self.treatment_repo)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini analysis step raised unexpectedly and was skipped: %s", exc)
            return None

    @staticmethod
    def _weather_summary(weather_snapshot) -> Optional[str]:
        if not weather_snapshot:
            return None
        return (
            f"Temperature: {weather_snapshot.temperature_c}°C, Humidity: {weather_snapshot.humidity_pct}%, "
            f"Wind: {weather_snapshot.wind_speed_kmh} km/h, Rain probability: "
            f"{weather_snapshot.rain_probability_pct}%, UV Index: {weather_snapshot.uv_index}"
        )

    def _save_original_image(self, image: Image.Image) -> str:
        # Strip EXIF (incl. GPS) by re-encoding a fresh RGB copy (FR-SCAN-3).
        from io import BytesIO
        from PIL import ImageOps

        buf = BytesIO()
        ImageOps.exif_transpose(image).convert("RGB").save(buf, format="JPEG", quality=92)
        key = generate_storage_key("scans", "jpg")
        return self.storage.save_bytes(buf.getvalue(), key)

    @staticmethod
    def _build_recommendation(out, decision_status: str, weather_snapshot) -> Recommendation:
        """Weather-aware practical advice. Spraying advice is only given for a confident
        disease result — recommending spraying for an unconfirmed condition would push
        users toward unnecessary pesticide use. Weather is never used as evidence of a
        disease."""
        irrigation_advice = spraying_advice = fertilizer_advice = None
        diseased_confident = (decision_status == "confident" and out.condition and out.condition != "healthy")

        if weather_snapshot is not None:
            rain = weather_snapshot.rain_probability_pct
            if rain is not None and rain >= 60:
                irrigation_advice = "Rain is likely in the next few hours — delay irrigation; rainfall may be sufficient."
                if diseased_confident:
                    spraying_advice = "Rain is likely — if a treatment is applied, wait for a dry window to avoid wash-off."
            elif diseased_confident:
                if weather_snapshot.humidity_pct is not None and weather_snapshot.humidity_pct >= 85:
                    spraying_advice = ("Humidity is high, which favours many foliar diseases. Follow the product "
                                       "label and local guidance if a treatment is chosen.")
                elif weather_snapshot.wind_speed_kmh is not None and weather_snapshot.wind_speed_kmh >= 15:
                    spraying_advice = "Wind is strong — avoid spraying now to limit drift."
            if weather_snapshot.temperature_c is not None and weather_snapshot.temperature_c >= 35:
                irrigation_advice = ((irrigation_advice + " ") if irrigation_advice else "") + \
                    "High temperature — irrigate early in the morning or in the evening."

        if decision_status != "confident":
            fertilizer_advice = None
        elif out.condition == "healthy":
            fertilizer_advice = "Maintain your regular fertilizing schedule."

        return Recommendation(id=None, diagnosis_id=None, irrigation_advice=irrigation_advice,
                              spraying_advice=spraying_advice, fertilizer_advice=fertilizer_advice)

    def _generate_report(self, diagnosis: Diagnosis, plant_entity, disease_entity, image_local_path: Path) -> str:
        treatments = self.treatment_repo.get_current_for_disease(disease_entity.id) if disease_entity else []
        organic = next((t.instructions for t in treatments if t.category.value == "organic"), None)
        chemical_treatment = next((t for t in treatments if t.category.value == "chemical"), None)
        chemical = None
        if chemical_treatment:
            if chemical_treatment.is_dosage_verified() and not chemical_treatment.authority_referral_only:
                chemical = chemical_treatment.instructions
            else:
                chemical = ("Please consult your local agricultural authority for verified dosage "
                            "guidance for this treatment.")
        biological = next((t.instructions for t in treatments if t.category.value == "biological"), None)

        status = diagnosis.decision_status or "legacy"
        label = diagnosis.predicted_label
        if status == "inconclusive":
            disease_name = "Inconclusive — no condition named"
            description = ("The model could not identify the condition with enough evidence. Retake the photo "
                           "(single leaf, even daylight, in focus) or ask an agricultural expert.")
        elif disease_entity:
            disease_name = disease_entity.name
            description = disease_entity.description
        elif is_healthy_label(label) and status == "confident":
            disease_name = "No disease recognized (healthy class)"
            description = "The model's leading class is a healthy-plant class."
        else:
            disease_name = display_label(label) or "Unknown"
            if status == "uncertain":
                disease_name += " (leading candidate — uncertain)"
            description = ("No curated description is available for this condition in the AgriGuard knowledge base yet."
                           if status == "confident" else
                           "The model is not confident. Several conditions are plausible; see the candidate list.")

        differential = diagnosis.differential or {}
        candidates = []
        for c in differential.get("model_candidates", []):
            candidates.append({**c, "display": display_label(c.get("label"))})
        quality_notes = [i.get("message") for i in (diagnosis.image_quality or {}).get("issues", []) if i.get("message")]

        report_key = generate_storage_key("reports", "pdf")
        report_local_path = self.storage.resolve_path(report_key)
        report_local_path.parent.mkdir(parents=True, exist_ok=True)
        heatmap_path = self.storage.resolve_path(diagnosis.heatmap_image_ref) if diagnosis.heatmap_image_ref else None
        seg_path = (self.storage.resolve_path(diagnosis.segmentation_overlay_ref)
                    if diagnosis.segmentation_overlay_ref else None)

        data = ReportData(
            diagnosis_id=str(diagnosis.id),
            plant_name=plant_entity.canonical_name.replace("_", " ").title() if plant_entity else "Not identified",
            disease_name=disease_name, disease_description=description,
            severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
            confidence_score=diagnosis.confidence_score, affected_area_pct=diagnosis.affected_area_pct,
            healthy_area_pct=diagnosis.healthy_area_pct, organic_treatment=organic, chemical_treatment=chemical,
            biological_treatment=biological,
            prevention_advice=(["Remove and destroy clearly infected plant material.",
                                "Avoid overhead irrigation late in the day; improve air circulation.",
                                "Practice crop rotation and field sanitation where applicable."]
                               if status == "confident" and disease_entity else []),
            weather_summary=self._weather_summary(diagnosis.weather_snapshot),
            diagnosed_at=diagnosis.diagnosed_at or datetime.now(timezone.utc),
            original_image_path=str(image_local_path),
            heatmap_image_path=str(heatmap_path) if heatmap_path and heatmap_path.exists() else None,
            report_verification_url=f"{settings.api_prefix}/reports/{diagnosis.id}",
            decision_status=status, candidates=candidates if status != "confident" else candidates[:3],
            model_version=diagnosis.model_version, pipeline_version=diagnosis.pipeline_version,
            severity_basis=diagnosis.severity_method, quality_notes=quality_notes,
            expert_review_recommended=bool(differential.get("expert_review_recommended")),
            limitations=REPORT_LIMITATIONS,
            segmentation_overlay_path=str(seg_path) if seg_path and seg_path.exists() else None,
        )
        self.pdf_generator.generate(data, str(report_local_path))
        return report_key
