"""Password hashing (NFR-SEC-2: bcrypt with per-user salt, via passlib)."""
from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PasswordHasher:
    def hash(self, plain_password: str) -> str:
        return _pwd_context.hash(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return _pwd_context.verify(plain_password, password_hash)
