"""Production must not start with the placeholder JWT secret (it also signs media URLs)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_production_refuses_placeholder_secret(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret_key", "CHANGE_ME_IN_PRODUCTION_ENV")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        with TestClient(app):
            pass
