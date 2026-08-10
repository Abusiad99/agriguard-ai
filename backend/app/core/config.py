"""
Centralized configuration (requirement #10) for the AgriGuard AI backend.

All values are overridable via environment variables / a `.env` file (pydantic-settings).
Nothing below should ever be hardcoded elsewhere in `app/` — every module that needs a
setting imports `get_settings()` from here. NFR-MAINT-4.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "AgriGuard AI"
    app_env: str = Field(default="development")  # development | staging | production
    api_prefix: str = "/api/v1"
    debug: bool = Field(default=False)

    # --- Database (PostgreSQL) ---
    database_url: str = Field(
        default="postgresql+psycopg2://agriguard:agriguard@localhost:5432/agriguard",
        description="SQLAlchemy connection URL. Compose overrides via env var.",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    weather_cache_ttl_seconds: int = 3 * 60 * 60  # freshness window, BR7

    # --- JWT / Auth (FR-AUTH, NFR-SEC-3) ---
    jwt_secret_key: str = Field(default="CHANGE_ME_IN_PRODUCTION_ENV")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    password_reset_token_expire_minutes: int = 30

    # --- Rate limiting (NFR-SEC-5) ---
    rate_limit_auth_per_5min: int = 10
    rate_limit_scan_per_hour: int = 30
    rate_limit_default_per_5min: int = 300

    # --- File upload (FR-SCAN-1) ---
    max_upload_size_bytes: int = 15 * 1024 * 1024  # 15MB
    allowed_image_content_types: List[str] = ["image/jpeg", "image/png", "image/webp"]

    # --- Storage ---
    storage_backend: str = Field(default="local")  # local | s3
    local_storage_dir: str = Field(default="/app/storage")
    s3_bucket: str = Field(default="")
    s3_endpoint_url: str = Field(default="")
    s3_access_key: str = Field(default="")
    s3_secret_key: str = Field(default="")

    # --- AI Pipeline (ties to ai/ package config) ---
    ai_artifacts_dir: str = Field(default="/app/artifacts")
    ai_artifacts_run_dir: str = Field(default="", description="Explicit run dir override; empty = use latest trained run")

    # --- Weather API (FR-WEATHER) ---
    weather_api_provider: str = Field(default="open-meteo")  # requires no API key by default
    weather_api_key: str = Field(default="")
    weather_api_base_url: str = Field(default="https://api.open-meteo.com/v1/forecast")
    weather_request_timeout_seconds: float = 5.0

    # --- Gemini AI reasoning layer (optional multimodal explanation on top of the
    # existing CV diagnosis — see docs/GEMINI_INTEGRATION.md). Leaving
    # gemini_api_key empty disables the feature entirely; every other part of the
    # diagnosis pipeline is unaffected either way. ---
    gemini_api_key: str = Field(default="", description="Server-side only. Never exposed to the frontend.")
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_timeout_seconds: float = 20.0
    gemini_max_tool_calls: int = 6  # cap on automatic function-calling round-trips per analysis

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    # --- Email/SMTP (FR-AUTH-4) ---
    smtp_host: str = Field(default="")
    smtp_port: int = 587
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_address: str = Field(default="no-reply@agriguard.ai")
    smtp_use_tls: bool = True

    # --- CORS ---
    cors_allow_origins: List[str] = ["*"]

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = True
    log_dir: str = Field(default="./logs")


@lru_cache
def get_settings() -> Settings:
    return Settings()
