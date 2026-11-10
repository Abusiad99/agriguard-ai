"""
Scans & Diagnoses routes — FR-SCAN, FR-AI, FR-RESULT, FR-HIST (UC-03, UC-04, UC-06,
UC-07). See docs/02-system-design/13-api-specification.md §3.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.application.services.guidance import GENERIC_PREVENTION_ADVICE, GENERIC_PREVENTION_CODES
from app.application.services.scan_service import UNLISTED_DISEASE_DESCRIPTION, ScanOrchestrator
from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, FileTooLargeError, NotFoundError, ValidationError
from app.core.media_urls import signed_media_url
from app.domain.entities.user import User, UserRole
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.repositories.knowledge_base_repository import (
    SqlAlchemyDiseaseRepository,
    SqlAlchemyPlantRepository,
    SqlAlchemyTreatmentRepository,
)
from app.infrastructure.repositories.ai_features_repository import (
    SqlAlchemyRecoveryRepository,
    SqlAlchemySegmentationRepository,
)
from app.infrastructure.storage.object_storage import LocalObjectStorage
from app.interface.api.v1.dependencies import (
    get_current_user,
    get_diagnosis_repository,
    get_disease_repository,
    get_object_storage,
    get_plant_repository,
    get_recovery_repository,
    get_scan_orchestrator,
    get_segmentation_repository,
    get_treatment_repository,
)
from app.interface.schemas.ai_features_schemas import SegmentationSchema, TrackedPlantRefSchema
from app.interface.schemas.ai_analysis_schemas import AiAnalysisSchema, AiAnalysisStatus, AnalysisUrgency, CvConsistency, GeminiAnalysisSchema
from app.interface.schemas.diagnosis_schemas import (
    DiagnosisResponse,
    WeatherGuidanceSchema,
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


def _weather_guidance(diagnosis) -> dict:
    from app.application.reporting.recommendations import load_rules
    from app.application.reporting.weather_guidance import guidance_all_locales, weather_dict

    return guidance_all_locales(weather_dict(diagnosis.weather_snapshot), load_rules(), applicable=not diagnosis.is_healthy())


def _ai_analysis_to_schema(diagnosis) -> Optional[AiAnalysisSchema]:
    aa = diagnosis.ai_analysis
    if aa is None:
        return None  # Gemini was disabled for this scan — nothing to show, not an error state
    if aa.status != "ok":
        return AiAnalysisSchema(status=AiAnalysisStatus.UNAVAILABLE,
                                 message=aa.message or "AI analysis temporarily unavailable.")
    # Weather-based advice from the LLM is never shown (ai_text_guard.py); stored text is
    # kept unchanged, the filter runs on every read so older analyses are covered too.
    from app.application.services.ai_text_guard import strip_list, strip_weather_advice

    explanation, n1 = strip_weather_advice(aa.diagnosis_explanation or "")
    confidence, n2 = strip_weather_advice(aa.confidence_assessment or "")
    severity, n3 = strip_weather_advice(aa.severity_explanation or "")
    environmental, n4 = strip_weather_advice(aa.environmental_risk or "")
    treatment, n5 = strip_list(aa.treatment_guidance)
    prevention, n6 = strip_list(aa.prevention_guidance)
    return AiAnalysisSchema(
        status=AiAnalysisStatus.OK,
        weather_advice_removed=bool(n1 + n2 + n3 + n4 + n5 + n6),
        analysis=GeminiAnalysisSchema(
            diagnosis_explanation=explanation,
            observed_symptoms=aa.observed_symptoms,
            cv_consistency=CvConsistency(aa.cv_consistency) if aa.cv_consistency else CvConsistency.UNCERTAIN,
            confidence_assessment=confidence,
            severity_explanation=severity,
            treatment_guidance=treatment,
            prevention_guidance=prevention,
            environmental_risk=environmental,
            urgency=AnalysisUrgency(aa.urgency) if aa.urgency else AnalysisUrgency.LOW,
        ),
    )


SEGMENTATION_ARTIFACTS = ("mask", "overlay", "contours")


def _segmentation_to_schema(row, diagnosis_id) -> Optional[SegmentationSchema]:
    if row is None:
        return None
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    ok = row.status == "ok"
    return SegmentationSchema(
        status=row.status, message=row.message, model_name=row.model_name, model_version=row.model_version,
        image_width=row.image_width, image_height=row.image_height, mask_width=row.mask_width, mask_height=row.mask_height,
        affected_pixels=row.affected_pixels, plant_pixels=row.plant_pixels, affected_area_pct=f(row.affected_area_pct),
        area_basis=row.area_basis, area_unavailable_reason=row.area_unavailable_reason,
        mean_confidence=f(row.mean_confidence), mean_uncertainty=f(row.mean_uncertainty),
        classes=row.classes_json or [], regions=row.regions_json or [], created_at=row.created_at,
        artifacts={name: f"/api/v1/diagnoses/{diagnosis_id}/segmentation/{name}" for name in SEGMENTATION_ARTIFACTS}
        if ok and row.artifact_dir else None)


def _tracked_plant_ref(recovery_repo, diagnosis) -> Optional[TrackedPlantRefSchema]:
    link = recovery_repo.link_for_diagnosis(diagnosis.id)
    plant = recovery_repo.get_owned_plant(link.tracked_plant_id, diagnosis.user_id) if link else None
    return TrackedPlantRefSchema(id=str(plant.id), name=plant.name) if plant else None


def _diagnosis_to_response(
    diagnosis, settings,
    plant_repo: Optional[SqlAlchemyPlantRepository] = None,
    disease_repo: Optional[SqlAlchemyDiseaseRepository] = None,
    treatment_repo: Optional[SqlAlchemyTreatmentRepository] = None,
    segmentation_repo: Optional[SqlAlchemySegmentationRepository] = None,
    recovery_repo: Optional[SqlAlchemyRecoveryRepository] = None,
    viewer_id=None,
) -> DiagnosisResponse:
    plant_schema = None
    disease_schema = None
    treatment_schema = None
    prevention_advice = []
    prevention_codes = []

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
                    withheld = not t.may_display_instructions()
                    if withheld:
                        instructions = "Please consult your local agricultural authority for verified dosage guidance."
                    groups[t.category.value] = TreatmentGroupSchema(
                        instructions=instructions, instructions_withheld=withheld,
                        safety_notes=t.safety_notes, source_citation=t.source_citation,
                    )
                treatment_schema = TreatmentSchema(**groups)
            prevention_advice = list(GENERIC_PREVENTION_ADVICE)  # general practice, not disease-specific
            prevention_codes = list(GENERIC_PREVENTION_CODES)

    if disease_schema is None and not diagnosis.is_healthy():
        # The CV model found a disease the knowledge base has no record for. Report it
        # by its predicted name rather than as "healthy" (clients treat disease=null
        # as healthy); there is no verified treatment to attach.
        disease_schema = DiseaseSchema(
            name=diagnosis.predicted_condition_display_name() or "Unidentified condition",
            description=UNLISTED_DISEASE_DESCRIPTION,
            knowledge_base_status="not_listed",
        )

    weather_guidance = _weather_guidance(diagnosis)
    return DiagnosisResponse(
        diagnosis_id=str(diagnosis.id),
        status="completed",
        plant=plant_schema,
        disease=disease_schema,
        confidence_score=diagnosis.confidence_score,
        severity_level=diagnosis.severity_level.value if diagnosis.severity_level else None,
        affected_area_pct=diagnosis.affected_area_pct,
        healthy_area_pct=diagnosis.healthy_area_pct,
        heatmap_image_url=signed_media_url(diagnosis.heatmap_image_ref),
        roi_image_url=signed_media_url(diagnosis.original_image_ref),
        low_confidence_flag=diagnosis.low_confidence_flag,
        pests_detected=[
            PestSchema(name=p.pest_name, confidence=p.confidence, bbox=p.bbox) for p in diagnosis.pest_detections
        ],
        treatment=treatment_schema,
        recovery_probability=(disease.recovery_probability if disease_repo and diagnosis.disease_id and disease else None),
        estimated_recovery_time=(disease.estimated_recovery_time if disease_repo and diagnosis.disease_id and disease else None),
        prevention_advice=prevention_advice,
        prevention_advice_codes=prevention_codes,
        weather=(
            WeatherSchema(
                temperature_c=diagnosis.weather_snapshot.temperature_c,
                humidity_pct=diagnosis.weather_snapshot.humidity_pct,
                wind_speed_kmh=diagnosis.weather_snapshot.wind_speed_kmh,
                rain_probability_pct=diagnosis.weather_snapshot.rain_probability_pct,
                uv_index=diagnosis.weather_snapshot.uv_index,
            ) if diagnosis.weather_snapshot else None
        ),
        # Recomputed from the stored weather on every read (weather_guidance.py), so older
        # scans' unsourced advice texts are never shown. Field names are unchanged for
        # API clients; irrigation and fertilizer advice are no longer given (no source).
        recommendation=(RecommendationSchema(spraying_advice=weather_guidance["summary"]["en"])
                        if not diagnosis.is_healthy() else None),
        weather_guidance=WeatherGuidanceSchema(**weather_guidance),
        report_url=f"/api/v1/reports/{diagnosis.id}" if diagnosis.report else None,
        diagnosed_at=diagnosis.diagnosed_at,
        ai_analysis=_ai_analysis_to_schema(diagnosis),
        # A healthy prediction gets no heatmap (ai/inference/inference_service.py): its 0 % / 100 %
        # are the classifier's healthy result, not a heatmap estimate.
        severity_method=("explainability_heatmap"
                         if diagnosis.affected_area_pct is not None and not diagnosis.is_healthy() else None),
        segmentation=_segmentation_to_schema(segmentation_repo.get_for_diagnosis(diagnosis.id), diagnosis.id)
        if segmentation_repo else None,
        image_quality=diagnosis.image_quality,
        tracked_plant=_tracked_plant_ref(recovery_repo, diagnosis)
        if recovery_repo and (viewer_id is None or viewer_id == diagnosis.user_id) else None,
        viewer_is_owner=(viewer_id == diagnosis.user_id) if viewer_id is not None else None,
    )


# Deliberately a sync `def`: process_scan is blocking (model inference, Grad-CAM,
# weather/Gemini HTTP calls, PDF rendering), so FastAPI must run it in its threadpool
# rather than on the event loop, where it would stall every other request — including
# /health — on this worker for the whole scan.
@router.post("/scans", status_code=status.HTTP_201_CREATED)
def create_scan(
    image: UploadFile = File(...),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    attach_location: bool = Form(default=False),
    tracked_plant_id: Optional[UUID] = Form(default=None),
    treatment_stage: str = Form(default="unknown", pattern="^(before_treatment|during_treatment|after_treatment|unknown)$"),
    current_user: User = Depends(get_current_user),
    orchestrator: ScanOrchestrator = Depends(get_scan_orchestrator),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
    recovery_repo: SqlAlchemyRecoveryRepository = Depends(get_recovery_repository),
):
    if current_user.role != UserRole.FARMER:
        # Agronomists/admins may still test scans; only enforce the intended
        # persona restriction if explicitly required. Left permissive here since
        # FR-SCAN does not exclude other roles from scanning their own fields.
        pass

    # Read at most one byte past the limit: enough to detect an oversized upload
    # without pulling all of it into memory.
    image_bytes = image.file.read(settings.max_upload_size_bytes + 1)
    if len(image_bytes) > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            f"Image exceeds the maximum allowed size of {settings.max_upload_size_bytes // (1024*1024)}MB."
        )

    result = orchestrator.process_scan(
        user_id=current_user.id, image_bytes=image_bytes, content_type=image.content_type or "",
        latitude=latitude, longitude=longitude, attach_location=attach_location,
        tracked_plant_id=tracked_plant_id, treatment_stage=treatment_stage,
    )

    if result.status == "unrecognized_plant":
        return UnrecognizedPlantResponse(message=result.message)

    return _diagnosis_to_response(result.diagnosis, settings, plant_repo, disease_repo, treatment_repo,
                                  segmentation_repo, recovery_repo, viewer_id=current_user.id)


@router.get("/diagnoses", response_model=PaginatedDiagnosesResponse)
def list_diagnoses(
    plant: Optional[str] = None,
    disease: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1),
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
):
    page_size = min(page_size, 100)
    items, total = diagnosis_repo.list_for_user(current_user.id, plant, disease, date_from, date_to, page, page_size)

    # Summaries carry display names (the history cards show them as titles), not IDs.
    plant_names = {p.id: p.canonical_name for p in plant_repo.list()} if items else {}
    disease_names = {}
    for disease_id in {d.disease_id for d in items if d.disease_id}:
        kb_disease = disease_repo.get_by_id(disease_id)
        if kb_disease:
            disease_names[disease_id] = kb_disease.name

    summaries = [
        DiagnosisSummarySchema(
            id=str(d.id),
            plant=plant_names.get(d.plant_id),
            disease=(
                None if d.is_healthy()
                else disease_names.get(d.disease_id) or d.predicted_condition_display_name()
            ),
            severity_level=d.severity_level.value if d.severity_level else None,
            confidence_score=d.confidence_score,
            thumbnail_url=signed_media_url(d.original_image_ref),
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
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
    recovery_repo: SqlAlchemyRecoveryRepository = Depends(get_recovery_repository),
):
    diagnosis = diagnosis_repo.get_by_id(diagnosis_id)
    if diagnosis is None:
        raise NotFoundError("Diagnosis not found.")
    if diagnosis.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise AuthorizationError("You do not have access to this diagnosis.")
    return _diagnosis_to_response(diagnosis, settings, plant_repo, disease_repo, treatment_repo,
                                  segmentation_repo, recovery_repo, viewer_id=current_user.id)


@router.get("/diagnoses/{diagnosis_id}/segmentation/{artifact}")
def get_segmentation_artifact(
    diagnosis_id: UUID,
    artifact: str,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    segmentation_repo: SqlAlchemySegmentationRepository = Depends(get_segmentation_repository),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    """Segmentation mask / overlay / contour PNG. Same access rule as the diagnosis
    (owner or admin); these files are never under a public /storage mount."""
    from ai.segmentation import ARTIFACT_FILES

    if artifact not in ARTIFACT_FILES:
        raise NotFoundError("Unknown segmentation artifact.")
    diagnosis = diagnosis_repo.get_by_id(diagnosis_id)
    if diagnosis is None:
        raise NotFoundError("Diagnosis not found.")
    if diagnosis.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise AuthorizationError("You do not have access to this diagnosis.")
    row = segmentation_repo.get_for_diagnosis(diagnosis_id)
    if row is None or row.status != "ok" or not row.artifact_dir:
        raise NotFoundError("No segmentation result for this diagnosis.")
    path = storage.resolve_path(f"{row.artifact_dir}/{ARTIFACT_FILES[artifact]}")
    if not path.is_file():
        raise NotFoundError("The segmentation file could not be found.")
    return FileResponse(path=str(path), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
