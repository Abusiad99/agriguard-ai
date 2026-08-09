"""
Integration tests for PdfReportGenerator — FR-REPORT-1. Generates a real PDF to a
temp file and asserts on the actual output (file exists, non-trivial size, valid PDF
header bytes) rather than mocking reportlab away, since the whole point of this
component is producing a real, openable file.

NOT EXECUTABLE IN THIS SANDBOX: app.infrastructure.reporting.pdf_report_generator
imports the `qrcode` package, which is not installed here and there is no network
access to install it (reportlab itself IS installed and was independently verified
importable — see the Phase 3 validation report). Syntax-checked; logically reviewed.
Expected to pass unchanged once `qrcode` is installed per backend/requirements.txt.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.infrastructure.reporting.pdf_report_generator import PdfReportGenerator, ReportData


@pytest.fixture()
def sample_report_data(tmp_path) -> ReportData:
    image_path = tmp_path / "original.jpg"
    Image.new("RGB", (200, 200), color=(80, 140, 60)).save(image_path)

    heatmap_path = tmp_path / "heatmap.png"
    Image.new("RGB", (200, 200), color=(180, 40, 40)).save(heatmap_path)

    return ReportData(
        diagnosis_id="12345678-1234-1234-1234-123456789012",
        plant_name="tomato",
        disease_name="Early Blight",
        disease_description="A common fungal disease causing concentric leaf spots.",
        severity_level="moderate",
        confidence_score=91.5,
        affected_area_pct=28.0,
        healthy_area_pct=72.0,
        organic_treatment="Apply neem oil weekly.",
        chemical_treatment="Please consult your local agricultural authority for verified dosage guidance.",
        biological_treatment=None,
        prevention_advice=["Ensure proper irrigation.", "Remove infected leaves.", "Rotate crops annually."],
        weather_summary="Temperature: 30°C, Humidity: 45%, Wind: 10 km/h, Rain probability: 5%, UV Index: 7.0",
        diagnosed_at=datetime.now(timezone.utc),
        original_image_path=str(image_path),
        heatmap_image_path=str(heatmap_path),
        report_verification_url="https://agriguard.ai/api/v1/reports/12345678-1234-1234-1234-123456789012",
    )


class TestPdfGeneration:
    def test_generates_a_valid_pdf_file(self, sample_report_data, tmp_path):
        output_path = tmp_path / "report.pdf"
        generator = PdfReportGenerator()

        result_path = generator.generate(sample_report_data, str(output_path))

        assert Path(result_path).exists()
        assert Path(result_path).stat().st_size > 1000  # a real multi-section PDF, not an empty stub

        with open(result_path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-", "output must be a genuine PDF file (correct magic bytes)"

    def test_generation_succeeds_without_a_heatmap_image(self, sample_report_data, tmp_path):
        sample_report_data.heatmap_image_path = None
        output_path = tmp_path / "report_no_heatmap.pdf"
        generator = PdfReportGenerator()

        result_path = generator.generate(sample_report_data, str(output_path))
        assert Path(result_path).exists()

    def test_generation_succeeds_with_missing_recovery_fields(self, sample_report_data, tmp_path):
        # FR-RESULT-2: recovery probability/time are allowed to be entirely absent;
        # the PDF must still render cleanly without them (ReportData simply doesn't
        # carry those fields — ensuring the generator never assumes their presence).
        output_path = tmp_path / "report_no_recovery.pdf"
        generator = PdfReportGenerator()
        result_path = generator.generate(sample_report_data, str(output_path))
        assert Path(result_path).exists()

    def test_generation_handles_missing_biological_treatment_gracefully(self, sample_report_data, tmp_path):
        assert sample_report_data.biological_treatment is None
        output_path = tmp_path / "report_no_bio.pdf"
        generator = PdfReportGenerator()
        result_path = generator.generate(sample_report_data, str(output_path))
        assert Path(result_path).exists()
