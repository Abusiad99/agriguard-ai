"""Knowledge-base references — read for any signed-in user, write for agronomists and
admins. See app/application/services/reference_service.py."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.application.services.reference_service import ReferenceService, reference_to_dict
from app.domain.entities.user import User, UserRole
from app.interface.api.v1.dependencies import get_current_user, get_reference_service, require_roles

router = APIRouter(prefix="/references", tags=["Knowledge Base — References"])
_EDITORS = (UserRole.AGRONOMIST, UserRole.ADMIN)


class ReferenceBody(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)
    authors: Optional[str] = Field(default=None, max_length=500)
    organization: Optional[str] = Field(default=None, max_length=300)
    url: Optional[str] = Field(default=None, max_length=1000)
    doi: Optional[str] = Field(default=None, max_length=200)
    publication_date: Optional[str] = Field(default=None, max_length=60)
    source_type: Optional[str] = Field(default=None, max_length=40)
    language: Optional[str] = Field(default=None, max_length=8)
    notes: Optional[str] = Field(default=None, max_length=4000)
    verified_on: Optional[str] = Field(default=None, max_length=10)
    is_active: Optional[bool] = None


class ClaimBody(BaseModel):
    subject_type: str = Field(max_length=20)
    subject_key: Optional[str] = Field(default=None, max_length=200)
    subject_id: Optional[str] = Field(default=None, max_length=40)
    claim: str = Field(max_length=1000)


@router.get("")
def list_references(q: Optional[str] = Query(default=None, max_length=100),
                    subject_type: Optional[str] = Query(default=None, max_length=20),
                    subject_key: Optional[str] = Query(default=None, max_length=200),
                    subject_id: Optional[UUID] = None, include_inactive: bool = False,
                    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
                    current_user: User = Depends(get_current_user),
                    service: ReferenceService = Depends(get_reference_service)):
    rows, total = service.list(q=q, subject_type=subject_type, subject_key=subject_key, subject_id=subject_id,
                               include_inactive=include_inactive, page=page, page_size=page_size)
    return {"items": [reference_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/catalog")
def built_in_catalog(current_user: User = Depends(get_current_user),
                     service: ReferenceService = Depends(get_reference_service)):
    """The verified references AgriGuard's own report rules cite (read-only)."""
    return service.catalog()


@router.get("/{reference_id}")
def get_reference(reference_id: UUID, current_user: User = Depends(get_current_user),
                  service: ReferenceService = Depends(get_reference_service)):
    return reference_to_dict(service.get(reference_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_reference(body: ReferenceBody, current_user: User = Depends(require_roles(*_EDITORS)),
                     service: ReferenceService = Depends(get_reference_service)):
    return reference_to_dict(service.create(current_user, body.model_dump(exclude_unset=True, exclude={"is_active"})))


@router.patch("/{reference_id}")
def update_reference(reference_id: UUID, body: ReferenceBody, current_user: User = Depends(require_roles(*_EDITORS)),
                     service: ReferenceService = Depends(get_reference_service)):
    return reference_to_dict(service.update(current_user, reference_id, body.model_dump(exclude_unset=True)))


@router.delete("/{reference_id}")
def deactivate_reference(reference_id: UUID, current_user: User = Depends(require_roles(*_EDITORS)),
                         service: ReferenceService = Depends(get_reference_service)):
    return reference_to_dict(service.deactivate(current_user, reference_id))


@router.post("/{reference_id}/claims", status_code=status.HTTP_201_CREATED)
def add_claim(reference_id: UUID, body: ClaimBody, current_user: User = Depends(require_roles(*_EDITORS)),
              service: ReferenceService = Depends(get_reference_service)):
    service.add_claim(current_user, reference_id, body.subject_type, body.claim, body.subject_key, body.subject_id)
    return reference_to_dict(service.get(reference_id))


@router.delete("/{reference_id}/claims/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_claim(reference_id: UUID, claim_id: UUID, current_user: User = Depends(require_roles(*_EDITORS)),
                 service: ReferenceService = Depends(get_reference_service)):
    service.remove_claim(current_user, reference_id, claim_id)
