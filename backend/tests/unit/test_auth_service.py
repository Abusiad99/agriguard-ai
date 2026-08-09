"""
Unit tests for AuthService (FR-AUTH-1..5), using in-memory fake repositories that
implement the domain repository interfaces directly — no database, no mocking
framework magic, just plain Python objects satisfying the same contract the real
SQLAlchemy repositories satisfy (this is exactly what Dependency Inversion buys us:
the application layer cannot tell the difference).

NOTE ON EXECUTABILITY: AuthService imports PasswordHasher (passlib) and JwtService
(PyJWT) and app.core.config (pydantic-settings). In this development sandbox, passlib
and pydantic-settings are not installed and there is no network access to install
them, so this file could not be executed here. It is syntax-checked
(`python -m py_compile`) and logically reviewed. It is expected to run cleanly once
`pip install -r backend/requirements.txt` succeeds in an environment with network
access, matching the pattern already established for tests/unit/test_domain_entities.py,
which IS executed in this sandbox because it has zero third-party dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.services.auth_service import AuthService
from app.core.exceptions import AuthenticationError, ConflictError, TokenExpiredOrInvalidError, ValidationError
from app.domain.entities.user import Locale, User, UserRole
from app.infrastructure.security.jwt_service import JwtService
from app.infrastructure.security.password_hasher import PasswordHasher
from app.infrastructure.security.token_hasher import hash_token


class FakeUserRepository:
    def __init__(self):
        self._by_id = {}
        self._by_email = {}

    def create(self, user: User) -> User:
        user.id = uuid.uuid4()
        self._by_id[user.id] = user
        self._by_email[user.email.lower()] = user
        return user

    def get_by_id(self, user_id):
        return self._by_id.get(user_id)

    def get_by_email(self, email):
        return self._by_email.get(email.lower())

    def update(self, user):
        self._by_id[user.id] = user
        return user

    def list(self, role, is_active, search, page, page_size):
        items = list(self._by_id.values())
        return items, len(items)


class FakeRefreshTokenRepository:
    def __init__(self):
        self._tokens = {}  # token_hash -> (user_id, expires_at, revoked)

    def store(self, user_id, token_hash, expires_at):
        self._tokens[token_hash] = [user_id, expires_at, False]

    def is_valid(self, token_hash):
        entry = self._tokens.get(token_hash)
        if entry is None:
            return None
        user_id, expires_at, revoked = entry
        if revoked or expires_at < datetime.now(timezone.utc):
            return None
        return user_id

    def revoke(self, token_hash):
        if token_hash in self._tokens:
            self._tokens[token_hash][2] = True

    def revoke_all_for_user(self, user_id):
        for entry in self._tokens.values():
            if entry[0] == user_id:
                entry[2] = True


@pytest.fixture()
def auth_service():
    return AuthService(FakeUserRepository(), FakeRefreshTokenRepository(), PasswordHasher(), JwtService())


class TestRegistration:
    def test_register_creates_user_with_farmer_role(self, auth_service):
        user = auth_service.register("farmer@example.com", "S3curePass1", "Youssef Amrani")
        assert user.role == UserRole.FARMER
        assert user.email == "farmer@example.com"
        assert user.password_hash != "S3curePass1"  # never store plaintext (NFR-SEC-2)

    def test_register_rejects_duplicate_email(self, auth_service):
        auth_service.register("dup@example.com", "S3curePass1", "First User")
        with pytest.raises(ConflictError):
            auth_service.register("dup@example.com", "AnotherPass1", "Second User")

    def test_register_rejects_weak_password(self, auth_service):
        with pytest.raises(ValidationError):
            auth_service.register("weak@example.com", "weak", "Weak Password User")

    def test_register_rejects_invalid_email(self, auth_service):
        with pytest.raises(ValidationError):
            auth_service.register("not-an-email", "S3curePass1", "Bad Email User")


class TestLogin:
    def test_login_with_correct_credentials_returns_tokens(self, auth_service):
        auth_service.register("login@example.com", "S3curePass1", "Login User")
        tokens = auth_service.login("login@example.com", "S3curePass1")
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.expires_in > 0

    def test_login_with_wrong_password_raises_authentication_error(self, auth_service):
        auth_service.register("login2@example.com", "S3curePass1", "Login User 2")
        with pytest.raises(AuthenticationError):
            auth_service.login("login2@example.com", "WrongPassword1")

    def test_login_with_unknown_email_raises_authentication_error_not_not_found(self, auth_service):
        # No user enumeration: unknown email and wrong password must look identical.
        with pytest.raises(AuthenticationError):
            auth_service.login("nobody@example.com", "SomePassword1")

    def test_login_with_inactive_account_fails(self, auth_service):
        user = auth_service.register("inactive@example.com", "S3curePass1", "Inactive User")
        user.is_active = False
        auth_service.user_repo.update(user)
        with pytest.raises(AuthenticationError):
            auth_service.login("inactive@example.com", "S3curePass1")


class TestTokenRefresh:
    def test_refresh_rotates_token_and_revokes_old_one(self, auth_service):
        auth_service.register("refresh@example.com", "S3curePass1", "Refresh User")
        tokens = auth_service.login("refresh@example.com", "S3curePass1")

        new_tokens = auth_service.refresh(tokens.refresh_token)
        assert new_tokens.refresh_token != tokens.refresh_token

        # Old refresh token must now be rejected (rotation, NFR-SEC-3).
        with pytest.raises(TokenExpiredOrInvalidError):
            auth_service.refresh(tokens.refresh_token)

    def test_refresh_with_garbage_token_fails(self, auth_service):
        with pytest.raises(TokenExpiredOrInvalidError):
            auth_service.refresh("not-a-real-token")

    def test_logout_revokes_refresh_token(self, auth_service):
        auth_service.register("logout@example.com", "S3curePass1", "Logout User")
        tokens = auth_service.login("logout@example.com", "S3curePass1")
        auth_service.logout(tokens.refresh_token)
        with pytest.raises(TokenExpiredOrInvalidError):
            auth_service.refresh(tokens.refresh_token)
