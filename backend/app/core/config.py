"""
Centralized configuration (requirement #10) for the AgriGuard AI backend.

All values are overridable via environment variables / a `.env` file (pydantic-settings).
Nothing below should ever be hardcoded elsewhere in `app/` — every module that needs a
setting imports `get_settings()` from here. NFR-MAINT-4.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/ -> repository root. Defaults below are
# relative to these so the app runs natively from any working directory; Docker
# overrides every path via environment variables (docker/docker-compose.yml).
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

DEFAULT_JWT_SECRET = "CHANGE_ME_IN_PRODUCTION_ENV"
MIN_PRODUCTION_SECRET_LENGTH = 32  # characters; secrets.token_urlsafe(48) gives 64


def find_configs_dir(start: Path) -> Path:
    """The repository's configs/ folder (report rules, references, outbreak and recovery
    settings), found by walking up from `start`. Natively that is <repo>/configs; in the
    Docker image the backend lives at /app/app next to /app/configs, so a fixed number
    of parent folders would point at the wrong place there."""
    for folder in start.resolve().parents:
        if (folder / "configs" / "reports").is_dir():
            return folder / "configs"
    return _REPO_ROOT / "configs"


CONFIGS_DIR = find_configs_dir(Path(__file__))


class Settings(BaseSettings):
    # Real environment variables win over both files; backend/.env wins over the
    # repo-root .env. Missing files are ignored.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore",
    )

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

    # --- Redis (optional, not required to run) ---
    # Nothing connects to Redis today: the weather cache and rate limiter are
    # in-process. Reserved for a shared cache across replicas
    # (infrastructure/external/redis_cache.py).
    redis_url: str = Field(default="")
    weather_cache_ttl_seconds: int = 3 * 60 * 60  # freshness window, BR7

    # --- JWT / Auth (FR-AUTH, NFR-SEC-3) ---
    jwt_secret_key: str = Field(default=DEFAULT_JWT_SECRET)  # refused at startup when APP_ENV=production
    # Private media (scan photos, heatmaps, segmentation images) is served through signed,
    # expiring URLs (app/core/media_urls.py). LEGACY_PUBLIC_MEDIA=true re-opens the old public
    # /storage/scans and /storage/heatmaps paths for clients that still need them.
    media_url_ttl_seconds: int = 3600
    legacy_public_media: bool = False
    # Reports (docs/features/reports.md). The LLM only words the summary when a Gemini key is
    # set and this is true; its output is validated and falls back to a template.
    report_share_max_days: int = 30
    reports_llm_enabled: bool = True
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
    local_storage_dir: str = Field(default=str(_REPO_ROOT / "storage"))
    s3_bucket: str = Field(default="")
    s3_endpoint_url: str = Field(default="")
    s3_access_key: str = Field(default="")
    s3_secret_key: str = Field(default="")

    # --- AI Pipeline (ties to ai/ package config) ---
    ai_artifacts_dir: str = Field(default=str(_REPO_ROOT / "artifacts"))
    ai_artifacts_run_dir: str = Field(default="", description="Explicit run dir override; empty = use latest trained run")

    # --- Weather API (FR-WEATHER) ---
    weather_api_provider: str = Field(default="open-meteo")  # requires no API key by default
    weather_api_key: str = Field(default="")
    weather_api_base_url: str = Field(default="https://api.open-meteo.com/v1/forecast")
    weather_request_timeout_seconds: float = 5.0
    weather_archive_base_url: str = Field(default="https://archive-api.open-meteo.com/v1/archive")
    weather_forecast_cache_hours: float = 3.0  # cached forecast days older than this are re-fetched

    # --- Outbreak risk (docs/features/outbreak-prediction.md) ---
    outbreak_grid_resolution_deg: float = 0.25   # >= 0.1; observations are aggregated to cells this size
    outbreak_min_contributors: int = 3           # app-scan counts in a cell are hidden below this many distinct users
    outbreak_history_days: int = 400             # history window used for features and trends
    outbreak_min_local_inspections: int = 5      # inspections needed in a cell + its neighbours (history window) to estimate risk
    rate_limit_prediction_per_hour: int = 60

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
    log_dir: str = Field(default=str(_REPO_ROOT / "logs"))


def production_config_problems(settings: "Settings") -> List[str]:
    """Settings that must not reach production. The JWT secret also keys the signed
    media URLs (app/core/media_urls.py), so the published default or a short value
    would let anyone forge both."""
    if settings.app_env != "production":
        return []
    problems = []
    if settings.jwt_secret_key == DEFAULT_JWT_SECRET or len(settings.jwt_secret_key) < MIN_PRODUCTION_SECRET_LENGTH:
        problems.append(f"JWT_SECRET_KEY must be a random value of at least {MIN_PRODUCTION_SECRET_LENGTH} characters "
                        "(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\").")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
