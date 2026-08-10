"""
Unit tests for the Gemini multimodal reasoning layer
(infrastructure/external/gemini_client.py, application/services/gemini_analysis_service.py).

These tests mock `google.genai.Client` entirely — there is no network route to
generativelanguage.googleapis.com in this environment (see
docs/GEMINI_INTEGRATION.md "Live validation status"), so a real Gemini call is
BLOCKED here by design, not by a test gap. What IS verified for real: the SDK
import succeeds, the two-call request shape is built correctly, and — most
importantly — every failure path (disabled, network/SDK exception, invalid JSON,
schema-invalid JSON, empty response) degrades to status="unavailable"/"disabled"
without ever raising, matching requirement #8 ("Gemini is an enhancement, not the
single point of failure").
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.application.services.gemini_analysis_service import GeminiAnalysisService
from app.domain.entities.disease import Disease, Plant, Treatment, TreatmentCategory
from app.infrastructure.external.gemini_client import GeminiClient, GeminiRequestContext, _GeminiTools


def _make_ctx() -> GeminiRequestContext:
    return GeminiRequestContext(
        image_bytes=b"fake-jpeg-bytes",
        image_mime_type="image/jpeg",
        plant_name="tomato",
        cv_condition="early_blight",
        cv_confidence_score=91.0,
        cv_severity_level="moderate",
        cv_affected_area_pct=28.0,
        disease_description="A common fungal disease of tomato.",
        disease_symptoms=["dark concentric spots"],
        weather_summary="Temperature: 29°C, Humidity: 60%",
    )


def _repos():
    return MagicMock(), MagicMock(), MagicMock()


class TestGeminiDisabled:
    """Requirement: missing GEMINI_API_KEY -> status='disabled', no SDK call attempted."""

    def test_analyze_returns_disabled_when_no_api_key(self):
        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = False
            client = GeminiClient()
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)
        assert result.status == "disabled"
        assert result.analysis is None

    def test_service_returns_none_when_disabled(self):
        """GeminiAnalysisService must return None (not an AiAnalysis row) when
        disabled, so ScanOrchestrator persists nothing at all for this scan."""
        fake_client = MagicMock()
        fake_client.analyze.return_value = MagicMock(status="disabled", analysis=None, message=None)
        service = GeminiAnalysisService(client=fake_client)
        plant_repo, disease_repo, treatment_repo = _repos()
        result = service.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)
        assert result is None


class TestGeminiSuccessPath:
    """Mocks the google-genai SDK's two generate_content calls to verify the
    reasoning->structuring request shape and successful parsing into
    GeminiAnalysisSchema / AiAnalysis."""

    def test_analyze_success_returns_ok_status_with_parsed_analysis(self):
        valid_json = (
            '{"diagnosis_explanation": "Symptoms match early blight.", '
            '"observed_symptoms": ["dark spots", "yellowing"], '
            '"cv_consistency": "consistent", '
            '"confidence_assessment": "Well supported by visible lesions.", '
            '"severity_explanation": "Moderate spread across lower leaves.", '
            '"treatment_guidance": ["Apply organic treatment per database record."], '
            '"prevention_guidance": ["Rotate crops."], '
            '"environmental_risk": "High humidity increases spread risk.", '
            '"urgency": "medium"}'
        )
        reasoning_response = MagicMock(text="Detailed reasoning about the visible symptoms...")
        structure_response = MagicMock(text=valid_json)

        mock_sdk_client = MagicMock()
        mock_sdk_client.models.generate_content.side_effect = [reasoning_response, structure_response]

        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = True
            mock_settings.gemini_api_key = "fake-key-not-real"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_timeout_seconds = 20.0
            mock_settings.gemini_max_tool_calls = 6

            client = GeminiClient()
            client._get_sdk_client = MagicMock(return_value=mock_sdk_client)
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert result.status == "ok"
        assert result.analysis is not None
        assert result.analysis.cv_consistency.value == "consistent"
        assert result.analysis.urgency.value == "medium"
        assert result.analysis.treatment_guidance == ["Apply organic treatment per database record."]
        assert mock_sdk_client.models.generate_content.call_count == 2
        # Never exposes the key in the returned result object.
        assert "fake-key-not-real" not in str(result)

    def test_analysis_service_maps_success_result_to_domain_entity(self):
        from app.infrastructure.external.gemini_client import GeminiAnalysisResult
        from app.interface.schemas.ai_analysis_schemas import AnalysisUrgency, CvConsistency, GeminiAnalysisSchema

        fake_client = MagicMock()
        fake_client.analyze.return_value = GeminiAnalysisResult(
            status="ok",
            analysis=GeminiAnalysisSchema(
                diagnosis_explanation="ok", observed_symptoms=["spot"],
                cv_consistency=CvConsistency.CONSISTENT, confidence_assessment="ok",
                severity_explanation="ok", treatment_guidance=["t"], prevention_guidance=["p"],
                environmental_risk="ok", urgency=AnalysisUrgency.LOW,
            ),
            model_name="gemini-2.5-flash",
        )
        service = GeminiAnalysisService(client=fake_client)
        plant_repo, disease_repo, treatment_repo = _repos()
        entity = service.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert entity is not None
        assert entity.status == "ok"
        assert entity.cv_consistency == "consistent"
        assert entity.urgency == "low"
        assert entity.model_name == "gemini-2.5-flash"


class TestGeminiFailurePaths:
    """Requirement #8: network failure, timeout, rate limit, and any other SDK
    exception must all degrade to status='unavailable', never raise."""

    def test_analyze_returns_unavailable_when_sdk_raises(self):
        mock_sdk_client = MagicMock()
        mock_sdk_client.models.generate_content.side_effect = ConnectionError("network unreachable")

        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = True
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_timeout_seconds = 20.0
            mock_settings.gemini_max_tool_calls = 6

            client = GeminiClient()
            client._get_sdk_client = MagicMock(return_value=mock_sdk_client)
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert result.status == "unavailable"
        assert result.analysis is None
        assert result.message == "AI analysis temporarily unavailable."

    def test_analyze_returns_unavailable_on_empty_reasoning_response(self):
        mock_sdk_client = MagicMock()
        mock_sdk_client.models.generate_content.return_value = MagicMock(text="")

        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = True
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_timeout_seconds = 20.0
            mock_settings.gemini_max_tool_calls = 6

            client = GeminiClient()
            client._get_sdk_client = MagicMock(return_value=mock_sdk_client)
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert result.status == "unavailable"

    def test_service_persists_unavailable_status_with_message(self):
        from app.infrastructure.external.gemini_client import GeminiAnalysisResult

        fake_client = MagicMock()
        fake_client.analyze.return_value = GeminiAnalysisResult(
            status="unavailable", analysis=None, message="AI analysis temporarily unavailable.",
        )
        service = GeminiAnalysisService(client=fake_client)
        plant_repo, disease_repo, treatment_repo = _repos()
        entity = service.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert entity is not None
        assert entity.status == "unavailable"
        assert entity.message == "AI analysis temporarily unavailable."


class TestGeminiInvalidStructuredResponse:
    """Requirement: 'The response must fail safely if Gemini returns
    invalid/unexpected data' — malformed JSON and schema-violating JSON must both
    be rejected rather than partially trusted."""

    def test_analyze_returns_unavailable_on_malformed_json(self):
        reasoning_response = MagicMock(text="Some reasoning text.")
        structure_response = MagicMock(text="{not valid json at all")

        mock_sdk_client = MagicMock()
        mock_sdk_client.models.generate_content.side_effect = [reasoning_response, structure_response]

        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = True
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_timeout_seconds = 20.0
            mock_settings.gemini_max_tool_calls = 6

            client = GeminiClient()
            client._get_sdk_client = MagicMock(return_value=mock_sdk_client)
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert result.status == "unavailable"
        assert result.analysis is None

    def test_analyze_returns_unavailable_on_schema_violating_json(self):
        """Valid JSON, but missing required fields / wrong enum value — must be
        rejected by Pydantic validation, not silently accepted."""
        reasoning_response = MagicMock(text="Some reasoning text.")
        # missing every required field, and an invalid enum value for urgency
        invalid_shape_json = '{"urgency": "extremely_urgent_not_a_real_value"}'
        structure_response = MagicMock(text=invalid_shape_json)

        mock_sdk_client = MagicMock()
        mock_sdk_client.models.generate_content.side_effect = [reasoning_response, structure_response]

        with patch("app.infrastructure.external.gemini_client.settings") as mock_settings:
            mock_settings.gemini_enabled = True
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.5-flash"
            mock_settings.gemini_timeout_seconds = 20.0
            mock_settings.gemini_max_tool_calls = 6

            client = GeminiClient()
            client._get_sdk_client = MagicMock(return_value=mock_sdk_client)
            plant_repo, disease_repo, treatment_repo = _repos()
            result = client.analyze(_make_ctx(), plant_repo, disease_repo, treatment_repo)

        assert result.status == "unavailable"
        assert result.analysis is None


class TestGeminiToolsEnforceBr6:
    """Requirement #3/#4: function-calling tools are the enforcement point for BR6
    (chemical dosage must be source-cited or explicitly authority-referral-only) —
    Gemini cannot get an unverified dosage by calling the tool differently, because
    the tool itself substitutes the safe fallback string."""

    def test_get_treatment_info_withholds_unverified_chemical_dosage(self):
        plant_id = uuid4()
        disease_id = uuid4()
        plant_repo = MagicMock()
        plant_repo.get_by_canonical_name.return_value = Plant(id=plant_id, canonical_name="tomato")
        disease_repo = MagicMock()
        disease_repo.get_current_by_plant_and_name.return_value = Disease(
            id=disease_id, plant_id=plant_id, name="early_blight", disease_type="fungal",
            description="desc", symptoms=[], causes=[],
        )
        treatment_repo = MagicMock()
        treatment_repo.get_current_for_disease.return_value = [
            Treatment(
                id=uuid4(), disease_id=disease_id, category=TreatmentCategory.CHEMICAL,
                instructions="Apply 50ml/L of ProductX twice weekly.",
                source_citation=None, authority_referral_only=False,  # NOT verified
            ),
        ]

        tools = _GeminiTools(plant_repo, disease_repo, treatment_repo, weather_summary=None)
        result = tools.get_treatment_info("tomato", "early_blight")

        assert result["found"] is True
        assert "ProductX" not in result["chemical"]["instructions"]
        assert "consult your local agricultural authority" in result["chemical"]["instructions"].lower()

    def test_get_treatment_info_returns_verified_chemical_dosage(self):
        plant_id = uuid4()
        disease_id = uuid4()
        plant_repo = MagicMock()
        plant_repo.get_by_canonical_name.return_value = Plant(id=plant_id, canonical_name="tomato")
        disease_repo = MagicMock()
        disease_repo.get_current_by_plant_and_name.return_value = Disease(
            id=disease_id, plant_id=plant_id, name="early_blight", disease_type="fungal",
            description="desc", symptoms=[], causes=[],
        )
        treatment_repo = MagicMock()
        treatment_repo.get_current_for_disease.return_value = [
            Treatment(
                id=uuid4(), disease_id=disease_id, category=TreatmentCategory.CHEMICAL,
                instructions="Apply 50ml/L of ProductX twice weekly.",
                source_citation="Verified: National Agricultural Extension Manual 2025",
                authority_referral_only=False,
            ),
        ]

        tools = _GeminiTools(plant_repo, disease_repo, treatment_repo, weather_summary=None)
        result = tools.get_treatment_info("tomato", "early_blight")

        assert result["chemical"]["instructions"] == "Apply 50ml/L of ProductX twice weekly."

    def test_get_weather_never_invents_data_when_unavailable(self):
        plant_repo, disease_repo, treatment_repo = _repos()
        tools = _GeminiTools(plant_repo, disease_repo, treatment_repo, weather_summary=None)
        result = tools.get_weather()
        assert result == {"available": False}
