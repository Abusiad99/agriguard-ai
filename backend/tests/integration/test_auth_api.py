"""
Integration tests for /api/v1/auth/* — FR-AUTH-1..5, exercised through the real
FastAPI app + SQLite DB + real password hashing/JWT (via the `client` fixture in
conftest.py).

NOT EXECUTABLE IN THIS SANDBOX: requires fastapi, sqlalchemy, pydantic, passlib —
none installed here, no network access to install them. Syntax-checked; logically
reviewed against docs/02-system-design/13-api-specification.md §2.
"""
from __future__ import annotations

from tests.conftest import make_auth_header


class TestRegister:
    def test_register_returns_201_with_farmer_role(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "new@example.com", "password": "S3curePass1", "full_name": "New User",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "farmer"
        assert body["email"] == "new@example.com"

    def test_register_duplicate_email_returns_409(self, client):
        payload = {"email": "dup@example.com", "password": "S3curePass1", "full_name": "Dup User"}
        client.post("/api/v1/auth/register", json=payload)
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_register_weak_password_returns_400(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "weak@example.com", "password": "weak", "full_name": "Weak User",
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


class TestLogin:
    def test_login_success_returns_tokens(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "login@example.com", "password": "S3curePass1", "full_name": "Login User",
        })
        resp = client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "S3curePass1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body and "refresh_token" in body
        assert body["user"]["role"] == "farmer"

    def test_login_wrong_password_returns_401(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "login2@example.com", "password": "S3curePass1", "full_name": "Login User 2",
        })
        resp = client.post("/api/v1/auth/login", json={"email": "login2@example.com", "password": "WrongPass1"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


class TestRefreshAndLogout:
    def test_refresh_rotates_tokens(self, client):
        client.post("/api/v1/auth/register", json={
            "email": "refresh@example.com", "password": "S3curePass1", "full_name": "Refresh User",
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "refresh@example.com", "password": "S3curePass1",
        })
        old_refresh = login_resp.json()["refresh_token"]

        refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert refresh_resp.status_code == 200
        assert refresh_resp.json()["refresh_token"] != old_refresh

        # Old token must now be rejected.
        reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert reuse_resp.status_code == 401

    def test_logout_requires_authentication(self, client):
        resp = client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
        assert resp.status_code == 401

    def test_logout_then_refresh_fails(self, client):
        headers = make_auth_header(client, email="logout@example.com")
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "logout@example.com", "password": "Str0ngPass!",
        })
        refresh_token = login_resp.json()["refresh_token"]

        logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token}, headers=headers)
        assert logout_resp.status_code == 204

        refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_resp.status_code == 401
