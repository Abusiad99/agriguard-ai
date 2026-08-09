"""
Integration tests for /api/v1/dashboard/* — FR-DASH-1..3.

NOT EXECUTABLE IN THIS SANDBOX (see test_auth_api.py header). Syntax-checked;
logically reviewed against app/application/services/dashboard_admin_service.py and
app/infrastructure/repositories/diagnosis_repository.py's dashboard_summary().
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


class TestMyDashboard:
    def test_dashboard_reflects_scan_count(self, client):
        headers = make_auth_header(client, email="dashuser@example.com")
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})
        client.post("/api/v1/scans", headers=headers, files={"image": _image_file()})

        resp = client.get("/api/v1/dashboard/me", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_scans"] == 2
        assert "palm_disease_stats" in body
        assert "most_common_diseases" in body
        assert "monthly_trend" in body

    def test_dashboard_is_scoped_to_the_requesting_user(self, client):
        headers_a = make_auth_header(client, email="dashA@example.com")
        headers_b = make_auth_header(client, email="dashB@example.com")

        client.post("/api/v1/scans", headers=headers_a, files={"image": _image_file()})

        resp_b = client.get("/api/v1/dashboard/me", headers=headers_b)
        assert resp_b.json()["total_scans"] == 0, "user B must not see user A's scans"

        resp_a = client.get("/api/v1/dashboard/me", headers=headers_a)
        assert resp_a.json()["total_scans"] == 1

    def test_dashboard_requires_authentication(self, client):
        resp = client.get("/api/v1/dashboard/me")
        assert resp.status_code == 401
