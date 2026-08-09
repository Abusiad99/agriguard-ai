"""Diseases routes — FR-RESULT (browse), FR-ADMIN-2 (UC-09). See API spec §6."""
from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.services.knowledge_base_service import KnowledgeBaseService
from app.domain.entities.user import User, UserRole
from app.interface.api.v1.dependencies import get_current_user, get_knowledge_base_service, require_roles
from app.interface.schemas.common_schemas import DiseaseCreateRequest, DiseaseResponseSchema

router = APIRouter(prefix="/diseases", tags=["Knowledge Base — Diseases"])


def _to_schema(disease) -> DiseaseResponseSchema:
    return DiseaseResponseSchema(
        id=str(disease.id), plant_id=str(disease.plant_id), name=disease.name,
        disease_type=disease.disease_type, description=disease.description,
        symptoms=disease.symptoms, causes=disease.causes, transmission_method=disease.transmission_method,
        recovery_probability=disease.recovery_probability, estimated_recovery_time=disease.estimated_recovery_time,
        version=disease.version,
    )


@router.get("")
def list_diseases(
    plant_id: Optional[UUID] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    page_size = min(page_size, 100)
    items, total = kb_service.list_diseases(plant_id, search, page, page_size)
    return {
        "items": [_to_schema(d) for d in items],
        "page": page, "page_size": page_size, "total": total,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.post("", response_model=DiseaseResponseSchema, status_code=status.HTTP_201_CREATED)
def create_disease(
    body: DiseaseCreateRequest,
    current_user: User = Depends(require_roles(UserRole.AGRONOMIST, UserRole.ADMIN)),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    disease = kb_service.create_or_update_disease(
        actor=current_user, plant_canonical_name=body.plant_canonical_name, name=body.name,
        disease_type=body.disease_type, description=body.description, symptoms=body.symptoms,
        causes=body.causes, transmission_method=body.transmission_method,
        recovery_probability=body.recovery_probability, estimated_recovery_time=body.estimated_recovery_time,
    )
    return _to_schema(disease)


@router.put("/{disease_id}", response_model=DiseaseResponseSchema)
def update_disease(
    disease_id: UUID,
    body: DiseaseCreateRequest,
    current_user: User = Depends(require_roles(UserRole.AGRONOMIST, UserRole.ADMIN)),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    # Versioning semantics: create_or_update_disease supersedes the prior current
    # version for the same (plant, name) pair (NFR-DATA-1), so PUT and POST share
    # the same underlying operation — this mirrors UC-09's "create new version"
    # flow described in the state diagram.
    disease = kb_service.create_or_update_disease(
        actor=current_user, plant_canonical_name=body.plant_canonical_name, name=body.name,
        disease_type=body.disease_type, description=body.description, symptoms=body.symptoms,
        causes=body.causes, transmission_method=body.transmission_method,
        recovery_probability=body.recovery_probability, estimated_recovery_time=body.estimated_recovery_time,
    )
    return _to_schema(disease)
