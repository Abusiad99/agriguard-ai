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

    def test_scan_with_invalid_image_returns_422(self, client):
        headers = make_auth_header(client, email="badimg@example.com")
        resp = client.post(
            "/api/v1/scans", headers=headers,
            files={"image": ("not_an_image.jpg", io.BytesIO(b"garbage data"), "image/jpeg")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_IMAGE"


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
