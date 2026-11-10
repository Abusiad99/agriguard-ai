"""
Integration tests for POST /api/v1/scans and GET /api/v1/diagnoses/{id} — FR-SCAN,
FR-AI, using the `_FakeInferenceService` from conftest.py so no trained model weights
are required.

NOT EXECUTABLE IN THIS SANDBOX (see test_auth_api.py header for the full dependency
list). Syntax-checked; logically reviewed against
docs/02-system-design/13-api-specification.md §3 and
docs/02-system-design/07a-sequence-scan-plant.mermaid.
"""
from __future__ import annotations

import io

from PIL import Image

from tests.conftest import make_auth_header


def _image_file():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


class TestCreateScan:
    def test_scan_with_valid_image_returns_completed_diagnosis(self, client):
        headers = make_auth_header(client, email="scanner@example.com")
        resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        assert body["plant"]["name"] == "tomato"
        assert body["confidence_score"] == 91.5

    def test_scan_without_auth_returns_401(self, client):
        resp = client.post("/api/v1/scans", files={"image": _image_file()})
        assert resp.status_code == 401

    def test_scan_endpoint_runs_off_the_event_loop(self):
        """The scan pipeline is blocking; as an `async def` it would stall every other
        request on the worker. A plain `def` makes FastAPI run it in its threadpool."""
        import inspect

        from app.interface.api.v1.scans_router import create_scan

        assert not inspect.iscoroutinefunction(create_scan)

    def test_disease_missing_from_knowledge_base_is_not_reported_healthy(self, client):
        # The fake model predicts tomato___early_blight; the KB is empty in tests.
        headers = make_auth_header(client, email="unlisted@example.com")
        resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        assert resp.status_code == 201
        body = resp.json()
        assert body["disease"] is not None
        assert body["disease"]["name"] == "Early blight"
        assert body["treatment"] is None

        history = client.get("/api/v1/diagnoses", headers=headers).json()
        assert history["items"][0]["disease"] == "Early blight"

    def test_referral_only_chemical_instructions_are_withheld(self, client, db_session):
        from app.domain.entities.disease import Disease, Treatment, TreatmentCategory
        from app.infrastructure.repositories.knowledge_base_repository import (
            SqlAlchemyDiseaseRepository,
            SqlAlchemyPlantRepository,
            SqlAlchemyTreatmentRepository,
        )

        plant = SqlAlchemyPlantRepository(db_session).get_or_create("tomato")
        disease = SqlAlchemyDiseaseRepository(db_session).create_version(Disease(
            id=None, plant_id=plant.id, name="early_blight", disease_type="fungal",
            description="A fungal disease.", symptoms=[], causes=[],
        ))
        SqlAlchemyTreatmentRepository(db_session).create_version(Treatment(
            id=None, disease_id=disease.id, category=TreatmentCategory.CHEMICAL,
            instructions="Apply 50ml/L of ProductX twice weekly.", authority_referral_only=True,
        ))

        headers = make_auth_header(client, email="referral@example.com")
        resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        assert resp.status_code == 201
        chemical = resp.json()["treatment"]["chemical"]["instructions"]
        assert "ProductX" not in chemical
        assert "consult your local agricultural authority" in chemical.lower()

    def test_scan_with_invalid_image_returns_422(self, client):
        headers = make_auth_header(client, email="badimg@example.com")
        resp = client.post(
            "/api/v1/scans", headers=headers,
            files={"image": ("not_an_image.jpg", io.BytesIO(b"garbage data"), "image/jpeg")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_IMAGE"

    def test_decompression_bomb_is_rejected_not_a_server_error(self, client):
        """A few-KB PNG can declare hundreds of megapixels. Above Pillow's limit it raised
        an unhandled DecompressionBombError (500); just above MAX_IMAGE_PIXELS it was only a
        warning and the full image was decoded and converted."""
        headers = make_auth_header(client, email="bomb@example.com")
        for width, height in ((20000, 20000), (10000, 9000)):  # 2x over the limit / just over it
            buf = io.BytesIO()
            Image.new("1", (width, height), 0).save(buf, format="PNG")
            assert buf.tell() < 200_000  # tiny upload, well under the size limit
            buf.seek(0)
            resp = client.post("/api/v1/scans", headers=headers, files={"image": ("leaf.png", buf, "image/png")})
            assert resp.status_code == 422, resp.text
            assert resp.json()["error"]["code"] == "INVALID_IMAGE"
        assert client.get("/api/v1/diagnoses", headers=headers).json()["total"] == 0


class TestDiagnosisOwnership:
    def test_owner_can_retrieve_own_diagnosis(self, client):
        headers = make_auth_header(client, email="owner@example.com")
        create_resp = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        diagnosis_id = create_resp.json()["diagnosis_id"]

        get_resp = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=headers)
        assert get_resp.status_code == 200

    def test_other_user_cannot_retrieve_someone_elses_diagnosis(self, client):
        owner_headers = make_auth_header(client, email="owner2@example.com")
        create_resp = client.post("/api/v1/scans", headers=owner_headers, files={"image": _image_file()})
        diagnosis_id = create_resp.json()["diagnosis_id"]

        other_headers = make_auth_header(client, email="intruder@example.com")
        get_resp = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=other_headers)
        assert get_resp.status_code == 403
        assert get_resp.json()["error"]["code"] == "FORBIDDEN"

    def test_nonexistent_diagnosis_returns_404(self, client):
        headers = make_auth_header(client, email="notfound@example.com")
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/api/v1/diagnoses/{fake_id}", headers=headers)
        assert resp.status_code == 404


class TestDiagnosisHistory:
    def test_list_diagnoses_returns_paginated_results(self, client):
        headers = make_auth_header(client, email="history@example.com")
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})

        resp = client.get("/api/v1/diagnoses", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_history_items_carry_names_not_ids(self, client):
        headers = make_auth_header(client, email="names@example.com")
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})

        item = client.get("/api/v1/diagnoses", headers=headers).json()["items"][0]
        assert item["plant"] == "tomato"
        assert item["disease"] == "Early blight"

    def test_date_to_includes_scans_made_on_that_day(self, client):
        from datetime import datetime, timezone

        headers = make_auth_header(client, email="dates@example.com")
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})

        today = datetime.now(timezone.utc).date().isoformat()
        resp = client.get("/api/v1/diagnoses", headers=headers, params={"date_from": today, "date_to": today})
        assert resp.json()["total"] == 1

    def test_invalid_pagination_is_rejected_not_a_server_error(self, client):
        # The app maps request validation errors to 400 VALIDATION_ERROR (see
        # exception_middleware.py); before the Query(ge=1) bounds these were 500s.
        headers = make_auth_header(client, email="pages@example.com")
        for params in ({"page_size": 0}, {"page": 0}, {"page_size": -5}):
            resp = client.get("/api/v1/diagnoses", headers=headers, params=params)
            assert resp.status_code == 400, params
            assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


class TestStoragePublicity:
    def test_scan_images_are_served_but_reports_are_not(self, client):
        headers = make_auth_header(client, email="storage@example.com")
        scan = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()}).json()

        # Images are still public by URL (the <img> tags can't send a bearer token)...
        assert client.get(scan["roi_image_url"]).status_code == 200
        # ...but PDF reports are only available through the authenticated endpoint.
        assert client.get("/storage/reports/anything.pdf").status_code == 404
        assert client.get(scan["report_url"]).status_code == 401
        assert client.get(scan["report_url"], headers=headers).status_code == 200
