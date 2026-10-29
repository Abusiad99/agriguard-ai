"""
Plant profiles & longitudinal health tracking.

Every endpoint resolves the plant through `get_owned(plant_id, current_user.id)`, so a
user can never read or modify another user's plant by guessing its id (the response
is 404, which also avoids confirming that the id exists). Admins can read any plant
through the diagnosis endpoints, not here.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.application.services.observation_comparison import compare_observations
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.entities.tracking import PlantProfile
from app.domain.entities.user import User
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
    get_current_user,
    get_diagnosis_repository,
    get_disease_repository,
    get_note_repository,
    get_plant_profile_repository,
    get_plant_repository,
    get_treatment_repository,
)
from app.interface.api.v1.presenters import (
    diagnosis_to_response,
    diagnosis_to_summary,
    name_maps,
    note_to_schema,
    profile_to_schema,
)
from app.interface.schemas.diagnosis_schemas import (
    MeasurementPointSchema,
    PaginatedPlantProfilesResponse,
    PlantProfileCreateRequest,
    PlantProfileSchema,
    PlantProfileUpdateRequest,
    PlantTimelineResponse,
    TimelineEntrySchema,
)

router = APIRouter(prefix="/plants", tags=["Plant Tracking"])

_STATUS_PATTERN = "^(confident|uncertain|inconclusive|legacy)$"


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _owned(plant_id: UUID, user: User, repo: SqlAlchemyPlantProfileRepository) -> PlantProfile:
    profile = repo.get_owned(plant_id, user.id)
    if profile is None:
        raise NotFoundError("Plant not found.")
    return profile


@router.post("", response_model=PlantProfileSchema, status_code=status.HTTP_201_CREATED)
def create_plant(payload: PlantProfileCreateRequest,
                 current_user: User = Depends(get_current_user),
                 repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository)):
    name = _clean(payload.name)
    if not name:
        raise ValidationError("Plant name is required.")
    profile = repo.create(PlantProfile(
        id=None, owner_user_id=current_user.id, name=name,
        crop_type=(_clean(payload.crop_type) or None) and _clean(payload.crop_type).lower(),
        variety=_clean(payload.variety), planting_date=payload.planting_date,
        location_label=_clean(payload.location_label), growing_environment=payload.growing_environment,
        notes=_clean(payload.notes),
    ))
    return profile_to_schema(profile)


@router.get("", response_model=PaginatedPlantProfilesResponse)
def list_plants(search: Optional[str] = Query(default=None, max_length=100),
                include_archived: bool = False,
                last_status: Optional[str] = Query(default=None, pattern=_STATUS_PATTERN),
                page: int = Query(default=1, ge=1),
                page_size: int = Query(default=20, ge=1, le=100),
                current_user: User = Depends(get_current_user),
                repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository)):
    items, total = repo.list_for_owner(current_user.id, search=search, include_archived=include_archived,
                                       last_status=last_status, page=page, page_size=page_size)
    return PaginatedPlantProfilesResponse(items=[profile_to_schema(p) for p in items], page=page,
                                          page_size=page_size, total=total,
                                          total_pages=max(1, math.ceil(total / page_size)))


@router.get("/{plant_id}", response_model=PlantProfileSchema)
def get_plant(plant_id: UUID, current_user: User = Depends(get_current_user),
              repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository)):
    return profile_to_schema(_owned(plant_id, current_user, repo))


@router.patch("/{plant_id}", response_model=PlantProfileSchema)
def update_plant(plant_id: UUID, payload: PlantProfileUpdateRequest,
                 current_user: User = Depends(get_current_user),
                 repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository)):
    _owned(plant_id, current_user, repo)
    changes = payload.model_dump(exclude_unset=True)
    archived = changes.pop("archived", None)
    for key in ("name", "crop_type", "variety", "location_label", "notes"):
        if key in changes:
            changes[key] = _clean(changes[key])
    if "name" in changes and not changes["name"]:
        raise ValidationError("Plant name cannot be empty.")
    if changes.get("crop_type"):
        changes["crop_type"] = changes["crop_type"].lower()
    profile = repo.update(plant_id, current_user.id, changes) if changes else _owned(plant_id, current_user, repo)
    if archived is not None:
        profile = repo.set_archived(plant_id, current_user.id, archived)
    return profile_to_schema(profile)


@router.delete("/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_plant(plant_id: UUID, current_user: User = Depends(get_current_user),
                  repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository)):
    """Archives the plant (soft delete). Its observations and images are preserved."""
    _owned(plant_id, current_user, repo)
    repo.set_archived(plant_id, current_user.id, True)


@router.get("/{plant_id}/timeline", response_model=PlantTimelineResponse)
def plant_timeline(
    plant_id: UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    decision_status: Optional[str] = Query(default=None, pattern=_STATUS_PATTERN),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    note_repo: SqlAlchemyObservationNoteRepository = Depends(get_note_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
):
    """Chronological observations (oldest first) with their notes, plus a measurement
    series containing ONLY genuine segmentation measurements. Observations without a
    comparable measurement are counted, not plotted, so the chart never mixes
    estimates with measurements."""
    profile = _owned(plant_id, current_user, profile_repo)
    if date_from and date_to and date_from > date_to:
        raise ValidationError("date_from must be on or before date_to.")
    items, total = diagnosis_repo.list_for_plant_profile(profile.id, date_from, date_to, decision_status,
                                                         page=page, page_size=page_size, ascending=True)
    notes = note_repo.list_for_diagnoses([d.id for d in items])
    plant_names, disease_names = name_maps(items, plant_repo, disease_repo)
    profile_names = {profile.id: profile.name}

    entries = []
    series = []
    without = 0
    for d in items:
        d_notes = notes.get(d.id, [])
        treatments = [n.body for n in d_notes if n.note_type == "treatment_applied" and n.body]
        entries.append(TimelineEntrySchema(
            observation=diagnosis_to_summary(d, plant_names, disease_names, profile_names),
            notes=[note_to_schema(n, profile.owner_user_id) for n in d_notes],
            treatment_summary="; ".join(treatments)[:500] if treatments else None,
        ))
        if d.has_segmentation_measurement and d.diagnosed_at:
            series.append(MeasurementPointSchema(
                diagnosis_id=str(d.id), diagnosed_at=d.diagnosed_at, affected_area_pct=d.affected_area_pct,
                method=d.severity_method, model_version=(d.segmentation or {}).get("model_version"),
                image_quality_status=(d.image_quality or {}).get("status")))
        else:
            without += 1

    methods = {(p.method, p.model_version) for p in series}
    note = None
    if not series:
        note = "no_segmentation_measurements"
    elif len(methods) > 1:
        note = "mixed_measurement_methods"
    return PlantTimelineResponse(
        plant=profile_to_schema(profile), entries=entries, page=page, page_size=page_size, total=total,
        total_pages=max(1, math.ceil(total / page_size)), measurement_series=series,
        measurement_series_note=note, observations_without_measurement=without,
    )


@router.get("/{plant_id}/compare")
def compare_plant_observations(
    plant_id: UUID, a: UUID, b: UUID,
    current_user: User = Depends(get_current_user),
    profile_repo: SqlAlchemyPlantProfileRepository = Depends(get_plant_profile_repository),
    diagnosis_repo: SqlAlchemyDiagnosisRepository = Depends(get_diagnosis_repository),
    plant_repo: SqlAlchemyPlantRepository = Depends(get_plant_repository),
    disease_repo: SqlAlchemyDiseaseRepository = Depends(get_disease_repository),
    treatment_repo: SqlAlchemyTreatmentRepository = Depends(get_treatment_repository),
):
    from app.interface.api.v1.scans_router import _measurement_tolerance

    profile = _owned(plant_id, current_user, profile_repo)
    if a == b:
        raise ValidationError("Choose two different observations to compare.")
    obs = []
    for oid in (a, b):
        d = diagnosis_repo.get_by_id(oid)
        if d is None or d.user_id != current_user.id or d.plant_profile_id != profile.id:
            raise NotFoundError("Observation not found for this plant.")
        obs.append(d)
    comparison = compare_observations(obs[0], obs[1], measurement_tolerance_pct_points=_measurement_tolerance())
    return {
        "a": diagnosis_to_response(obs[0], plant_repo, disease_repo, treatment_repo, plant_profile=profile),
        "b": diagnosis_to_response(obs[1], plant_repo, disease_repo, treatment_repo, plant_profile=profile),
        "comparison": comparison,
    }
