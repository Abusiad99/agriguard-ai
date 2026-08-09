"""
Integration tests for role-based authorization — BR3 (admin-only routes), BR4
(agronomist/admin knowledge-base edit routes). Since registration always creates a
`farmer` role account (FR-AUTH-1), these tests promote a user's role directly via the
DB session fixture to simulate agronomist/admin accounts, which mirrors how such
accounts are actually provisioned in production (UC-11: an existing admin promotes a
user — there is intentionally no public "become an admin" endpoint).

NOT EXECUTABLE IN THIS SANDBOX (see test_auth_api.py header). Syntax-checked;
logically reviewed against BR3/BR4 and every `require_roles(...)` dependency usage
across app/interface/api/v1/*.
"""
from __future__ import annotations

from app.infrastructure.db.models.user_model import UserModel
from tests.conftest import make_auth_header


def _promote_user(db_session, email: str, role: str):
    user = db_session.query(UserModel).filter(UserModel.email == email).one()
    user.role = role
    db_session.commit()


class TestAdminOnlyRoutes:
    def test_farmer_cannot_list_users(self, client):
        headers = make_auth_header(client, email="farmer1@example.com")
        resp = client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    def test_admin_can_list_users(self, client, db_session):
        headers = make_auth_header(client, email="admin1@example.com")
        _promote_user(db_session, "admin1@example.com", "admin")

        resp = client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200

    def test_farmer_cannot_export_reports(self, client):
        headers = make_auth_header(client, email="farmer2@example.com")
        resp = client.get("/api/v1/admin/reports/export", headers=headers)
        assert resp.status_code == 403

    def test_admin_cannot_demote_own_account(self, client, db_session):
        headers = make_auth_header(client, email="admin2@example.com")
        _promote_user(db_session, "admin2@example.com", "admin")

        me_resp = client.get("/api/v1/admin/users", headers=headers)
        my_id = next(u["id"] for u in me_resp.json()["items"] if u["email"] == "admin2@example.com")

        resp = client.patch(f"/api/v1/admin/users/{my_id}", json={"role": "farmer"}, headers=headers)
        assert resp.status_code == 400


class TestKnowledgeBaseEditRoutes:
    def test_farmer_cannot_create_disease(self, client):
        headers = make_auth_header(client, email="farmer3@example.com")
        resp = client.post("/api/v1/diseases", headers=headers, json={
            "plant_canonical_name": "tomato", "name": "Early Blight", "description": "desc",
        })
        assert resp.status_code == 403

    def test_agronomist_can_create_disease(self, client, db_session):
        headers = make_auth_header(client, email="agro1@example.com")
        _promote_user(db_session, "agro1@example.com", "agronomist")

        resp = client.post("/api/v1/diseases", headers=headers, json={
            "plant_canonical_name": "tomato", "name": "Early Blight", "description": "A fungal disease.",
        })
        assert resp.status_code == 201

    def test_farmer_cannot_create_treatment(self, client):
        headers = make_auth_header(client, email="farmer4@example.com")
        resp = client.post("/api/v1/treatments", headers=headers, json={
            "disease_id": "00000000-0000-0000-0000-000000000000",
            "category": "organic", "instructions": "neem oil",
        })
        assert resp.status_code == 403

    def test_chemical_treatment_without_citation_returns_422(self, client, db_session):
        headers = make_auth_header(client, email="agro2@example.com")
        _promote_user(db_session, "agro2@example.com", "agronomist")

        disease_resp = client.post("/api/v1/diseases", headers=headers, json={
            "plant_canonical_name": "tomato", "name": "Late Blight", "description": "desc",
        })
        disease_id = disease_resp.json()["id"]

        resp = client.post("/api/v1/treatments", headers=headers, json={
            "disease_id": disease_id, "category": "chemical", "instructions": "spray fungicide",
        })
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "DOSAGE_SOURCE_REQUIRED"


class TestDashboardSystemRoute:
    def test_farmer_cannot_access_system_dashboard(self, client):
        headers = make_auth_header(client, email="farmer5@example.com")
        resp = client.get("/api/v1/dashboard/system", headers=headers)
        assert resp.status_code == 403

    def test_admin_can_access_system_dashboard(self, client, db_session):
        headers = make_auth_header(client, email="admin3@example.com")
        _promote_user(db_session, "admin3@example.com", "admin")
        resp = client.get("/api/v1/dashboard/system", headers=headers)
        assert resp.status_code == 200
