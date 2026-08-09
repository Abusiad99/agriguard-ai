"""
AuthService — orchestrates FR-AUTH-1..5 use cases (UC-01, UC-02). Depends only on
domain repository interfaces + security interfaces, never on FastAPI or SQLAlchemy
directly (Clean Architecture application layer).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import AuthenticationError, ConflictError, TokenExpiredOrInvalidError, ValidationError
from app.domain.entities.user import Locale, User, UserRole
from app.domain.repositories.interfaces import IRefreshTokenRepository, IUserRepository
from app.infrastructure.security.jwt_service import JwtService, TokenPair
from app.infrastructure.security.password_hasher import PasswordHasher
from app.infrastructure.security.token_hasher import hash_token

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class AuthService:
    def __init__(self, user_repo: IUserRepository, refresh_token_repo: IRefreshTokenRepository,
                 password_hasher: PasswordHasher, jwt_service: JwtService):
        self.user_repo = user_repo
        self.refresh_token_repo = refresh_token_repo
        self.password_hasher = password_hasher
        self.jwt_service = jwt_service

    def register(self, email: str, password: str, full_name: str) -> User:
        self._validate_registration(email, password, full_name)

        if self.user_repo.get_by_email(email):
            raise ConflictError("An account with this email already exists.", details=[
                {"field": "email", "issue": "already exists"}
            ])

        user = User(
            id=None, email=email.lower().strip(), password_hash=self.password_hasher.hash(password),
            full_name=full_name.strip(), role=UserRole.FARMER, is_active=True, preferred_locale=Locale.EN,
        )
        return self.user_repo.create(user)

    def _validate_registration(self, email: str, password: str, full_name: str) -> None:
        details = []
        if not email or not _EMAIL_RE.match(email):
            details.append({"field": "email", "issue": "must be a valid email address"})
        if not password or len(password) < 8:
            details.append({"field": "password", "issue": "must be at least 8 characters"})
        elif not (any(c.isupper() for c in password) and any(c.isdigit() for c in password)):
            details.append({"field": "password", "issue": "must contain an uppercase letter and a digit"})
        if not full_name or len(full_name.strip()) < 2:
            details.append({"field": "full_name", "issue": "must be provided"})
        if details:
            raise ValidationError("Registration validation failed.", details=details)

    def login(self, email: str, password: str) -> TokenPair:
        user = self.user_repo.get_by_email(email)
        # Constant-shape response regardless of which check fails (no user enumeration).
        if user is None or not user.is_active or not self.password_hasher.verify(password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")

        return self._issue_tokens(user)

    def _issue_tokens(self, user: User) -> TokenPair:
        access_token = self.jwt_service.create_access_token(user.id, user.role.value)
        refresh_token = self.jwt_service.generate_refresh_token()
        self.refresh_token_repo.store(
            user_id=user.id, token_hash=hash_token(refresh_token),
            expires_at=self.jwt_service.refresh_token_expiry(),
        )
        return TokenPair(
            access_token=access_token, refresh_token=refresh_token,
            expires_in=self.jwt_service.access_token_ttl_seconds(),
        )

    def refresh(self, raw_refresh_token: str) -> TokenPair:
        token_hash = hash_token(raw_refresh_token)
        user_id = self.refresh_token_repo.is_valid(token_hash)
        if user_id is None:
            raise TokenExpiredOrInvalidError("Refresh token is invalid, expired, or revoked.")

        user = self.user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise TokenExpiredOrInvalidError("Associated account is no longer active.")

        # Rotation: revoke the used token, issue a new pair (NFR-SEC-3).
        self.refresh_token_repo.revoke(token_hash)
        return self._issue_tokens(user)

    def logout(self, raw_refresh_token: str) -> None:
        self.refresh_token_repo.revoke(hash_token(raw_refresh_token))

    def get_current_user(self, user_id: UUID) -> User:
        user = self.user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account not found or inactive.")
        return user
