"""Deployment safety of the settings: no published/short JWT secret in production, and the
configs/ folder is found both natively and in the Docker image layout."""
from __future__ import annotations

import pytest

from app.core.config import DEFAULT_JWT_SECRET, Settings, find_configs_dir, production_config_problems


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_production_refuses_the_default_or_a_short_jwt_secret():
    assert production_config_problems(_settings(app_env="production", jwt_secret_key=DEFAULT_JWT_SECRET))
    assert production_config_problems(_settings(app_env="production", jwt_secret_key="too-short"))
    assert production_config_problems(_settings(app_env="production", jwt_secret_key="r" * 48)) == []
    # development and staging keep working with the example value
    assert production_config_problems(_settings(app_env="development", jwt_secret_key=DEFAULT_JWT_SECRET)) == []


def test_app_does_not_start_with_an_insecure_production_secret(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main.settings, "jwt_secret_key", DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        with TestClient(main.app):
            pass


def test_configs_dir_is_found_natively():
    from app.core.config import CONFIGS_DIR

    assert (CONFIGS_DIR / "reports" / "rules.json").is_file()
    assert (CONFIGS_DIR / "reports" / "references.json").is_file()


def test_configs_dir_is_found_in_the_docker_image_layout(tmp_path):
    """docker/backend.Dockerfile copies backend/app to /app/app and configs/ to /app/configs."""
    (tmp_path / "configs" / "reports").mkdir(parents=True)
    module = tmp_path / "app" / "core" / "config.py"
    module.parent.mkdir(parents=True)
    module.touch()
    assert find_configs_dir(module) == tmp_path.resolve() / "configs"


def test_backend_image_copies_the_configs_folder():
    from app.core.config import CONFIGS_DIR

    dockerfile = (CONFIGS_DIR.parent / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "COPY configs/ /app/configs/" in dockerfile
