"""
ScanOrchestrator — orchestrates the full Scan Plant use case (UC-03, FR-SCAN,
FR-AI, FR-TREAT, FR-WEATHER, FR-REPORT), matching the sequence diagram
`docs/02-system-design/07a-sequence-scan-plant.mermaid` step for step.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import InvalidImageError, ServiceUnavailableError
from app.domain.entities.diagnosis import Diagnosis, PestDetection, Recommendation, SeverityLevel, WeatherSnapshot
from app.domain.repositories.interfaces import IDiagnosisRepository, IPlantRepository, ITreatmentRepository, IDiseaseRepository
from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
from app.infrastructure.external.weather_client import WeatherService
from app.infrastructure.reporting.pdf_report_generator import PdfReportGenerator, ReportData
from app.infrastructure.storage.object_storage import IObjectStorage, generate_storage_key

logger = logging.getLogger("agriguard.scan_orchestrator")
settings = get_settings()


@dataclass
class ScanResult:
    status: str  # "completed" | "unrecognized_plant"
    diagnosis: Optional[Diagnosis] = None
    message: Optional[str] = None


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
    ):
        self.storage = storage
        self.ai_client = ai_client
        self.plant_repo = plant_repo
        self.disease_repo = disease_repo
        self.treatment_repo = treatment_repo
        self.diagnosis_repo = diagnosis_repo
        self.weather_service = weather_service
        self.pdf_generator = pdf_generator

    def process_scan(self, user_id: UUID, image_bytes: bytes, content_type: str,
                      latitude: Optional[float] = None, longitude: Optional[float] = None,
                      attach_location: bool = False) -> ScanResult:
        # --- FR-SCAN-2: validate the image is genuine and decodable ---
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.verify()
            image = Image.open(io.BytesIO(image_bytes))  # re-open after verify() invalidates handle
            image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise InvalidImageError("The uploaded file is not a valid, decodable image.")

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

        # --- Assemble and persist the Diagnosis aggregate (BR2: immutable) ---
        severity = SeverityLevel(diagnosis_output.severity_level) if diagnosis_output.severity_level else None
        diagnosis = Diagnosis(
            id=None, user_id=user_id, plant_id=plant_entity.id,
            disease_id=disease_entity.id if disease_entity else None,
            confidence_score=diagnosis_output.confidence_score, severity_level=severity,
            affected_area_pct=diagnosis_output.affected_area_pct, healthy_area_pct=diagnosis_output.healthy_area_pct,
            original_image_ref=original_ref, heatmap_image_ref=heatmap_ref,
            low_confidence_flag=diagnosis_output.low_confidence_flag, unrecognized_plant=False,
            location_lat=latitude if attach_location else None, location_lon=longitude if attach_location else None,
            weather_snapshot=weather_snapshot, recommendation=recommendation,
        )
        saved_diagnosis = self.diagnosis_repo.create(diagnosis)

        # --- Step 11: generate PDF report (BR5) and attach it to the persisted diagnosis ---
        report_key = self._generate_report(saved_diagnosis, plant_entity, disease_entity, recommendation,
                                            weather_snapshot, image_local_path, heatmap_local_path)
        self.diagnosis_repo.attach_report(saved_diagnosis.id, file_ref=report_key, qr_code_ref=report_key)

        final = self.diagnosis_repo.get_by_id(saved_diagnosis.id)
        return ScanResult(status="completed", diagnosis=final)

    def _save_original_image(self, image: Image.Image, original_bytes: bytes) -> str:
        # Strip EXIF by re-encoding through a fresh Image object with no exif data
        # attached, which is the default behavior of Image.save() unless exif= is
        # explicitly passed (FR-SCAN-3).
        buf = io.BytesIO()
        rgb_image = image.convert("RGB")
        rgb_image.save(buf, format="JPEG", quality=92)
        key = generate_storage_key("scans", "jpg")
        return self.storage.save_bytes(buf.getvalue(), key)

    def _build_recommendation(self, diagnosis_output, weather_snapshot) -> Recommendation:
        irrigation_advice = None
        spraying_advice = None
        fertilizer_advice = None

        if weather_snapshot is not None:
            if weather_snapshot.rain_probability_pct is not None and weather_snapshot.rain_probability_pct >= 60:
                spraying_advice = "Rain is likely in the next few hours — delay spraying to avoid wash-off."
                irrigation_advice = "Delay irrigation; expected rainfall may be sufficient."
            elif weather_snapshot.humidity_pct is not None and weather_snapshot.humidity_pct >= 85:
                spraying_advice = "High humidity detected — favorable conditions for fungal spread; consider treatment soon."
            else:
                spraying_advice = "Weather conditions are currently favorable for spraying."

            if weather_snapshot.temperature_c is not None and weather_snapshot.temperature_c >= 35:
                irrigation_advice = (irrigation_advice or "") + " High temperature — consider early morning or evening irrigation."

        if diagnosis_output.severity_level == "severe":
            fertilizer_advice = "Hold off on nitrogen-heavy fertilizer until the plant's health stabilizes."
        elif diagnosis_output.condition == "healthy":
            fertilizer_advice = "Maintain your regular fertilizing schedule."

        return Recommendation(
            id=None, diagnosis_id=None, irrigation_advice=irrigation_advice,
            spraying_advice=spraying_advice, fertilizer_advice=fertilizer_advice,
        )

    def _generate_report(self, diagnosis, plant_entity, disease_entity, recommendation,
                          weather_snapshot, image_local_path: Path, heatmap_local_path: Path) -> str:
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

        weather_summary = None
        if weather_snapshot:
            weather_summary = (
                f"Temperature: {weather_snapshot.temperature_c}°C, Humidity: {weather_snapshot.humidity_pct}%, "
                f"Wind: {weather_snapshot.wind_speed_kmh} km/h, Rain probability: "
                f"{weather_snapshot.rain_probability_pct}%, UV Index: {weather_snapshot.uv_index}"
            )

        report_key = generate_storage_key("reports", "pdf")
        report_local_path = self.storage.resolve_path(report_key)
        report_local_path.parent.mkdir(parents=True, exist_ok=True)

        data = ReportData(
            diagnosis_id=str(diagnosis.id), plant_name=plant_entity.canonical_name,
            disease_name=disease_entity.name if disease_entity else "Healthy / No disease detected",
            disease_description=disease_entity.description if disease_entity else "No disease was detected in this scan.",
            severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
            confidence_score=diagnosis.confidence_score, affected_area_pct=diagnosis.affected_area_pct,
            healthy_area_pct=diagnosis.healthy_area_pct, organic_treatment=organic, chemical_treatment=chemical,
            biological_treatment=biological,
            prevention_advice=["Ensure proper irrigation and ventilation.", "Remove and destroy infected leaves.",
                                "Practice crop rotation and field sanitation."],
            weather_summary=weather_summary, diagnosed_at=diagnosis.diagnosed_at or datetime.now(timezone.utc),
            original_image_path=str(image_local_path),
            heatmap_image_path=str(heatmap_local_path) if heatmap_local_path.exists() else None,
            report_verification_url=f"{settings.api_prefix}/reports/{diagnosis.id}",
        )
        self.pdf_generator.generate(data, str(report_local_path))
        return report_key
