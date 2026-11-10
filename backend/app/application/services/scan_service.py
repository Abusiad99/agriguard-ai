"""
ScanOrchestrator — orchestrates the full Scan Plant use case (UC-03, FR-SCAN,
FR-AI, FR-TREAT, FR-WEATHER, FR-REPORT), matching the sequence diagram
`docs/02-system-design/07a-sequence-scan-plant.mermaid` step for step.
"""
from __future__ import annotations

import io
import logging
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError

from app.application.reporting.recommendations import load_rules
from app.application.reporting.references import Citations
from app.application.reporting.weather_guidance import guidance as weather_guidance, measurements_text, weather_dict
from app.application.services.gemini_analysis_service import GeminiAnalysisService
from app.application.services.guidance import GENERIC_PREVENTION_ADVICE
from app.core.config import get_settings
from app.core.exceptions import InvalidImageError, ServiceUnavailableError
from app.domain.entities.diagnosis import (
    HEALTHY_CONDITION,
    Diagnosis,
    PestDetection,
    Recommendation,
    SeverityLevel,
    WeatherSnapshot,
)
from app.domain.repositories.interfaces import IDiagnosisRepository, IPlantRepository, ITreatmentRepository, IDiseaseRepository
from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
from app.infrastructure.db.models.ai_features_model import DiagnosisSegmentationModel
from app.infrastructure.external.model_clients import ModelUnavailable
from app.infrastructure.external.gemini_client import GeminiRequestContext
from app.infrastructure.external.weather_client import WeatherService
from app.infrastructure.reporting.pdf_report_generator import PdfReportGenerator, ReportData
from app.infrastructure.storage.object_storage import IObjectStorage, generate_storage_key

from ai.image_quality import assess as assess_image_quality

logger = logging.getLogger("agriguard.scan_orchestrator")
settings = get_settings()

# Shown (API response and PDF) when the CV model predicts a disease the knowledge
# base has no record for yet — never reported as "healthy".
UNLISTED_DISEASE_DESCRIPTION = (
    "This condition is not yet in the AgriGuard knowledge base, so no verified "
    "description or treatment is available. Please consult your local agricultural authority."
)


@dataclass
class ScanResult:
    status: str  # "completed" | "unrecognized_plant"
    diagnosis: Optional[Diagnosis] = None
    message: Optional[str] = None


def _top_predictions(diagnosis_output) -> Optional[list]:
    """The classifier's ranked alternatives, kept for reports. Only well-formed entries
    from the pipeline are stored; anything else (e.g. test doubles) is ignored."""
    ranked = getattr(diagnosis_output, "top_k", None)
    if not isinstance(ranked, list):
        return None
    out = [{"plant": r.get("plant"), "condition": r.get("condition"), "confidence": float(r["confidence"])}
           for r in ranked if isinstance(r, dict) and isinstance(r.get("confidence"), (int, float))]
    return out or None


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
        segmentation_client=None,
        segmentation_repo=None,
        outbreak_service=None,
        recovery_service=None,
    ):
        self.storage = storage
        self.ai_client = ai_client
        self.plant_repo = plant_repo
        self.disease_repo = disease_repo
        self.treatment_repo = treatment_repo
        self.diagnosis_repo = diagnosis_repo
        self.weather_service = weather_service
        self.pdf_generator = pdf_generator
        # Optional: constructing ScanOrchestrator without a gemini_service (e.g. in
        # older call sites or tests that don't care about it) simply means the AI
        # Agricultural Analysis section is skipped, same as if GEMINI_API_KEY were
        # unset — never a hard dependency.
        self.gemini_service = gemini_service or GeminiAnalysisService()
        # Optional AI-feature steps. Each is skipped when not wired in (older call
        # sites/tests) and none can fail the classification result.
        self.segmentation_client = segmentation_client
        self.segmentation_repo = segmentation_repo
        self.outbreak_service = outbreak_service
        self.recovery_service = recovery_service

    def process_scan(self, user_id: UUID, image_bytes: bytes, content_type: str,
                      latitude: Optional[float] = None, longitude: Optional[float] = None,
                      attach_location: bool = False, tracked_plant_id: Optional[UUID] = None,
                      treatment_stage: str = "unknown") -> ScanResult:
        # A follow-up scan must target the caller's own plant; check before doing any work.
        if tracked_plant_id is not None:
            if self.recovery_service is None:
                raise ServiceUnavailableError("Plant tracking is not available.")
            self.recovery_service.require_plant(user_id, tracked_plant_id)

        # --- FR-SCAN-2: validate the image is genuine and decodable ---
        # A small file can declare enormous dimensions ("decompression bomb"). Pillow warns
        # above Image.MAX_IMAGE_PIXELS and raises at twice that; both are rejected here, so
        # such an upload is a 400 instead of an unhandled error or gigabytes of pixels.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(image_bytes))
                image.verify()
                image = Image.open(io.BytesIO(image_bytes))  # re-open after verify() invalidates handle
                image.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise InvalidImageError("The image dimensions are too large to process. Please upload a smaller photo.")
        except (UnidentifiedImageError, OSError, ValueError):
            raise InvalidImageError("The uploaded file is not a valid, decodable image.")
        image_format = image.format
        # Phone photos often store their orientation as EXIF metadata. Apply it before the
        # EXIF is stripped below, so the saved photo, the classifier, the heatmap and the
        # segmentation overlay are all upright and aligned with what the user sees.
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:  # noqa: BLE001 - malformed EXIF: keep the pixels as stored
            pass

        # Quality checks (blur, exposure, size) travel with the result as caveats; they
        # never block the scan.
        image_quality = assess_image_quality(image).to_dict()

        # --- FR-SCAN-3: strip EXIF unless the user opted in to attaching location ---
        original_ref = self._save_original_image(image, image_bytes)

        # --- Steps 1-7: run the AI pipeline ---
        image_local_path = self.storage.resolve_path(original_ref)
        heatmap_ref = generate_storage_key("heatmaps", "png")
        heatmap_local_path = self.storage.resolve_path(heatmap_ref)

        try:
            diagnosis_output = self.ai_client.diagnose(image_local_path, heatmap_output_path=heatmap_local_path)
        except AiPipelineUnavailableError as exc:
            raise ServiceUnavailableError(str(exc))

        if diagnosis_output.unrecognized_plant:
            return ScanResult(
                status="unrecognized_plant",
                message="We could not confidently identify this plant. Please retake the photo "
                        "with clearer framing.",
            )

        # --- Resolve plant/disease knowledge base records ---
        plant_entity = self.plant_repo.get_or_create(diagnosis_output.plant)
        disease_entity = self.disease_repo.get_current_by_plant_and_name(plant_entity.id, diagnosis_output.condition)

        # --- Step 9: weather (best-effort, never blocks the pipeline — NFR-AVAIL-2) ---
        weather_snapshot = None
        if latitude is not None and longitude is not None:
            conditions = self.weather_service.get_conditions(latitude, longitude)
            if conditions is not None:
                weather_snapshot = WeatherSnapshot(
                    id=None, diagnosis_id=None, temperature_c=conditions.temperature_c,
                    humidity_pct=conditions.humidity_pct, wind_speed_kmh=conditions.wind_speed_kmh,
                    rain_probability_pct=conditions.rain_probability_pct, uv_index=conditions.uv_index,
                    retrieved_at=conditions.retrieved_at,
                )

        # --- Step 10: agricultural recommendation ---
        recommendation = self._build_recommendation(diagnosis_output, weather_snapshot)

        # --- Gemini multimodal reasoning layer (best-effort, additive — never
        # blocks or alters the CV diagnosis; see docs/GEMINI_INTEGRATION.md). Runs
        # after the CV result, disease lookup, and weather are all known, since
        # Gemini's job is to reason ABOUT them, not replace any of them. ---
        ai_analysis = self._run_gemini_analysis(
            image_bytes, image_format, diagnosis_output, plant_entity, disease_entity, weather_snapshot,
        )

        # --- Assemble and persist the Diagnosis aggregate (BR2: immutable) ---
        severity = SeverityLevel(diagnosis_output.severity_level) if diagnosis_output.severity_level else None
        diagnosis = Diagnosis(
            id=None, user_id=user_id, plant_id=plant_entity.id,
            disease_id=disease_entity.id if disease_entity else None,
            confidence_score=diagnosis_output.confidence_score, severity_level=severity,
            affected_area_pct=diagnosis_output.affected_area_pct, healthy_area_pct=diagnosis_output.healthy_area_pct,
            # No heatmap is written for healthy predictions or when explainability fails.
            original_image_ref=original_ref,
            heatmap_image_ref=heatmap_ref if self.storage.exists(heatmap_ref) else None,
            low_confidence_flag=diagnosis_output.low_confidence_flag, unrecognized_plant=False,
            predicted_condition=diagnosis_output.condition, image_quality=image_quality,
            top_predictions=_top_predictions(diagnosis_output),
            location_lat=latitude if attach_location else None, location_lon=longitude if attach_location else None,
            weather_snapshot=weather_snapshot, recommendation=recommendation, ai_analysis=ai_analysis,
        )
        saved_diagnosis = self.diagnosis_repo.create(diagnosis)

        # --- Step 11: generate PDF report (BR5) and attach it to the persisted diagnosis ---
        report_key = self._generate_report(saved_diagnosis, plant_entity, disease_entity, recommendation,
                                            weather_snapshot, image_local_path, heatmap_local_path)
        self.diagnosis_repo.attach_report(saved_diagnosis.id, file_ref=report_key, qr_code_ref=report_key)

        # --- Disease localization (separate segmentation model; optional) ---
        self._run_segmentation(saved_diagnosis.id, image)

        final = self.diagnosis_repo.get_by_id(saved_diagnosis.id)

        # --- Outbreak observation: only for scans whose owner attached a location ---
        if self.outbreak_service is not None and attach_location:
            try:
                self.outbreak_service.record_scan_observation(final, plant_entity.canonical_name)
            except Exception as exc:  # noqa: BLE001 - aggregation is secondary to the diagnosis
                logger.warning("Recording outbreak observation failed: %s", exc)

        # --- Follow-up scan of a tracked plant (ownership verified above) ---
        if tracked_plant_id is not None:
            self.recovery_service.link_scan(user_id, tracked_plant_id, saved_diagnosis.id, treatment_stage, None)
        return ScanResult(status="completed", diagnosis=final)

    def _run_segmentation(self, diagnosis_id, image: Image.Image) -> None:
        """Record what the segmentation model found — or why it couldn't run (no
        dataset, not trained, failed) — without ever failing the scan."""
        if self.segmentation_client is None or self.segmentation_repo is None:
            return
        try:
            card = self.segmentation_client.status()
            if not card.is_ready:
                row = DiagnosisSegmentationModel(diagnosis_id=diagnosis_id, status=card.readiness.value, message=card.message)
            else:
                from ai.segmentation.visualize import save_artifacts  # needs the AI packages; only reached with a ready model

                result, mapping = self.segmentation_client.call(lambda svc: (svc.segment(image), svc.mapping))
                key = f"segmentations/{uuid.uuid4().hex}"
                save_artifacts(result.mask, mapping, self.storage.resolve_path(key))
                row = DiagnosisSegmentationModel(
                    diagnosis_id=diagnosis_id, status="ok", model_name=result.model_name, model_version=result.model_version,
                    image_width=result.image_width, image_height=result.image_height, mask_width=result.mask_width,
                    mask_height=result.mask_height, affected_pixels=result.affected_pixels, plant_pixels=result.plant_pixels,
                    affected_area_pct=result.affected_area_pct, area_basis=result.area_basis,
                    area_unavailable_reason=result.area_unavailable_reason, class_pixels_json=result.class_pixels,
                    regions_json=result.regions, mean_confidence=result.mean_confidence,
                    mean_uncertainty=result.mean_uncertainty, inference_ms=result.inference_ms, artifact_dir=key,
                    classes_json=[{"id": c.id, "name": c.name, "kind": c.kind, "color": c.color} for c in mapping.classes])
        except ModelUnavailable as exc:
            row = DiagnosisSegmentationModel(diagnosis_id=diagnosis_id, status=exc.card.readiness.value, message=exc.card.message)
        except Exception as exc:  # noqa: BLE001 - localization is an add-on; classification already succeeded
            logger.warning("Segmentation failed for diagnosis %s: %s", diagnosis_id, exc)
            row = DiagnosisSegmentationModel(diagnosis_id=diagnosis_id, status="failed",
                                             message="Localization failed for this image; the diagnosis is unaffected.")
        try:
            self.segmentation_repo.save(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Saving segmentation result failed for diagnosis %s: %s", diagnosis_id, exc)

    def _run_gemini_analysis(self, image_bytes: bytes, image_format: Optional[str], diagnosis_output,
                              plant_entity, disease_entity, weather_snapshot):
        # Belt-and-suspenders: GeminiAnalysisService/GeminiClient already never
        # raise (every failure mode is caught internally and turned into a
        # status="unavailable" result), but this call is wrapped again here too
        # so that even an unforeseen bug in that layer can never take down the
        # rest of the scan pipeline (requirement #8: "Gemini is an enhancement,
        # not the single point of failure").
        try:
            mime_type = f"image/{(image_format or 'jpeg').lower()}"
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
            # Measured values only (missing ones say so). Gemini is told not to turn them
            # into spraying or disease-risk advice; AgriGuard does that from sources.
            weather_summary = measurements_text(weather_dict(weather_snapshot), "en")
            ctx = GeminiRequestContext(
                image_bytes=image_bytes, image_mime_type=mime_type,
                plant_name=plant_entity.canonical_name if plant_entity else None,
                cv_condition=disease_entity.name if disease_entity else diagnosis_output.condition,
                cv_confidence_score=diagnosis_output.confidence_score,
                cv_severity_level=diagnosis_output.severity_level,
                cv_affected_area_pct=diagnosis_output.affected_area_pct,
                disease_description=disease_entity.description if disease_entity else None,
                disease_symptoms=disease_entity.symptoms if disease_entity else [],
                weather_summary=weather_summary,
            )
            return self.gemini_service.analyze(ctx, self.plant_repo, self.disease_repo, self.treatment_repo)
        except Exception as exc:  # noqa: BLE001 - see comment above
            logger.warning("Gemini analysis step raised unexpectedly and was skipped: %s", exc)
            return None

    def _save_original_image(self, image: Image.Image, original_bytes: bytes) -> str:
        # Strip EXIF by re-encoding through a fresh Image object with no exif data
        # attached, which is the default behavior of Image.save() unless exif= is
        # explicitly passed (FR-SCAN-3).
        buf = io.BytesIO()
        rgb_image = image.convert("RGB")
        rgb_image.save(buf, format="JPEG", quality=92)
        key = generate_storage_key("scans", "jpg")
        return self.storage.save_bytes(buf.getvalue(), key)

    def _build_recommendation(self, diagnosis_output, weather_snapshot) -> Optional[Recommendation]:
        """The spraying-conditions summary from the shared, sourced weather guidance
        (app/application/reporting/weather_guidance.py), stored in English for API
        clients that read `recommendation.spraying_advice`. The diagnosis API recomputes
        the full guidance from the stored weather when read, in both languages.

        No irrigation or fertilizer advice is generated any more, and nothing for a
        healthy prediction: no verified source supported the earlier rules (rain >= 60 %
        -> "delay irrigation", humidity >= 85 % -> "favourable for fungal spread",
        otherwise "favourable for spraying" without checking wind, temperature >= 35 °C,
        severity -> fertilizer)."""
        if diagnosis_output.condition == HEALTHY_CONDITION:
            return None
        wx = weather_guidance(weather_dict(weather_snapshot), load_rules(), "en", Citations("en"))
        return Recommendation(id=None, diagnosis_id=None, irrigation_advice=None,
                              spraying_advice=wx["summary"], fertilizer_advice=None)

    def _generate_report(self, diagnosis, plant_entity, disease_entity, recommendation,
                          weather_snapshot, image_local_path: Path, heatmap_local_path: Path) -> str:
        treatments = self.treatment_repo.get_current_for_disease(disease_entity.id) if disease_entity else []
        organic = next((t.instructions for t in treatments if t.category.value == "organic"), None)
        chemical_treatment = next((t for t in treatments if t.category.value == "chemical"), None)
        chemical = None
        if chemical_treatment:
            if chemical_treatment.may_display_instructions():
                chemical = chemical_treatment.instructions
            else:
                chemical = ("Please consult your local agricultural authority for verified dosage "
                            "guidance for this treatment.")
        biological = next((t.instructions for t in treatments if t.category.value == "biological"), None)

        weather = weather_dict(weather_snapshot)
        weather_summary = measurements_text(weather, "en")
        spraying = None
        if not diagnosis.is_healthy():
            cites = Citations("en")
            spraying = weather_guidance(weather, load_rules(), "en", cites)
            spraying["references"] = cites.to_list()

        if disease_entity:
            disease_name, disease_description = disease_entity.name, disease_entity.description
        elif diagnosis.is_healthy():
            disease_name, disease_description = "Healthy / No disease detected", "No disease was detected in this scan."
        else:
            disease_name = diagnosis.predicted_condition_display_name()
            disease_description = UNLISTED_DISEASE_DESCRIPTION

        report_key = generate_storage_key("reports", "pdf")
        report_local_path = self.storage.resolve_path(report_key)
        report_local_path.parent.mkdir(parents=True, exist_ok=True)

        data = ReportData(
            diagnosis_id=str(diagnosis.id), plant_name=plant_entity.canonical_name,
            disease_name=disease_name, disease_description=disease_description,
            severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
            confidence_score=diagnosis.confidence_score, affected_area_pct=diagnosis.affected_area_pct,
            healthy_area_pct=diagnosis.healthy_area_pct, organic_treatment=organic, chemical_treatment=chemical,
            biological_treatment=biological,
            prevention_advice=list(GENERIC_PREVENTION_ADVICE),
            weather_summary=weather_summary, spraying_guidance=spraying,
            diagnosed_at=diagnosis.diagnosed_at or datetime.now(timezone.utc),
            original_image_path=str(image_local_path),
            heatmap_image_path=str(heatmap_local_path) if heatmap_local_path.exists() else None,
            report_verification_url=f"{settings.api_prefix}/reports/{diagnosis.id}",
        )
        self.pdf_generator.generate(data, str(report_local_path))
        return report_key
