"""Disease localization in the scan workflow + model registry API: classification keeps
working without (or despite) segmentation; artifacts are owner-only; no paths leak."""
from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from tests.conftest import make_auth_header


def _image(size=64):
    buf = io.BytesIO()
    img = Image.new("RGB", (size, size), (190, 190, 190))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([6, 12, 58, 52], fill=(50, 140, 60))
    d.ellipse([28, 26, 36, 34], fill=(120, 70, 30))
    img.save(buf, format="PNG")
    buf.seek(0)
    return ("leaf.png", buf, "image/png")


def test_models_endpoint_lists_every_task_without_paths(client):
    headers = make_auth_header(client, email="m1@example.com")
    cards = client.get("/api/v1/models", headers=headers).json()
    assert {c["task"] for c in cards} == {"classification", "segmentation", "outbreak"}
    assert all(c["readiness"] == "dataset_unavailable" for c in cards)
    assert "run_dir" not in json.dumps(cards) and "artifacts" not in json.dumps(cards).lower()
    assert client.get("/api/v1/models/segmentation", headers=headers).json()["task"] == "segmentation"
    assert client.get("/api/v1/models/nope", headers=headers).status_code == 404
    assert client.get("/api/v1/models").status_code == 401


def test_scan_without_segmentation_model_still_diagnoses(client):
    headers = make_auth_header(client, email="s1@example.com")
    body = client.post("/api/v1/scans", headers=headers, files={"image": _image()}).json()
    assert body["status"] == "completed" and body["confidence_score"] == 91.5
    assert body["segmentation"]["status"] == "dataset_unavailable" and body["segmentation"]["artifacts"] is None
    assert body["severity_method"] == "explainability_heatmap"  # Grad-CAM numbers are labeled as such
    assert body["image_quality"]["issues"]  # 64 px test image is flagged too_small


def test_healthy_prediction_is_not_labelled_as_a_heatmap_estimate(client, db_session):
    """Healthy predictions skip Grad-CAM (no heatmap is made), so their area values must
    not carry the "estimated from the attention heatmap" label."""
    import uuid

    from app.infrastructure.db.models.diagnosis_model import DiagnosisModel

    headers = make_auth_header(client, email="s-healthy@example.com")
    body = client.post("/api/v1/scans", headers=headers, files={"image": _image()}).json()
    row = db_session.get(DiagnosisModel, uuid.UUID(body["diagnosis_id"]))
    # SYNTHETIC: what the pipeline stores for a healthy prediction
    row.predicted_condition, row.severity_level, row.affected_area_pct, row.healthy_area_pct = "healthy", None, 0.0, 100.0
    row.heatmap_image_ref = None
    db_session.commit()
    healthy = client.get(f"/api/v1/diagnoses/{body['diagnosis_id']}", headers=headers).json()
    assert healthy["disease"] is None and healthy["severity_method"] is None


class TestWithSyntheticSegmentationModel:
    @pytest.fixture(autouse=True)
    def model(self, trained_segmentation_artifacts, monkeypatch):
        from ai.config import CONFIG
        monkeypatch.setattr(CONFIG.paths, "artifacts_dir", trained_segmentation_artifacts)

    def test_segmentation_result_and_private_artifacts(self, client):
        owner = make_auth_header(client, email="s2@example.com")
        other = make_auth_header(client, email="s3@example.com")
        body = client.post("/api/v1/scans", headers=owner, files={"image": _image()}).json()
        seg = body["segmentation"]
        assert seg["status"] == "ok" and seg["model_version"]
        assert [c["kind"] for c in seg["classes"]] == ["background", "leaf", "disease"]
        if seg["affected_area_pct"] is not None:
            assert seg["area_basis"] == "plant_pixels" and seg["plant_pixels"] > 0
        else:
            assert seg["area_unavailable_reason"]
        for name, url in seg["artifacts"].items():
            ok = client.get(url, headers=owner)
            assert ok.status_code == 200 and ok.headers["content-type"] == "image/png", name
            assert client.get(url, headers=other).status_code == 403
            assert client.get(url).status_code == 401
        assert client.get(f"/api/v1/diagnoses/{body['diagnosis_id']}/segmentation/secrets", headers=owner).status_code == 404
        # not reachable through the public storage mounts
        assert client.get("/storage/segmentations/x/mask.png").status_code == 404

    def test_segmentation_failure_does_not_fail_the_scan(self, client, monkeypatch):
        from app.interface.api.v1 import dependencies

        def boom(fn):
            raise RuntimeError("GPU on fire")
        monkeypatch.setattr(dependencies._segmentation_client, "call", boom)
        headers = make_auth_header(client, email="s4@example.com")
        resp = client.post("/api/v1/scans", headers=headers, files={"image": _image()})
        assert resp.status_code == 201
        assert resp.json()["segmentation"]["status"] == "failed"
        assert resp.json()["disease"] is not None
