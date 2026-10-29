"""
Scans & Diagnoses routes — FR-SCAN, FR-AI, FR-RESULT, FR-HIST (UC-03, UC-04, UC-06,
UC-07). See docs/02-system-design/13-api-specification.md §3.

Every diagnosis is a time-stamped, immutable observation. Its only post-creation
additions are append-only notes and the follow-up answers used by the differential
view; corrections are recorded as notes, never by editing the stored result.
Access: the owner, or an admin (read-only), for every endpoint below — checked
server-side for each id in the request.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.application.services.observation_comparison import compare_observations
from app.application.services.scan_service import ScanOrchestrator
from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, FileTooLargeError, NotFoundError, ValidationError
from app.domain.entities.tracking import ObservationNote
from app.domain.entities.user import User, UserRole
from app.infrastructure.external.ai_pipeline_client import AiPipelineClient
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.repositories.knowledge_base_repository import (
    SqlAlchemyDiseaseRepository,
    SqlAlchemyPlantRepository,
    SqlAlchemyTreatmentRepository,
)
from app.infrastructure.repositories.tracking_repository import (
    SqlAlchemyObservationNoteRepository,
    SqlAlchemyPlantProfileRepository,
)
from app.interface.api.v1.dependencies import (
    get_ai_client,
    get_current_user,
    get_diagnosis_repository,
    get_disease_repository,
    get_note_repository,
    get_plant_profile_repository,
    get_plant_repository,
    get_scan_orchestrator,
    get_treatment_repository,
)
from app.interface.api.v1.presenters import (
    diagnosis_to_response,
    diagnosis_to_summary,
    name_maps,
    note_to_schema,
)
from app.interface.schemas.diagnosis_schemas import (
    AssignPlantRequest,
    DiagnosisResponse,
    DifferentialSchema,
    FollowUpAnswersRequest,
    ImageQualitySchema,
    ObservationNoteCreateRequest,
    ObservationNoteSchema,
    PaginatedDiagnosesResponse,
    ScanRejectedResponse,
)

router = APIRouter(tags=["Scans & Diagnoses"])
settings = get_settings()

_DECISION_STATUSES = "^(confident|uncertain|inconclusive|legacy)$"


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Read at most `limit` bytes; abort as soon as the stream exceeds it instead of
    buffering an arbitrarily large upload in memory first."""
    chunks, total = [], 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise FileTooLargeError(f"Image exceeds the maximum allowed size of {limit // (1024 * 1024)}MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def get_accessible_diagnosis(diagnosis_id: UUID, user: User, repo: SqlAlchemyDiagnosisRepository):
    diagnosis = repo.get_by_id(diagnosis_id)
    if diagnosis is None:
        raise NotFoundError("Diagnosis not found.")
    if diagnosis.user_id != user.id and user.role != UserRole.ADMIN:
        raise AuthorizationError("You do not have access to this diagnosis.")
    return diagnosis


def _profile_for(diagnosis, profile_repo: SqlAlchemyPlantProfileRepository):
    if diagnosis.plant_profile_id is None:
        return None
    return profile_repo.get_owned(diagnosis.plant_profile_id, diagnosis.user_id)


@router.post("/scans", status_code=status.HTTP_201_CREATED)
async def create_scan(
    image: UploadFile = File(...),
    latitude: Optional[float] = Form(default=None, ge=-90, le=90),
    longitude: Optional[float] = Form(default=None, ge=-180, le=180),
    attach_location: bool = Form(default=False),
    plant_profile_id: Optional[UUID] = Form(default=None),
    new_plant_name: Optional[str] = Form(default=None, max_length=100),
    note: Optional[str] = Form(default=None, max_length=4000),
    current_user: User = Depends(get_current_user),
    orchestrator: ScanOrchestrator = Depends(get_scan_orchestrator),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
    ai_client: AiPipelineClient = Depends(get_ai_client),
):
    image_bytes = await _read_limited(image, settings.max_upload_size_bytes)

    # Image decoding, the quality gate, model inference and PDF rendering are CPU-bound
    # and synchronous; running them on the event loop would stall every other request.
    result = await run_in_threadpool(
        orchestrator.process_scan,
        user_id=current_user.id, image_bytes=image_bytes, content_type=image.content_type or "",
        latitude=latitude, longitude=longitude, attach_location=attach_location,
        plant_profile_id=plant_profile_id, new_plant_name=(new_plant_name or None), user_note=note,
    )

    if result.status == "rejected_image_quality":
        return ScanRejectedResponse(message=result.message or "The photo is not suitable for analysis.",
                                    quality=ImageQualitySchema(**result.quality))

    d = result.diagnosis
    return diagnosis_to_response(d, plant_repo, disease_repo, treatment_repo,
                                 plant_profile=_profile_for(d, profile_repo), model_info=ai_client.model_info())


@router.get("/model/info")
def model_info(current_user: User = Depends(get_current_user),
               ai_client: AiPipelineClient = Depends(get_ai_client)):
    """What the deployed model can and cannot recognize, and where its decision
    thresholds come from. Used by the UI to state limitations accurately."""
    from ai.knowledge.differential import FOLLOW_UP_QUESTIONS

    info = ai_client.model_info()
    info["follow_up_questions"] = FOLLOW_UP_QUESTIONS
    return info


@router.get("/diagnoses", response_model=PaginatedDiagnosesResponse)
def list_diagnoses(
    plant: Optional[str] = Query(default=None, max_length=100),
    disease: Optional[str] = Query(default=None, max_length=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    decision_status: Optional[str] = Query(default=None, pattern=_DECISION_STATUSES),
    plant_profile_id: Optional[UUID] = None,
    unassigned: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
):
    if date_from and date_to and date_from > date_to:
        raise ValidationError("date_from must be on or before date_to.")
    if plant_profile_id is not None and profile_repo.get_owned(plant_profile_id, current_user.id) is None:
        raise NotFoundError("Plant not found.")
    items, total = diagnosis_repo.list_for_user(
        current_user.id, plant, disease, date_from, date_to, page, page_size,
        decision_status=decision_status, plant_profile_id=plant_profile_id, unassigned_only=unassigned)
    plant_names, disease_names = name_maps(items, plant_repo, disease_repo)
    profile_names = {}
    for d in items:
        if d.plant_profile_id and d.plant_profile_id not in profile_names:
            p = profile_repo.get_owned(d.plant_profile_id, current_user.id)
            profile_names[d.plant_profile_id] = p.name if p else None
    return PaginatedDiagnosesResponse(
        items=[diagnosis_to_summary(d, plant_names, disease_names, profile_names) for d in items],
        page=page, page_size=page_size, total=total, total_pages=max(1, math.ceil(total / page_size)),
    )


# NOTE ON ROUTE ORDERING: a literal path like "/diagnoses/compare" MUST be registered
# before the parameterized "/diagnoses/{diagnosis_id}" route, otherwise "compare" would
# be captured as `diagnosis_id` and fail UUID parsing.
@router.get("/diagnoses/compare")
def compare_diagnoses(
    a: UUID, b: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
):
    if a == b:
        raise ValidationError("Choose two different observations to compare.")
    diag_a = diagnosis_repo.get_by_id(a)
    diag_b = diagnosis_repo.get_by_id(b)
    if diag_a is None or diag_b is None:
        raise NotFoundError("One or both diagnoses were not found.")
    for d in (diag_a, diag_b):
        if d.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise AuthorizationError("You do not have access to one or both diagnoses.")

    comparison = compare_observations(diag_a, diag_b, measurement_tolerance_pct_points=_measurement_tolerance())
    return {
        "a": diagnosis_to_response(diag_a, plant_repo, disease_repo, treatment_repo, _profile_for(diag_a, profile_repo)),
        "b": diagnosis_to_response(diag_b, plant_repo, disease_repo, treatment_repo, _profile_for(diag_b, profile_repo)),
        "comparison": comparison,
        # Kept for backward compatibility with older clients; see `comparison` for the
        # interpretation. A confidence difference is NOT a health change.
        "delta": {
            "confidence_change": round(diag_b.confidence_score - diag_a.confidence_score, 2),
            "severity_change": None,
        },
    }


def _measurement_tolerance() -> Optional[float]:
    """Validated affected-area error (MAE, percentage points) of the deployed
    segmentation model, if a held-out evaluation exists; otherwise None."""
    try:
        import json

        from ai.segmentation.service import resolve_latest_seg_run

        run = resolve_latest_seg_run()
        if run is None or not (run / "evaluation_test.json").exists():
            return None
        report = json.loads((run / "evaluation_test.json").read_text())
        return report.get("metrics", {}).get("affected_area_mae_pct_points")
    except Exception:  # noqa: BLE001
        return None


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisResponse)
def get_diagnosis(
    diagnosis_id: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
    ai_client: AiPipelineClient = Depends(get_ai_client),
):
    diagnosis = get_accessible_diagnosis(diagnosis_id, current_user, diagnosis_repo)
    return diagnosis_to_response(diagnosis, plant_repo, disease_repo, treatment_repo,
                                 plant_profile=_profile_for(diagnosis, profile_repo),
                                 model_info=ai_client.model_info())


@router.get("/diagnoses/{diagnosis_id}/notes", response_model=list[ObservationNoteSchema])
def list_notes(
    diagnosis_id: UUID,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    note_repo: SqlAlchemyObservationNoteRepository = Depends(get_note_repository),
):
    diagnosis = get_accessible_diagnosis(diagnosis_id, current_user, diagnosis_repo)
    return [note_to_schema(n, diagnosis.user_id) for n in note_repo.list_for_diagnosis(diagnosis.id)]


@router.post("/diagnoses/{diagnosis_id}/notes", response_model=ObservationNoteSchema,
             status_code=status.HTTP_201_CREATED)
def add_note(
    diagnosis_id: UUID,
    payload: ObservationNoteCreateRequest,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    note_repo: SqlAlchemyObservationNoteRepository = Depends(get_note_repository),
):
    diagnosis = get_accessible_diagnosis(diagnosis_id, current_user, diagnosis_repo)
    is_owner = diagnosis.user_id == current_user.id
    if payload.note_type == "expert_feedback":
        if current_user.role != UserRole.ADMIN:
            raise AuthorizationError("Only administrators can add expert feedback.")
    elif not is_owner:
        raise AuthorizationError("Only the owner of this observation can add notes.")
    note = note_repo.add(ObservationNote(id=None, diagnosis_id=diagnosis.id, author_user_id=current_user.id,
                                         note_type=payload.note_type, body=payload.body.strip()))
    return note_to_schema(note, diagnosis.user_id)


@router.post("/diagnoses/{diagnosis_id}/follow-up", response_model=DifferentialSchema)
def submit_follow_up(
    diagnosis_id: UUID,
    payload: FollowUpAnswersRequest,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    note_repo: SqlAlchemyObservationNoteRepository = Depends(get_note_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
):
    """Answers to the differential-diagnosis questions. They are stored as user-
    provided context (an append-only follow_up note) and turned into rule-of-thumb
    hints; they never change the model's probabilities."""
    from ai.knowledge.differential import build_differential, validate_answers

    diagnosis = get_accessible_diagnosis(diagnosis_id, current_user, diagnosis_repo)
    if diagnosis.user_id != current_user.id:
        raise AuthorizationError("Only the owner of this observation can answer follow-up questions.")
    if diagnosis.is_legacy:
        raise ValidationError("Follow-up questions are not available for observations from the earlier pipeline.")
    answers = validate_answers(payload.answers)
    if not answers:
        raise ValidationError("No valid answers were provided.")
    differential = build_differential(diagnosis.candidates, diagnosis.decision_status, answers)
    diagnosis_repo.update_differential(diagnosis.id, differential)
    note_repo.add(ObservationNote(id=None, diagnosis_id=diagnosis.id, author_user_id=current_user.id,
                                  note_type="follow_up", body="", data={"answers": answers}))
    updated = diagnosis_repo.get_by_id(diagnosis.id)
    return diagnosis_to_response(updated, plant_repo, disease_repo).differential


@router.put("/diagnoses/{diagnosis_id}/plant", response_model=DiagnosisResponse)
def assign_plant(
    diagnosis_id: UUID,
    payload: AssignPlantRequest,
    current_user: User = Depends(get_current_user),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
    note_repo: SqlAlchemyObservationNoteRepository = Depends(get_note_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
):
    """Link (or unlink) an observation to one of the caller's plants. The change is
    recorded as an append-only plant_link_change note."""
    diagnosis = get_accessible_diagnosis(diagnosis_id, current_user, diagnosis_repo)
    if diagnosis.user_id != current_user.id:
        raise AuthorizationError("Only the owner can change which plant an observation belongs to.")
    new_profile = None
    if payload.plant_profile_id:
        try:
            pid = UUID(payload.plant_profile_id)
        except ValueError:
            raise ValidationError("plant_profile_id must be a valid id.")
        new_profile = profile_repo.get_owned(pid, current_user.id)
        if new_profile is None or new_profile.archived_at is not None:
            raise NotFoundError("Plant not found.")
    old = diagnosis.plant_profile_id
    new = new_profile.id if new_profile else None
    if old != new:
        diagnosis_repo.set_plant_profile(diagnosis.id, new)
        note_repo.add(ObservationNote(
            id=None, diagnosis_id=diagnosis.id, author_user_id=current_user.id, note_type="plant_link_change",
            body="", data={"from": str(old) if old else None, "to": str(new) if new else None}))
    updated = diagnosis_repo.get_by_id(diagnosis.id)
    return diagnosis_to_response(updated, plant_repo, disease_repo, treatment_repo, plant_profile=new_profile)
