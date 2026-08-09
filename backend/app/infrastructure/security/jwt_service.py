"""
JWT service (FR-AUTH-2, NFR-SEC-3). Issues short-lived access tokens (containing
`sub`=user id, `role`, `exp`, `iat`) and opaque refresh tokens (random strings, hashed
before storage by the repository layer — this module never persists tokens itself).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app.core.config import get_settings

settings = get_settings()


class TokenError(Exception):
    pass


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


class JwtService:
    def create_access_token(self, user_id: UUID, role: str) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {"sub": str(user_id), "role": role, "iat": int(now.timestamp()), "exp": expire}
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> dict:
        try:
            return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Access token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Invalid access token.") from exc

    def generate_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    def refresh_token_expiry(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    def access_token_ttl_seconds(self) -> int:
        return settings.access_token_expire_minutes * 60
