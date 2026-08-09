"""
Unit tests for ScanOrchestrator (UC-03 orchestration logic), using unittest.mock to
substitute every collaborator (storage, AI client, repositories, weather service, PDF
generator) so the test verifies orchestration/sequencing logic in isolation from any
real I/O.

NOT EXECUTABLE IN THIS SANDBOX: app.application.services.scan_service transitively
imports app.core.config (pydantic-settings), app.infrastructure.external.weather_client
(httpx), and app.infrastructure.reporting.pdf_report_generator (qrcode) — none of
which are installed here and there is no network access to install them. Syntax-
checked via `python -m py_compile`; logically reviewed line by line. Expected to pass
under real pytest once `pip install -r backend/requirements.txt` succeeds.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.application.services.scan_service import ScanOrchestrator
from app.core.exceptions import InvalidImageError
from app.domain.entities.disease import Plant


def _make_test_image_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), color=(90, 130, 60)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def mocks():
    storage = MagicMock()
    storage.save_bytes.return_value = "scans/test.jpg"
    storage.resolve_path.return_value = Path("/tmp/fake_scan.jpg")
    storage.exists.return_value = True

    ai_client = MagicMock()
    plant_repo = MagicMock()
    plant_repo.get_or_create.return_value = Plant(id=uuid.uuid4(), canonical_name="tomato")
    disease_repo = MagicMock()
    treatment_repo = MagicMock()
    treatment_repo.get_current_for_disease.return_value = []
    diagnosis_repo = MagicMock()
    weather_service = MagicMock()
    weather_service.get_conditions.return_value = None  # simulate weather unavailable
    pdf_generator = MagicMock()

    return {
        "storage": storage, "ai_client": ai_client, "plant_repo": plant_repo,
        "disease_repo": disease_repo, "treatment_repo": treatment_repo,
        "diagnosis_repo": diagnosis_repo, "weather_service": weather_service,
        "pdf_generator": pdf_generator,
    }


@pytest.fixture()
def orchestrator(mocks):
    return ScanOrchestrator(**mocks)


class TestImageValidation:
    """FR-SCAN-2."""

    def test_invalid_image_bytes_raise_invalid_image_error(self, orchestrator):
        with pytest.raises(InvalidImageError):
            orchestrator.process_scan(user_id=uuid.uuid4(), image_bytes=b"not an image", content_type="image/jpeg")

    def test_valid_image_passes_validation(self, orchestrator, mocks):
        from dataclasses import dataclass

        @dataclass
        class FakeOutput:
            unrecognized_plant: bool = False
            plant: str = "tomato"
            condition: str = "healthy"
            confidence_score: float = 88.0
            low_confidence_flag: bool = False
            severity_level: str = None
            affected_area_pct: float = None
            healthy_area_pct: float = None

        mocks["ai_client"].diagnose.return_value = FakeOutput()
        mocks["diagnosis_repo"].create.return_value = MagicMock(id=uuid.uuid4())
        mocks["diagnosis_repo"].get_by_id.return_value = MagicMock(id=uuid.uuid4())

        result = orchestrator.process_scan(
            user_id=uuid.uuid4(), image_bytes=_make_test_image_bytes(), content_type="image/jpeg",
        )
        assert result.status == "completed"
        mocks["storage"].save_bytes.assert_called_once()


class TestUnrecognizedPlantFlow:
    """FR-AI-12, Alt Flow A1: pipeline halts after Step 1 for low plant-ID confidence."""

    def test_unrecognized_plant_short_circuits_before_persistence(self, orchestrator, mocks):
        from dataclasses import dataclass

        @dataclass
        class FakeUnrecognized:
            unrecognized_plant: bool = True
            confidence_score: float = 12.0

        mocks["ai_client"].diagnose.return_value = FakeUnrecognized()

        result = orchestrator.process_scan(
            user_id=uuid.uuid4(), image_bytes=_make_test_image_bytes(), content_type="image/jpeg",
        )
        assert result.status == "unrecognized_plant"
        mocks["diagnosis_repo"].create.assert_not_called()
        mocks["pdf_generator"].generate.assert_not_called()


class TestWeatherDegradation:
    """NFR-AVAIL-2/BR7: the pipeline must complete even when weather is unavailable."""

    def test_scan_completes_when_weather_service_returns_none(self, orchestrator, mocks):
        from dataclasses import dataclass

        @dataclass
        class FakeOutput:
            unrecognized_plant: bool = False
            plant: str = "date_palm"
            condition: str = "red_palm_weevil"
            confidence_score: float = 93.0
            low_confidence_flag: bool = False
            severity_level: str = "severe"
            affected_area_pct: float = 40.0
            healthy_area_pct: float = 60.0

        mocks["ai_client"].diagnose.return_value = FakeOutput()
        mocks["weather_service"].get_conditions.return_value = None  # explicit failure
        mocks["diagnosis_repo"].create.return_value = MagicMock(id=uuid.uuid4())
        mocks["diagnosis_repo"].get_by_id.return_value = MagicMock(id=uuid.uuid4())

        result = orchestrator.process_scan(
            user_id=uuid.uuid4(), image_bytes=_make_test_image_bytes(), content_type="image/jpeg",
            latitude=31.6, longitude=-7.9,
        )
        assert result.status == "completed"
