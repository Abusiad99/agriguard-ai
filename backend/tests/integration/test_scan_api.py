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

from tests.conftest import make_auth_header, make_leaf_like_image_bytes


def _image_file():
    return ("leaf.jpg", io.BytesIO(make_leaf_like_image_bytes()), "image/jpeg")


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


def _set_fake_status(status: str):
    from app.infrastructure.external import ai_pipeline_client

    ai_pipeline_client.AiPipelineClient._service.decision_status = status


class TestReliabilityBehaviour:
    def test_unusable_photo_is_rejected_with_feedback_and_nothing_is_stored(self, client):
        headers = make_auth_header(client, email="dark@example.com")
        buf = io.BytesIO()
        Image.new("RGB", (400, 400), color=(3, 4, 2)).save(buf, format="JPEG")
        buf.seek(0)
        resp = client.post("/api/v1/scans", headers=headers, files={"image": ("dark.jpg", buf, "image/jpeg")})
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "rejected_image_quality"
        codes = {i["code"] for i in body["quality"]["issues"]}
        assert codes & {"no_detail", "too_dark"}
        assert all(i["hint"] for i in body["quality"]["issues"])
        assert client.get("/api/v1/diagnoses", headers=headers).json()["total"] == 0

    def test_tiny_image_is_rejected(self, client):
        headers = make_auth_header(client, email="tiny@example.com")
        resp = client.post("/api/v1/scans", headers=headers,
                           files={"image": ("t.jpg", io.BytesIO(make_leaf_like_image_bytes(size=64)), "image/jpeg")})
        assert resp.json()["status"] == "rejected_image_quality"

    def test_uncertain_result_is_saved_without_asserting_a_disease(self, client):
        _set_fake_status("uncertain")
        headers = make_auth_header(client, email="unsure@example.com")
        body = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()}).json()
        assert body["decision_status"] == "uncertain"
        assert body["disease"] is None and body["treatment"] is None
        assert body["low_confidence_flag"] is True
        assert body["differential"]["expert_review_recommended"] is True
        assert "model_not_confident" in body["differential"]["expert_review_reasons"]
        assert len(body["differential"]["model_candidates"]) == 3
        assert body["ai_analysis"] is None  # Gemini explanation only for confident results
        assert body["recommendation"]["spraying_advice"] is None
        listed = client.get("/api/v1/diagnoses?decision_status=uncertain", headers=headers).json()
        assert listed["total"] == 1

    def test_inconclusive_result_names_no_condition(self, client):
        _set_fake_status("inconclusive")
        headers = make_auth_header(client, email="inconclusive@example.com")
        body = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()}).json()
        assert body["decision_status"] == "inconclusive"
        assert body["disease"] is None and body["predicted_label"] is None
        assert body["differential"]["model_candidates"] == []
        assert body["report_url"]  # a report is still produced, saying "inconclusive"

    def test_images_are_served_only_through_signed_urls(self, client):
        _set_fake_status("confident")
        headers = make_auth_header(client, email="media@example.com")
        body = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()}).json()
        url = body["original_image_url"]
        assert url.startswith("/api/v1/media/scans/") and "sig=" in url
        ok = client.get(url)
        assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
        tampered = url[:-4] + ("0000" if not url.endswith("0000") else "1111")
        assert client.get(tampered).status_code == 403
        assert client.get(url.split("?")[0]).status_code == 400  # missing signature
        ref = url.split("/media/")[1].split("?")[0]
        assert client.get(f"/storage/{ref}").status_code == 404  # public static mount removed

    def test_response_exposes_provenance(self, client):
        _set_fake_status("confident")
        headers = make_auth_header(client, email="prov@example.com")
        body = client.post("/api/v1/scans", headers=headers, files={"image": _image_file()}).json()
        assert body["model_version"] == "test-run:abc123" and body["pipeline_version"] == "2.0.0"
        assert body["decision"]["thresholds"]["source"] == "validation"
        assert body["explanation"]["method"] == "grad_cam"
        assert body["image_quality"]["status"] == "ok"
