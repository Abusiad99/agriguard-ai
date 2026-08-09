"""
Unit tests for KnowledgeBaseService — FR-ADMIN-2/3, BR6.

NOTE ON EXECUTABILITY: same as test_auth_service.py — this module transitively
imports app.core.exceptions and app.domain layers only (no passlib/pydantic), so it
IS importable and executable in this sandbox using only pytest, which is itself not
installed here (no network access to install it). Logically verified via the manual
test runner pattern demonstrated for test_domain_entities.py; expected to pass
unchanged under real pytest once dependencies are installed.
"""
from __future__ import annotations

import uuid

import pytest

from app.application.services.knowledge_base_service import KnowledgeBaseService
from app.core.exceptions import AuthorizationError, DosageSourceRequiredError, NotFoundError
from app.domain.entities.disease import Disease, Plant, Treatment, TreatmentCategory
from app.domain.entities.user import User, UserRole


class FakePlantRepository:
    def __init__(self):
        self._plants = {}

    def get_by_canonical_name(self, name):
        return self._plants.get(name)

    def get_or_create(self, name):
        if name not in self._plants:
            self._plants[name] = Plant(id=uuid.uuid4(), canonical_name=name)
        return self._plants[name]

    def list(self):
        return list(self._plants.values())


class FakeDiseaseRepository:
    def __init__(self):
        self._diseases = {}

    def get_current_by_plant_and_name(self, plant_id, name):
        for d in self._diseases.values():
            if d.plant_id == plant_id and d.name == name and d.is_current:
                return d
        return None

    def get_by_id(self, disease_id):
        return self._diseases.get(disease_id)

    def create_version(self, disease):
        prior = self.get_current_by_plant_and_name(disease.plant_id, disease.name)
        version = 1
        if prior:
            prior.is_current = False
            version = prior.version + 1
        disease.id = uuid.uuid4()
        disease.version = version
        disease.is_current = True
        self._diseases[disease.id] = disease
        return disease

    def list(self, plant_id, search, page, page_size):
        items = [d for d in self._diseases.values() if d.is_current]
        return items, len(items)


class FakeTreatmentRepository:
    def __init__(self):
        self._treatments = {}

    def get_current_for_disease(self, disease_id):
        return [t for t in self._treatments.values() if t.disease_id == disease_id and t.is_current]

    def get_by_id(self, treatment_id):
        return self._treatments.get(treatment_id)

    def create_version(self, treatment):
        treatment.id = uuid.uuid4()
        self._treatments[treatment.id] = treatment
        return treatment


class FakeAuditLogRepository:
    def __init__(self):
        self.entries = []

    def log(self, actor_user_id, action, entity_type, entity_id, metadata):
        self.entries.append((actor_user_id, action, entity_type, entity_id, metadata))


@pytest.fixture()
def kb_service():
    return KnowledgeBaseService(FakePlantRepository(), FakeDiseaseRepository(),
                                 FakeTreatmentRepository(), FakeAuditLogRepository())


@pytest.fixture()
def agronomist():
    return User(id=uuid.uuid4(), email="ag@x.com", password_hash="h", full_name="Ag", role=UserRole.AGRONOMIST)


@pytest.fixture()
def farmer():
    return User(id=uuid.uuid4(), email="f@x.com", password_hash="h", full_name="F", role=UserRole.FARMER)


class TestDiseaseKnowledgeBase:
    def test_agronomist_can_create_disease(self, kb_service, agronomist):
        disease = kb_service.create_or_update_disease(
            agronomist, "date_palm", "Bayoud Disease", "fungal", "A vascular wilt disease.",
            ["wilting fronds"], ["Fusarium oxysporum"], "soil-borne", None, None,
        )
        assert disease.version == 1
        assert disease.is_current is True

    def test_farmer_cannot_create_disease(self, kb_service, farmer):
        with pytest.raises(AuthorizationError):
            kb_service.create_or_update_disease(
                farmer, "tomato", "Early Blight", "fungal", "desc", [], [], None, None, None,
            )

    def test_updating_a_disease_creates_new_version_and_supersedes_prior(self, kb_service, agronomist):
        first = kb_service.create_or_update_disease(
            agronomist, "tomato", "Early Blight", "fungal", "v1 description", [], [], None, None, None,
        )
        second = kb_service.create_or_update_disease(
            agronomist, "tomato", "Early Blight", "fungal", "v2 description — corrected", [], [], None, None, None,
        )
        assert second.version == 2
        assert second.is_current is True


class TestTreatmentDosageEnforcement:
    """BR6, enforced at the application layer (not just the DB CHECK constraint) so
    the API can return a clean 422 rather than a raw DB error."""

    def test_chemical_treatment_without_citation_is_rejected(self, kb_service, agronomist):
        disease = kb_service.create_or_update_disease(
            agronomist, "tomato", "Late Blight", "fungal", "desc", [], [], None, None, None,
        )
        with pytest.raises(DosageSourceRequiredError):
            kb_service.create_or_update_treatment(
                agronomist, disease.id, "chemical", "Apply fungicide X", None, None, False,
            )

    def test_chemical_treatment_with_citation_is_accepted(self, kb_service, agronomist):
        disease = kb_service.create_or_update_disease(
            agronomist, "tomato", "Late Blight", "fungal", "desc", [], [], None, None, None,
        )
        treatment = kb_service.create_or_update_treatment(
            agronomist, disease.id, "chemical", "Apply fungicide X", "Wear gloves.",
            "FAO Pesticide Guideline 2023", False,
        )
        assert treatment.category == TreatmentCategory.CHEMICAL

    def test_chemical_treatment_marked_authority_referral_only_is_accepted(self, kb_service, agronomist):
        disease = kb_service.create_or_update_disease(
            agronomist, "tomato", "Late Blight", "fungal", "desc", [], [], None, None, None,
        )
        treatment = kb_service.create_or_update_treatment(
            agronomist, disease.id, "chemical", "Consult local authority for approved fungicide.",
            None, None, True,
        )
        assert treatment.authority_referral_only is True

    def test_treatment_for_nonexistent_disease_raises_not_found(self, kb_service, agronomist):
        with pytest.raises(NotFoundError):
            kb_service.create_or_update_treatment(
                agronomist, uuid.uuid4(), "organic", "neem oil", None, None, False,
            )
