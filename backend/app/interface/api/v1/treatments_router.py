"""Treatments routes — FR-TREAT, FR-ADMIN-3 (UC-10), BR6. See API spec §6."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.application.services.knowledge_base_service import KnowledgeBaseService
from app.domain.entities.user import User, UserRole
from app.interface.api.v1.dependencies import get_current_user, get_knowledge_base_service, require_roles
from app.interface.schemas.common_schemas import TreatmentCreateRequest, TreatmentResponseSchema

router = APIRouter(prefix="/treatments", tags=["Knowledge Base — Treatments"])


def _to_schema(t) -> TreatmentResponseSchema:
    return TreatmentResponseSchema(
        id=str(t.id), disease_id=str(t.disease_id), category=t.category.value, instructions=t.instructions,
        safety_notes=t.safety_notes, source_citation=t.source_citation,
        authority_referral_only=t.authority_referral_only, version=t.version,
    )


@router.get("")
def list_treatments(
    disease_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    treatments = kb_service.get_treatments_for_disease(disease_id)
    return {"items": [_to_schema(t) for t in treatments]}


@router.post("", response_model=TreatmentResponseSchema, status_code=status.HTTP_201_CREATED)
def create_treatment(
    body: TreatmentCreateRequest,
    current_user: User = Depends(require_roles(UserRole.AGRONOMIST, UserRole.ADMIN)),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    treatment = kb_service.create_or_update_treatment(
        actor=current_user, disease_id=UUID(body.disease_id), category=body.category,
        instructions=body.instructions, safety_notes=body.safety_notes,
        source_citation=body.source_citation, authority_referral_only=body.authority_referral_only,
    )
    return _to_schema(treatment)


@router.put("/{treatment_id}", response_model=TreatmentResponseSchema)
def update_treatment(
    treatment_id: UUID,
    body: TreatmentCreateRequest,
    current_user: User = Depends(require_roles(UserRole.AGRONOMIST, UserRole.ADMIN)),
    kb_service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    # Same versioning rationale as diseases_router.update_disease.
    treatment = kb_service.create_or_update_treatment(
        actor=current_user, disease_id=UUID(body.disease_id), category=body.category,
        instructions=body.instructions, safety_notes=body.safety_notes,
        source_citation=body.source_citation, authority_referral_only=body.authority_referral_only,
    )
    return _to_schema(treatment)
