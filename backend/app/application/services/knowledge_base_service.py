"""
KnowledgeBaseService — FR-TREAT, FR-ADMIN-2/3 (UC-09, UC-10). Enforces BR6 (dosage
source requirement) at the application layer as well as the DB CHECK constraint /
repository guard, so the API can return a clear 422 before ever touching the DB.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.core.exceptions import DosageSourceRequiredError, NotFoundError, ValidationError
from app.domain.entities.disease import Disease, Plant, Treatment, TreatmentCategory
from app.domain.repositories.interfaces import (
    IAuditLogRepository,
    IDiseaseRepository,
    IPlantRepository,
    ITreatmentRepository,
)
from app.domain.entities.user import User


class KnowledgeBaseService:
    def __init__(self, plant_repo: IPlantRepository, disease_repo: IDiseaseRepository,
                 treatment_repo: ITreatmentRepository, audit_repo: IAuditLogRepository):
        self.plant_repo = plant_repo
        self.disease_repo = disease_repo
        self.treatment_repo = treatment_repo
        self.audit_repo = audit_repo

    def list_diseases(self, plant_id: Optional[UUID], search: Optional[str], page: int, page_size: int):
        return self.disease_repo.list(plant_id, search, page, page_size)

    def get_treatments_for_disease(self, disease_id: UUID) -> List[Treatment]:
        if self.disease_repo.get_by_id(disease_id) is None:
            raise NotFoundError("Disease not found.")
        return self.treatment_repo.get_current_for_disease(disease_id)

    def create_or_update_disease(self, actor: User, plant_canonical_name: str, name: str,
                                  disease_type: Optional[str], description: str, symptoms: List[str],
                                  causes: List[str], transmission_method: Optional[str],
                                  recovery_probability: Optional[float],
                                  estimated_recovery_time: Optional[str]) -> Disease:
        if not actor.can_edit_knowledge_base():
            from app.core.exceptions import AuthorizationError
            raise AuthorizationError("Only agronomists and admins may edit the knowledge base.")
        if not description or not name:
            raise ValidationError("Disease 'name' and 'description' are required.")

        plant = self.plant_repo.get_or_create(plant_canonical_name)
        disease = Disease(
            id=None, plant_id=plant.id, name=name, disease_type=disease_type, description=description,
            symptoms=symptoms, causes=causes, transmission_method=transmission_method,
            recovery_probability=recovery_probability, estimated_recovery_time=estimated_recovery_time,
            created_by=actor.id,
        )
        saved = self.disease_repo.create_version(disease)
        self.audit_repo.log(actor.id, "upsert_disease", "disease", saved.id,
                             {"name": name, "version": saved.version})
        return saved

    def create_or_update_treatment(self, actor: User, disease_id: UUID, category: str, instructions: str,
                                    safety_notes: Optional[str], source_citation: Optional[str],
                                    authority_referral_only: bool) -> Treatment:
        if not actor.can_edit_knowledge_base():
            from app.core.exceptions import AuthorizationError
            raise AuthorizationError("Only agronomists and admins may edit the knowledge base.")
        if self.disease_repo.get_by_id(disease_id) is None:
            raise NotFoundError("Disease not found.")
        if not instructions:
            raise ValidationError("Treatment 'instructions' are required.")

        treatment = Treatment(
            id=None, disease_id=disease_id, category=TreatmentCategory(category), instructions=instructions,
            safety_notes=safety_notes, source_citation=source_citation,
            authority_referral_only=authority_referral_only, created_by=actor.id,
        )
        if not treatment.is_dosage_verified():
            raise DosageSourceRequiredError(
                "A chemical treatment requires a source_citation unless "
                "authority_referral_only=True (BR6)."
            )
        saved = self.treatment_repo.create_version(treatment)
        self.audit_repo.log(actor.id, "upsert_treatment", "treatment", saved.id,
                             {"disease_id": str(disease_id), "category": category, "version": saved.version})
        return saved
