"""
Scans & Diagnoses routes — FR-SCAN, FR-AI, FR-RESULT, FR-HIST (UC-03, UC-04, UC-06,
UC-07). See docs/02-system-design/13-api-specification.md §3.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.application.services.scan_service import ScanOrchestrator
from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, FileTooLargeError, NotFoundError, ValidationError
from app.domain.entities.user import User, UserRole
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.repositories.knowledge_base_repository import (
    SqlAlchemyDiseaseRepository,
    SqlAlchemyPlantRepository,
    SqlAlchemyTreatmentRepository,
)
from app.interface.api.v1.dependencies import (
    get_current_user,
    get_diagnosis_repository,
    get_disease_repository,
    get_plant_repository,
    get_scan_orchestrator,
    get_treatment_repository,
)
from app.interface.schemas.ai_analysis_schemas import AiAnalysisSchema, AiAnalysisStatus, AnalysisUrgency, CvConsistency, GeminiAnalysisSchema
from app.interface.schemas.diagnosis_schemas import (
    DiagnosisResponse,
    DiagnosisSummarySchema,
    DiseaseSchema,
    PaginatedDiagnosesResponse,
    PestSchema,
    PlantSchema,
    RecommendationSchema,
    TreatmentGroupSchema,
    TreatmentSchema,
    UnrecognizedPlantResponse,
    WeatherSchema,
)

router = APIRouter(tags=["Scans & Diagnoses"])
settings = get_settings()


def _ai_analysis_to_schema(diagnosis) -> Optional[AiAnalysisSchema]:
    aa = diagnosis.ai_analysis
    if aa is None:
        return None  # Gemini was disabled for this scan — nothing to show, not an error state
    if aa.status != "ok":
        return AiAnalysisSchema(status=AiAnalysisStatus.UNAVAILABLE,
                                 message=aa.message or "AI analysis temporarily unavailable.")
    return AiAnalysisSchema(
        status=AiAnalysisStatus.OK,
        analysis=GeminiAnalysisSchema(
            diagnosis_explanation=aa.diagnosis_explanation or "",
            observed_symptoms=aa.observed_symptoms,
            cv_consistency=CvConsistency(aa.cv_consistency) if aa.cv_consistency else CvConsistency.UNCERTAIN,
            confidence_assessment=aa.confidence_assessment or "",
            severity_explanation=aa.severity_explanation or "",
            treatment_guidance=aa.treatment_guidance,
            prevention_guidance=aa.prevention_guidance,
            environmental_risk=aa.environmental_risk or "",
            urgency=AnalysisUrgency(aa.urgency) if aa.urgency else AnalysisUrgency.LOW,
        ),
    )


def _diagnosis_to_response(
    diagnosis, settings,
    plant_repo: Optional[SqlAlchemyPlantRepository] = None,
    disease_repo: Optional[SqlAlchemyDiseaseRepository] = None,
    treatment_repo: Optional[SqlAlchemyTreatmentRepository] = None,
) -> DiagnosisResponse:
    plant_schema = None
    disease_schema = None
    treatment_schema = None
    prevention_advice = []

    if plant_repo and diagnosis.plant_id:
        for p in plant_repo.list():
            if p.id == diagnosis.plant_id:
                plant_schema = PlantSchema(name=p.canonical_name, scientific_name=p.scientific_name)
                break

    if disease_repo and diagnosis.disease_id:
        disease = disease_repo.get_by_id(diagnosis.disease_id)
        if disease:
            disease_schema = DiseaseSchema(
                name=disease.name, type=disease.disease_type, description=disease.description,
                symptoms=disease.symptoms, causes=disease.causes, transmission_method=disease.transmission_method,
            )
            if treatment_repo:
                treatments = treatment_repo.get_current_for_disease(disease.id)
                groups = {"organic": None, "chemical": None, "biological": None}
                for t in treatments:
                    instructions = t.instructions
                    if t.category.value == "chemical" and not t.is_dosage_verified():
                        instructions = "Please consult your local agricultural authority for verified dosage guidance."
                    groups[t.category.value] = TreatmentGroupSchema(
                        instructions=instructions, safety_notes=t.safety_notes, source_citation=t.source_citation,
                    )
                treatment_schema = TreatmentSchema(**groups)
            prevention_advice = [
                "Ensure proper irrigation and ventilation.",
                "Remove and destroy infected plant material.",
                "Practice crop rotation and field sanitation.",
            ]

    return DiagnosisResponse(
        diagnosis_id=str(diagnosis.id),
        status="completed",
        plant=plant_schema,
        disease=disease_schema,
        confidence_score=diagnosis.confidence_score,
        severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
        affected_area_pct=diagnosis.affected_area_pct,
        healthy_area_pct=diagnosis.healthy_area_pct,
        heatmap_image_url=f"/storage/{diagnosis.heatmap_image_ref}" if diagnosis.heatmap_image_ref else None,
        roi_image_url=f"/storage/{diagnosis.original_image_ref}" if diagnosis.original_image_ref else None,
        low_confidence_flag=diagnosis.low_confidence_flag,
        pests_detected=[
            PestSchema(name=p.pest_name, confidence=p.confidence, bbox=p.bbox) for p in diagnosis.pest_detections
        ],
        treatment=treatment_schema,
        recovery_probability=(disease.recovery_probability if disease_repo and diagnosis.disease_id and disease else None),
        estimated_recovery_time=(disease.estimated_recovery_time if disease_repo and diagnosis.disease_id and disease else None),
        prevention_advice=prevention_advice,
        weather=(
            WeatherSchema(
                temperature_c=diagnosis.weather_snapshot.temperature_c,
                humidity_pct=diagnosis.weather_snapshot.humidity_pct,
                wind_speed_kmh=diagnosis.weather_snapshot.wind_speed_kmh,
                rain_probability_pct=diagnosis.weather_snapshot.rain_probability_pct,
                uv_index=diagnosis.weather_snapshot.uv_index,
            ) if diagnosis.weather_snapshot else None
        ),
        recommendation=(
            RecommendationSchema(
                irrigation_advice=diagnosis.recommendation.irrigation_advice,
                spraying_advice=diagnosis.recommendation.spraying_advice,
                fertilizer_advice=diagnosis.recommendation.fertilizer_advice,
            ) if diagnosis.recommendation else None
        ),
        report_url=f"/api/v1/reports/{diagnosis.id}" if diagnosis.report else None,
        diagnosed_at=diagnosis.diagnosed_at,
        ai_analysis=_ai_analysis_to_schema(diagnosis),
    )


@router.post("/scans", status_code=status.HTTP_201_CREATED)
async def create_scan(
    image: UploadFile = File(...),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    attach_location: bool = Form(default=False),
    current_user: User = Depends(get_current_user),
    orchestrator: ScanOrchestrator = Depends(get_scan_orchestrator),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
):
    if current_user.role != UserRole.FARMER:
        # Agronomists/admins may still test scans; only enforce the intended
        # persona restriction if explicitly required. Left permissive here since
        # FR-SCAN does not exclude other roles from scanning their own fields.
        pass

    image_bytes = await image.read()
    if len(image_bytes) > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            f"Image exceeds the maximum allowed size of {settings.max_upload_size_bytes // (1024*1024)}MB."
        )

    result = orchestrator.process_scan(
        user_id=current_user.id, image_bytes=image_bytes, content_type=image.content_type or "",
        latitude=latitude, longitude=longitude, attach_location=attach_location,
    )

    if result.status == "unrecognized_plant":
        return UnrecognizedPlantResponse(message=result.message)

    return _diagnosis_to_response(result.diagnosis, settings, plant_repo, disease_repo, treatment_repo)


@router.get("/diagnoses", response_model=PaginatedDiagnosesResponse)
def list_diagnoses(
    plant: Optional[str] = None,
    disease: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
):
    page_size = min(page_size, 100)
    items, total = diagnosis_repo.list_for_user(current_user.id, plant, disease, date_from, date_to, page, page_size)
    summaries = [
        DiagnosisSummarySchema(
            id=str(d.id),
            plant=d.plant_id and str(d.plant_id),
            disease=d.disease_id and str(d.disease_id),
            severity_level=d.severity_level.value if d.severity_level else None,
            confidence_score=d.confidence_score,
            thumbnail_url=f"/storage/{d.original_image_ref}" if d.original_image_ref else None,
            diagnosed_at=d.diagnosed_at,
        )
        for d in items
    ]
    return PaginatedDiagnosesResponse(
        items=summaries, page=page, page_size=page_size, total=total,
        total_pages=max(1, math.ceil(total / page_size)),
    )


# NOTE ON ROUTE ORDERING: FastAPI/Starlette matches routes in registration order, so
# a literal path segment like "/diagnoses/compare" MUST be registered before the
# parameterized "/diagnoses/{diagnosis_id}" route below it — otherwise "compare"
# would be captured as `diagnosis_id` and fail UUID parsing (returning a confusing
# 422 instead of ever reaching the compare handler). This ordering is deliberate and
# covered by tests/integration/test_scan_api.py's history/compare tests.
@router.get("/diagnoses/compare")
def compare_diagnoses(
    a: UUID, b: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
):
    diag_a = diagnosis_repo.get_by_id(a)
    diag_b = diagnosis_repo.get_by_id(b)
    if diag_a is None or diag_b is None:
        raise NotFoundError("One or both diagnoses were not found.")
    for d in (diag_a, diag_b):
        if d.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise AuthorizationError("You do not have access to one or both diagnoses.")

    severity_order = {"mild": 1, "moderate": 2, "severe": 3}
    sev_a = severity_order.get(diag_a.severity_level.value if diag_a.severity_level else "", None)
    sev_b = severity_order.get(diag_b.severity_level.value if diag_b.severity_level else "", None)
    severity_change = None
    if sev_a is not None and sev_b is not None:
        severity_change = f"{diag_a.severity_level.value}_to_{diag_b.severity_level.value}" if sev_a != sev_b else "unchanged"

    return {
        "a": _diagnosis_to_response(diag_a, settings, plant_repo, disease_repo, treatment_repo),
        "b": _diagnosis_to_response(diag_b, settings, plant_repo, disease_repo, treatment_repo),
        "delta": {
            "confidence_change": round(diag_b.confidence_score - diag_a.confidence_score, 2),
            "severity_change": severity_change,
        },
    }


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisResponse)
def get_diagnosis(
    diagnosis_id: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
):
    diagnosis = diagnosis_repo.get_by_id(diagnosis_id)
    if diagnosis is None:
        raise NotFoundError("Diagnosis not found.")
    if diagnosis.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise AuthorizationError("You do not have access to this diagnosis.")
    return _diagnosis_to_response(diagnosis, settings, plant_repo, disease_repo, treatment_repo)
