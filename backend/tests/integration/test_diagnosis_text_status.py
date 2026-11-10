"""Status fields that let clients show fixed diagnosis notices in the reader's language
(knowledge_base_status, instructions_withheld, prevention_advice_codes). The English texts
stay in the response for older clients, and nothing about the diagnosis itself changes.
Uses the fake classifier from conftest.py (predicts tomato early blight, confidence 91.5);
knowledge-base rows are SYNTHETIC fixtures."""
from __future__ import annotations

import io

from PIL import Image

from app.application.services.guidance import GENERIC_PREVENTION_ADVICE, GENERIC_PREVENTION_CODES
from app.application.services.scan_service import UNLISTED_DISEASE_DESCRIPTION
from tests.conftest import make_auth_header

# The frontend translates these codes (frontend/src/i18n/{en,ar}.ts, result.genericPrevention).
FRONTEND_PREVENTION_CODES = ["irrigation_ventilation", "remove_infected_material", "rotation_sanitation"]


def _image_file():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


def _scan(client, email):
    headers = make_auth_header(client, email=email)
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    again = client.get(f"/api/v1/diagnoses/{body['diagnosis_id']}", headers=headers).json()
    return body, again


def test_condition_missing_from_the_knowledge_base_is_flagged_not_listed(client):
    created, fetched = _scan(client, "kb-unlisted@example.com")
    for body in (created, fetched):
        disease = body["disease"]
        assert disease["knowledge_base_status"] == "not_listed"
        # unchanged for older clients and for the diagnosis itself
        assert disease["description"] == UNLISTED_DISEASE_DESCRIPTION
        assert disease["name"] == "Early blight" and body["confidence_score"] == 91.5
        assert body["treatment"] is None
        assert body["prevention_advice"] == [] and body["prevention_advice_codes"] == []


def test_listed_condition_withheld_dosage_and_prevention_codes(client, db_session):
    from app.domain.entities.disease import Disease, Treatment, TreatmentCategory
    from app.infrastructure.repositories.knowledge_base_repository import (
        SqlAlchemyDiseaseRepository,
        SqlAlchemyPlantRepository,
        SqlAlchemyTreatmentRepository,
    )

    plant = SqlAlchemyPlantRepository(db_session).get_or_create("tomato")
    disease = SqlAlchemyDiseaseRepository(db_session).create_version(Disease(
        id=None, plant_id=plant.id, name="early_blight", disease_type="fungal",
        description="SYNTHETIC: a fungal disease.", symptoms=[], causes=[],
    ))
    treatments = SqlAlchemyTreatmentRepository(db_session)
    treatments.create_version(Treatment(
        id=None, disease_id=disease.id, category=TreatmentCategory.CHEMICAL,
        instructions="SYNTHETIC: apply ProductX.", authority_referral_only=True,
    ))
    treatments.create_version(Treatment(
        id=None, disease_id=disease.id, category=TreatmentCategory.ORGANIC,
        instructions="SYNTHETIC: remove infected leaves.",
    ))

    created, fetched = _scan(client, "kb-listed@example.com")
    for body in (created, fetched):
        assert body["disease"]["knowledge_base_status"] == "listed"
        assert body["disease"]["description"] == "SYNTHETIC: a fungal disease."
        chemical, organic = body["treatment"]["chemical"], body["treatment"]["organic"]
        assert chemical["instructions_withheld"] is True and "ProductX" not in chemical["instructions"]
        assert "consult your local agricultural authority" in chemical["instructions"].lower()
        assert organic["instructions_withheld"] is False
        assert organic["instructions"] == "SYNTHETIC: remove infected leaves."
        assert body["prevention_advice"] == list(GENERIC_PREVENTION_ADVICE)
        assert body["prevention_advice_codes"] == list(GENERIC_PREVENTION_CODES) == FRONTEND_PREVENTION_CODES


def test_knowledge_base_text_with_markup_characters_prints_in_the_scan_pdf(client, db_session):
    """The per-scan PDF used to pass knowledge-base text to ReportLab's markup parser as
    is: an "&" or "<" made the PDF (and with it the scan request) fail after the
    diagnosis was saved."""
    from pypdf import PdfReader

    from app.domain.entities.disease import Disease, Treatment, TreatmentCategory
    from app.infrastructure.repositories.knowledge_base_repository import (
        SqlAlchemyDiseaseRepository,
        SqlAlchemyPlantRepository,
        SqlAlchemyTreatmentRepository,
    )

    plant = SqlAlchemyPlantRepository(db_session).get_or_create("tomato")
    disease = SqlAlchemyDiseaseRepository(db_session).create_version(Disease(
        id=None, plant_id=plant.id, name="early_blight", disease_type="fungal",
        description="SYNTHETIC: spreads when leaves stay wet & warm; worse at pH < 6 <b>.", symptoms=[], causes=[],
    ))
    SqlAlchemyTreatmentRepository(db_session).create_version(Treatment(
        id=None, disease_id=disease.id, category=TreatmentCategory.ORGANIC,
        instructions="SYNTHETIC: remove leaves & stems <now>.",
    ))

    headers = make_auth_header(client, email="kb-markup@example.com")
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
    assert resp.status_code == 201, resp.text
    pdf = client.get(resp.json()["report_url"], headers=headers)
    assert pdf.status_code == 200
    text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf.content)).pages)
    flat = " ".join(text.split())
    assert "wet & warm; worse at pH < 6 <b>." in flat
    assert "remove leaves & stems <now>." in flat
