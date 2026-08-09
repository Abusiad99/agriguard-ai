"""SHA-256 hashing for opaque tokens (refresh tokens, password reset tokens) before
they are persisted — the DB never stores a usable token in plaintext, only its hash,
so a database read alone cannot be used to forge a session (defense in depth for
NFR-SEC-3)."""
from __future__ import annotations

import hashlib


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
