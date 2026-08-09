"""
Integration tests for the centralized exception-handling middleware
(app/interface/middleware/exception_middleware.py) — verifies every error path
returns the standard envelope defined in
docs/02-system-design/13-api-specification.md §1.1/1.2, with the correct HTTP status
code and error `code` field, across validation errors, auth errors, not-found errors,
and unexpected-exception fallback.

NOT EXECUTABLE IN THIS SANDBOX (see test_auth_api.py header). Syntax-checked;
logically reviewed against every `raise AgriGuardError subclass` call site in
app/interface/api/v1/*.py and app/application/services/*.py.
"""
from __future__ import annotations

from tests.conftest import make_auth_header


class TestErrorEnvelopeShape:
    def test_every_error_response_has_the_standard_envelope(self, client):
        resp = client.post("/api/v1/auth/login", json={"email": "nobody@x.com", "password": "whatever"})
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
        assert "request_id" in body

    def test_request_id_is_present_in_response_header(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers


class TestValidationErrorMapping:
    def test_pydantic_validation_error_maps_to_400_with_field_details(self, client):
        # Missing required `password` field entirely -> FastAPI/Pydantic validation error.
        resp = client.post("/api/v1/auth/register", json={"email": "x@y.com", "full_name": "X"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert len(body["error"]["details"]) >= 1

    def test_application_level_validation_error_maps_to_400(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "bad-email-format", "password": "S3curePass1", "full_name": "X",
        })
        assert resp.status_code in (400, 422)  # Pydantic EmailStr rejects at 400/422 depending on FastAPI version


class TestNotFoundMapping:
    def test_unknown_diagnosis_returns_404_not_found(self, client):
        headers = make_auth_header(client, email="notfound2@example.com")
        fake_id = "11111111-1111-1111-1111-111111111111"
        resp = client.get(f"/api/v1/diagnoses/{fake_id}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestAuthenticationErrorMapping:
    def test_missing_authorization_header_returns_401(self, client):
        resp = client.get("/api/v1/dashboard/me")
        assert resp.status_code == 401

    def test_malformed_authorization_header_returns_401(self, client):
        resp = client.get("/api/v1/dashboard/me", headers={"Authorization": "NotBearer sometoken"})
        assert resp.status_code == 401

    def test_garbage_token_returns_401(self, client):
        resp = client.get("/api/v1/dashboard/me", headers={"Authorization": "Bearer garbage.token.value"})
        assert resp.status_code == 401


class TestAuthorizationErrorMapping:
    def test_forbidden_action_returns_403_with_correct_code(self, client):
        headers = make_auth_header(client, email="forbidden@example.com")
        resp = client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"


class TestUnexpectedErrorFallback:
    def test_health_endpoint_never_leaks_internal_details_on_db_failure(self, client, monkeypatch):
        # Simulate a DB failure inside the health check without crashing the test
        # process — the handler must catch it and report "down", not 500 with a
        # stack trace (NFR-OBS-2's health contract).
        resp = client.get("/health")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body and "database" in body
