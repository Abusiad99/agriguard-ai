"""Plant recovery monitoring routes (docs/features/plant-recovery-monitoring.md).

Every route is scoped to the authenticated owner through RecoveryService.require_plant:
another user's plant (or a missing one) is 404, so ids can't be probed.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.services.recovery_service import RecoveryService, compare_scans, reminder_state
from app.core.exceptions import NotFoundError, ValidationError
from app.core.media_urls import signed_media_url
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_current_user, get_recovery_repository, get_recovery_service
from app.interface.schemas.ai_features_schemas import (
    AssessmentSchema,
    CompareResponse,
    PaginatedReminders,
    PaginatedTimeline,
    PaginatedTrackedPlants,
    PlantScanSchema,
    ReminderCreate,
    ReminderSchema,
    ReminderUpdate,
    ScanLinkCreate,
    TimelineEventSchema,
    TrackedPlantCreate,
    TrackedPlantDetailSchema,
    TrackedPlantSchema,
    TrackedPlantUpdate,
    TreatmentCreate,
    TreatmentRecordSchema,
)

router = APIRouter(prefix="/tracked-plants", tags=["Plant Recovery"])


def _uuid(value: Optional[str], what: str) -> Optional[UUID]:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise ValidationError(f"{what} is not a valid id.")


def _f(value):
    return float(value) if value is not None else None


def plant_schema(p, summary: Optional[dict] = None) -> TrackedPlantSchema:
    summary = summary or {}
    return TrackedPlantSchema(
        id=str(p.id), name=p.name, crop=p.crop, species=p.species, notes=p.notes, status=p.status,
        latitude=_f(p.location_lat), longitude=_f(p.location_lon),
        initial_diagnosis_id=str(p.initial_diagnosis_id) if p.initial_diagnosis_id else None,
        created_at=p.created_at, updated_at=p.updated_at, **summary)


def scan_schema(item: dict) -> PlantScanSchema:
    link, d, seg = item["link"], item["diagnosis"], item["segmentation"]
    return PlantScanSchema(
        diagnosis_id=str(d.id), diagnosed_at=d.diagnosed_at, treatment_stage=link.treatment_stage, notes=link.notes,
        predicted_condition=d.predicted_condition,
        is_healthy=(d.predicted_condition == "healthy") if d.predicted_condition else None,
        confidence_score=_f(d.confidence_score), low_confidence_flag=d.low_confidence_flag,
        image_url=signed_media_url(d.original_image_ref),
        image_quality=d.image_quality_json, segmentation_status=seg.status if seg else None,
        affected_area_pct=_f(seg.affected_area_pct) if seg and seg.status == "ok" else None,
        segmentation_model=f"{seg.model_name}@{seg.model_version}" if seg and seg.status == "ok" else None)


def assessment_schema(a) -> AssessmentSchema:
    return AssessmentSchema(
        id=str(a.id), status=a.status, method_version=a.method_version,
        baseline_diagnosis_id=str(a.baseline_diagnosis_id) if a.baseline_diagnosis_id else None,
        latest_diagnosis_id=str(a.latest_diagnosis_id) if a.latest_diagnosis_id else None,
        indicators=a.indicators_json or [], limitations=a.limitations_json or [],
        area_series=a.area_series_json or [], summary=a.summary, created_at=a.created_at)


def treatment_schema(t) -> TreatmentRecordSchema:
    return TreatmentRecordSchema(id=str(t.id), name=t.name, category=t.category, applied_on=t.applied_on,
                                 application_notes=t.application_notes, dosage_text=t.dosage_text,
                                 documentation_ref=t.documentation_ref, follow_up_on=t.follow_up_on,
                                 user_notes=t.user_notes, created_at=t.created_at)


def reminder_schema(r, plant_name: Optional[str] = None) -> ReminderSchema:
    return ReminderSchema(id=str(r.id), tracked_plant_id=str(r.tracked_plant_id), plant_name=plant_name, kind=r.kind,
                          due_on=r.due_on, status=r.status, state=reminder_state(r), note=r.note,
                          treatment_record_id=str(r.treatment_record_id) if r.treatment_record_id else None,
                          completed_at=r.completed_at)


@router.get("", response_model=PaginatedTrackedPlants)
def list_plants(status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(active|archived)$"),
                page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                current_user: User = Depends(get_current_user), service: RecoveryService = Depends(get_recovery_service)):
    plants, total, summaries = service.list_plants(current_user.id, status_filter, page, page_size)
    return PaginatedTrackedPlants(items=[plant_schema(p, summaries.get(p.id)) for p in plants],
                                  page=page, page_size=page_size, total=total)


@router.post("", response_model=TrackedPlantSchema, status_code=status.HTTP_201_CREATED)
def create_plant(body: TrackedPlantCreate, current_user: User = Depends(get_current_user),
                 service: RecoveryService = Depends(get_recovery_service)):
    location = (body.latitude, body.longitude) if body.latitude is not None else None
    plant = service.create_plant(current_user.id, body.name, body.crop, body.species, body.notes, location,
                                 _uuid(body.initial_diagnosis_id, "initial_diagnosis_id"))
    return plant_schema(plant, service.repo.plant_summaries([plant.id])[plant.id])


# Literal paths before "/{plant_id}" (route order matters, see scans_router).
@router.get("/reminders", response_model=PaginatedReminders)
def my_reminders(state: str = Query(default="open", pattern="^(open|overdue|completed|all)$"),
                 page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                 current_user: User = Depends(get_current_user), repo=Depends(get_recovery_repository)):
    statuses = {"open": ["pending"], "overdue": ["pending"], "completed": ["completed"],
                "all": ["pending", "completed", "dismissed"]}[state]
    due_before = date.today() - timedelta(days=1) if state == "overdue" else None
    rows, total = repo.owner_reminders(current_user.id, statuses, due_before, page, page_size)
    return PaginatedReminders(items=[reminder_schema(r, p.name) for r, p in rows], page=page, page_size=page_size, total=total)


@router.get("/{plant_id}", response_model=TrackedPlantDetailSchema)
def get_plant(plant_id: UUID, current_user: User = Depends(get_current_user),
              service: RecoveryService = Depends(get_recovery_service)):
    plant = service.require_plant(current_user.id, plant_id)
    scans = service.scans(current_user.id, plant_id)
    return TrackedPlantDetailSchema(
        plant=plant_schema(plant, service.repo.plant_summaries([plant.id])[plant.id]),
        scans=[scan_schema(s) for s in scans],
        assessment=assessment_schema(service.latest_assessment(current_user.id, plant_id)),
        treatments=[treatment_schema(t) for t in service.repo.list_treatments(plant_id)],
        reminders=[reminder_schema(r, plant.name) for r in service.repo.list_reminders(plant_id)])


@router.patch("/{plant_id}", response_model=TrackedPlantSchema)
def update_plant(plant_id: UUID, body: TrackedPlantUpdate, current_user: User = Depends(get_current_user),
                 service: RecoveryService = Depends(get_recovery_service)):
    changes = body.model_dump(exclude_unset=True, exclude={"latitude", "longitude", "clear_location"})
    if body.clear_location:
        changes["location"] = None
    elif body.latitude is not None:
        changes["location"] = (body.latitude, body.longitude)
    plant = service.update_plant(current_user.id, plant_id, changes)
    return plant_schema(plant, service.repo.plant_summaries([plant.id])[plant.id])


@router.post("/{plant_id}/scans", response_model=PlantScanSchema, status_code=status.HTTP_201_CREATED)
def link_scan(plant_id: UUID, body: ScanLinkCreate, current_user: User = Depends(get_current_user),
              service: RecoveryService = Depends(get_recovery_service)):
    diagnosis_id = _uuid(body.diagnosis_id, "diagnosis_id")
    service.link_scan(current_user.id, plant_id, diagnosis_id, body.treatment_stage, body.notes)
    return next(scan_schema(s) for s in service.scans(current_user.id, plant_id) if s["diagnosis"].id == diagnosis_id)


@router.delete("/{plant_id}/scans/{diagnosis_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_scan(plant_id: UUID, diagnosis_id: UUID, current_user: User = Depends(get_current_user),
                service: RecoveryService = Depends(get_recovery_service)):
    service.unlink_scan(current_user.id, plant_id, diagnosis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{plant_id}/compare", response_model=CompareResponse)
def compare(plant_id: UUID, first: Optional[UUID] = None, second: Optional[UUID] = None,
            current_user: User = Depends(get_current_user), service: RecoveryService = Depends(get_recovery_service)):
    scans = service.scans(current_user.id, plant_id)
    if len(scans) < 2:
        raise ValidationError("At least two scans are needed to compare.")
    by_id = {s["diagnosis"].id: s for s in scans}
    a = by_id.get(first) if first else scans[0]
    b = by_id.get(second) if second else scans[-1]
    if a is None or b is None:
        raise NotFoundError("Both scans must belong to this plant.")
    if a is b:
        raise ValidationError("Choose two different scans.")
    if a["diagnosis"].diagnosed_at > b["diagnosis"].diagnosed_at:
        a, b = b, a
    result = compare_scans(a, b)
    return CompareResponse(first=scan_schema(a), second=scan_schema(b), **result)


@router.get("/{plant_id}/assessment", response_model=AssessmentSchema)
def get_assessment(plant_id: UUID, current_user: User = Depends(get_current_user),
                   service: RecoveryService = Depends(get_recovery_service)):
    return assessment_schema(service.latest_assessment(current_user.id, plant_id))


@router.post("/{plant_id}/assessment", response_model=AssessmentSchema)
def recompute_assessment(plant_id: UUID, current_user: User = Depends(get_current_user),
                         service: RecoveryService = Depends(get_recovery_service)):
    return assessment_schema(service.reassess(current_user.id, plant_id))


@router.get("/{plant_id}/timeline", response_model=PaginatedTimeline)
def timeline(plant_id: UUID, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
             current_user: User = Depends(get_current_user), service: RecoveryService = Depends(get_recovery_service)):
    service.require_plant(current_user.id, plant_id)
    rows, total = service.repo.list_events(plant_id, page, page_size)
    return PaginatedTimeline(items=[TimelineEventSchema(
        id=str(e.id), event_type=e.event_type, occurred_at=e.occurred_at, details=e.details_json,
        diagnosis_id=str(e.diagnosis_id) if e.diagnosis_id else None,
        treatment_record_id=str(e.treatment_record_id) if e.treatment_record_id else None,
        reminder_id=str(e.reminder_id) if e.reminder_id else None,
        assessment_id=str(e.assessment_id) if e.assessment_id else None) for e in rows],
        page=page, page_size=page_size, total=total)


@router.get("/{plant_id}/treatments", response_model=list[TreatmentRecordSchema])
def list_treatments(plant_id: UUID, current_user: User = Depends(get_current_user),
                    service: RecoveryService = Depends(get_recovery_service)):
    service.require_plant(current_user.id, plant_id)
    return [treatment_schema(t) for t in service.repo.list_treatments(plant_id)]


@router.post("/{plant_id}/treatments", response_model=TreatmentRecordSchema, status_code=status.HTTP_201_CREATED)
def add_treatment(plant_id: UUID, body: TreatmentCreate, current_user: User = Depends(get_current_user),
                  service: RecoveryService = Depends(get_recovery_service)):
    return treatment_schema(service.add_treatment(current_user.id, plant_id, body.model_dump()))


@router.delete("/{plant_id}/treatments/{treatment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_treatment(plant_id: UUID, treatment_id: UUID, current_user: User = Depends(get_current_user),
                     service: RecoveryService = Depends(get_recovery_service)):
    service.delete_treatment(current_user.id, plant_id, treatment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{plant_id}/reminders", response_model=list[ReminderSchema])
def list_reminders(plant_id: UUID, current_user: User = Depends(get_current_user),
                   service: RecoveryService = Depends(get_recovery_service)):
    plant = service.require_plant(current_user.id, plant_id)
    return [reminder_schema(r, plant.name) for r in service.repo.list_reminders(plant_id)]


@router.post("/{plant_id}/reminders", response_model=ReminderSchema, status_code=status.HTTP_201_CREATED)
def add_reminder(plant_id: UUID, body: ReminderCreate, current_user: User = Depends(get_current_user),
                 service: RecoveryService = Depends(get_recovery_service)):
    row = service.add_reminder(current_user.id, plant_id, body.kind, body.due_on, body.note,
                               _uuid(body.treatment_record_id, "treatment_record_id"))
    return reminder_schema(row)


@router.patch("/{plant_id}/reminders/{reminder_id}", response_model=ReminderSchema)
def update_reminder(plant_id: UUID, reminder_id: UUID, body: ReminderUpdate, current_user: User = Depends(get_current_user),
                    service: RecoveryService = Depends(get_recovery_service)):
    return reminder_schema(service.set_reminder_status(current_user.id, plant_id, reminder_id, body.status))
