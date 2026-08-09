"""
Integration tests for the SQLAlchemy repository implementations, run against an
in-memory SQLite database via the cross-dialect GUID type (app/infrastructure/db/base.py)
— proving the same repository code that runs against PostgreSQL in production also
works correctly against SQLite for fast, dependency-free CI runs.

NOT EXECUTABLE IN THIS SANDBOX: requires sqlalchemy, which is not installed here and
there is no network access to install it. Syntax-checked; logically reviewed against
the schema in database/01-schema.sql and the ORM models in
app/infrastructure/db/models/. Uses the shared `db_session` fixture from conftest.py.
"""
from __future__ import annotations

from app.domain.entities.disease import Disease, Treatment, TreatmentCategory
from app.domain.entities.diagnosis import Diagnosis, SeverityLevel
from app.domain.entities.user import Locale, User, UserRole
from app.infrastructure.repositories.diagnosis_repository import SqlAlchemyDiagnosisRepository
from app.infrastructure.repositories.knowledge_base_repository import (
    SqlAlchemyDiseaseRepository,
    SqlAlchemyPlantRepository,
    SqlAlchemyTreatmentRepository,
)
from app.infrastructure.repositories.user_repository import SqlAlchemyUserRepository


class TestUserRepository:
    def test_create_and_get_by_email(self, db_session):
        repo = SqlAlchemyUserRepository(db_session)
        user = User(id=None, email="repo@test.com", password_hash="hash", full_name="Repo Test",
                     role=UserRole.FARMER, is_active=True, preferred_locale=Locale.EN)
        created = repo.create(user)
        assert created.id is not None

        fetched = repo.get_by_email("repo@test.com")
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_email_is_case_insensitive(self, db_session):
        repo = SqlAlchemyUserRepository(db_session)
        repo.create(User(id=None, email="MixedCase@Test.com", password_hash="h", full_name="X",
                          role=UserRole.FARMER))
        assert repo.get_by_email("mixedcase@test.com") is not None

    def test_list_filters_by_role(self, db_session):
        repo = SqlAlchemyUserRepository(db_session)
        repo.create(User(id=None, email="f1@t.com", password_hash="h", full_name="F1", role=UserRole.FARMER))
        repo.create(User(id=None, email="a1@t.com", password_hash="h", full_name="A1", role=UserRole.ADMIN))

        farmers, total = repo.list(role="farmer", is_active=None, search=None, page=1, page_size=10)
        assert total == 1
        assert farmers[0].role == UserRole.FARMER


class TestKnowledgeBaseRepositories:
    def test_plant_get_or_create_is_idempotent(self, db_session):
        repo = SqlAlchemyPlantRepository(db_session)
        p1 = repo.get_or_create("tomato")
        p2 = repo.get_or_create("tomato")
        assert p1.id == p2.id

    def test_disease_versioning_supersedes_prior_version(self, db_session):
        plant_repo = SqlAlchemyPlantRepository(db_session)
        disease_repo = SqlAlchemyDiseaseRepository(db_session)
        plant = plant_repo.get_or_create("tomato")

        d1 = disease_repo.create_version(Disease(
            id=None, plant_id=plant.id, name="Early Blight", disease_type="fungal",
            description="v1", symptoms=[], causes=[],
        ))
        assert d1.version == 1

        d2 = disease_repo.create_version(Disease(
            id=None, plant_id=plant.id, name="Early Blight", disease_type="fungal",
            description="v2 — corrected", symptoms=[], causes=[],
        ))
        assert d2.version == 2

        current = disease_repo.get_current_by_plant_and_name(plant.id, "Early Blight")
        assert current.id == d2.id
        assert current.description == "v2 — corrected"

    def test_treatment_dosage_guard_raises_at_repository_level(self, db_session):
        plant_repo = SqlAlchemyPlantRepository(db_session)
        disease_repo = SqlAlchemyDiseaseRepository(db_session)
        treatment_repo = SqlAlchemyTreatmentRepository(db_session)

        plant = plant_repo.get_or_create("date_palm")
        disease = disease_repo.create_version(Disease(
            id=None, plant_id=plant.id, name="Red Palm Weevil", disease_type="pest",
            description="desc", symptoms=[], causes=[],
        ))

        import pytest
        with pytest.raises(ValueError):
            treatment_repo.create_version(Treatment(
                id=None, disease_id=disease.id, category=TreatmentCategory.CHEMICAL,
                instructions="Apply insecticide", source_citation=None, authority_referral_only=False,
            ))


class TestDiagnosisRepository:
    def test_create_and_retrieve_diagnosis_with_child_records(self, db_session):
        user_repo = SqlAlchemyUserRepository(db_session)
        plant_repo = SqlAlchemyPlantRepository(db_session)
        diagnosis_repo = SqlAlchemyDiagnosisRepository(db_session)

        user = user_repo.create(User(id=None, email="scanner@t.com", password_hash="h",
                                       full_name="Scanner", role=UserRole.FARMER))
        plant = plant_repo.get_or_create("tomato")

        diagnosis = Diagnosis(
            id=None, user_id=user.id, plant_id=plant.id, disease_id=None,
            confidence_score=87.5, severity_level=SeverityLevel.MODERATE,
            affected_area_pct=30.0, healthy_area_pct=70.0, original_image_ref="scans/x.jpg",
        )
        saved = diagnosis_repo.create(diagnosis)
        assert saved.id is not None

        fetched = diagnosis_repo.get_by_id(saved.id)
        assert fetched.confidence_score == 87.5
        assert fetched.severity_level == SeverityLevel.MODERATE

    def test_dashboard_summary_counts_are_correct(self, db_session):
        user_repo = SqlAlchemyUserRepository(db_session)
        plant_repo = SqlAlchemyPlantRepository(db_session)
        diagnosis_repo = SqlAlchemyDiagnosisRepository(db_session)

        user = user_repo.create(User(id=None, email="dash@t.com", password_hash="h",
                                       full_name="Dash", role=UserRole.FARMER))
        plant = plant_repo.get_or_create("tomato")

        diagnosis_repo.create(Diagnosis(
            id=None, user_id=user.id, plant_id=plant.id, disease_id=None,
            confidence_score=99.0, severity_level=None, affected_area_pct=None,
            healthy_area_pct=None, original_image_ref="scans/healthy.jpg",
        ))

        summary = diagnosis_repo.dashboard_summary(user_id=user.id)
        assert summary["total_scans"] == 1
        assert summary["healthy_count"] == 1
        assert summary["diseased_count"] == 0

    def test_attach_report_links_report_to_diagnosis(self, db_session):
        user_repo = SqlAlchemyUserRepository(db_session)
        diagnosis_repo = SqlAlchemyDiagnosisRepository(db_session)
        user = user_repo.create(User(id=None, email="rpt@t.com", password_hash="h",
                                       full_name="Rpt", role=UserRole.FARMER))
        diagnosis = diagnosis_repo.create(Diagnosis(
            id=None, user_id=user.id, plant_id=None, disease_id=None, confidence_score=70.0,
            severity_level=None, affected_area_pct=None, healthy_area_pct=None,
            original_image_ref="scans/y.jpg",
        ))
        diagnosis_repo.attach_report(diagnosis.id, file_ref="reports/y.pdf", qr_code_ref="reports/y.pdf")

        fetched = diagnosis_repo.get_by_id(diagnosis.id)
        assert fetched.report is not None
        assert fetched.report.file_ref == "reports/y.pdf"
