"""
Unit tests for the domain layer — pure business logic, zero infrastructure
dependencies (no DB, no HTTP, no mocks needed). These are the fastest and most
reliable tests in the suite since the domain layer has no external dependencies by
design (NFR-MAINT-1).
"""
from __future__ import annotations

from app.domain.entities.diagnosis import Diagnosis, SeverityLevel
from app.domain.entities.disease import Disease, Treatment, TreatmentCategory
from app.domain.entities.user import User, UserRole


class TestUserRoleLogic:
    def test_farmer_has_no_elevated_permissions(self):
        user = User(id=None, email="f@x.com", password_hash="h", full_name="F", role=UserRole.FARMER)
        assert user.is_admin() is False
        assert user.can_edit_knowledge_base() is False
        assert user.can_access_admin_panel() is False

    def test_admin_has_all_permissions(self):
        user = User(id=None, email="a@x.com", password_hash="h", full_name="A", role=UserRole.ADMIN)
        assert user.is_admin() is True
        assert user.can_edit_knowledge_base() is True
        assert user.can_access_admin_panel() is True

    def test_agronomist_can_edit_kb_but_not_admin_panel(self):
        user = User(id=None, email="ag@x.com", password_hash="h", full_name="Ag", role=UserRole.AGRONOMIST)
        assert user.can_edit_knowledge_base() is True
        assert user.can_access_admin_panel() is False


class TestTreatmentDosageVerification:
    """BR6: a chemical treatment must carry a source citation unless explicitly
    marked authority-referral-only."""

    def test_chemical_without_citation_is_unverified(self):
        t = Treatment(id=None, disease_id=None, category=TreatmentCategory.CHEMICAL, instructions="spray")
        assert t.is_dosage_verified() is False

    def test_chemical_with_citation_is_verified(self):
        t = Treatment(id=None, disease_id=None, category=TreatmentCategory.CHEMICAL,
                       instructions="spray", source_citation="FAO Guideline 2023")
        assert t.is_dosage_verified() is True

    def test_chemical_with_authority_referral_flag_is_verified(self):
        t = Treatment(id=None, disease_id=None, category=TreatmentCategory.CHEMICAL,
                       instructions="spray", authority_referral_only=True)
        assert t.is_dosage_verified() is True

    def test_organic_treatment_never_requires_citation(self):
        t = Treatment(id=None, disease_id=None, category=TreatmentCategory.ORGANIC, instructions="neem oil")
        assert t.is_dosage_verified() is True

    def test_biological_treatment_never_requires_citation(self):
        t = Treatment(id=None, disease_id=None, category=TreatmentCategory.BIOLOGICAL, instructions="predatory mites")
        assert t.is_dosage_verified() is True


class TestDiseaseRecoveryData:
    """FR-RESULT-2: recovery probability/time only shown when actually present."""

    def test_disease_without_recovery_data(self):
        d = Disease(id=None, plant_id=None, name="Rust", disease_type="fungal", description="desc")
        assert d.has_recovery_data() is False

    def test_disease_with_recovery_probability_only(self):
        d = Disease(id=None, plant_id=None, name="Rust", disease_type="fungal", description="desc",
                     recovery_probability=75.0)
        assert d.has_recovery_data() is True

    def test_disease_with_recovery_time_only(self):
        d = Disease(id=None, plant_id=None, name="Rust", disease_type="fungal", description="desc",
                     estimated_recovery_time="2-3 weeks")
        assert d.has_recovery_data() is True


class TestDiagnosisLowConfidence:
    """BR1: low-confidence diagnoses are flagged for manual review, distinct from
    an outright unrecognized-plant result."""

    def test_low_confidence_flag_triggers_review_recommendation(self):
        diag = Diagnosis(
            id=None, user_id=None, plant_id=None, disease_id=None, confidence_score=45.0,
            severity_level=SeverityLevel.MILD, affected_area_pct=5.0, healthy_area_pct=95.0,
            original_image_ref="ref", low_confidence_flag=True, unrecognized_plant=False,
        )
        assert diag.is_reviewable_low_confidence() is True

    def test_unrecognized_plant_is_not_a_reviewable_low_confidence_diagnosis(self):
        diag = Diagnosis(
            id=None, user_id=None, plant_id=None, disease_id=None, confidence_score=20.0,
            severity_level=None, affected_area_pct=None, healthy_area_pct=None,
            original_image_ref="ref", low_confidence_flag=True, unrecognized_plant=True,
        )
        # unrecognized_plant is a distinct terminal state (Alt Flow A1), not a
        # "reviewable" diagnosis with an assigned disease.
        assert diag.is_reviewable_low_confidence() is False

    def test_high_confidence_diagnosis_is_not_flagged(self):
        diag = Diagnosis(
            id=None, user_id=None, plant_id=None, disease_id=None, confidence_score=95.0,
            severity_level=SeverityLevel.SEVERE, affected_area_pct=60.0, healthy_area_pct=40.0,
            original_image_ref="ref", low_confidence_flag=False, unrecognized_plant=False,
        )
        assert diag.is_reviewable_low_confidence() is False
