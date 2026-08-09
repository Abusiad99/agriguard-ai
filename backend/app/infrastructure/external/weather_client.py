"""
WeatherService — FR-WEATHER-1..3. Uses Open-Meteo (no API key required, generous
free tier) as the default provider; swappable via IWeatherClient if a deployment
prefers OpenWeatherMap/WeatherAPI. Wraps every call with a timeout and never lets a
weather failure block the diagnosis pipeline (NFR-AVAIL-2/3, BR7).
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger("agriguard.weather")
settings = get_settings()


@dataclass
class WeatherConditions:
    temperature_c: float
    humidity_pct: float
    wind_speed_kmh: float
    rain_probability_pct: float
    uv_index: float
    retrieved_at: datetime


class IWeatherClient(abc.ABC):
    @abc.abstractmethod
    def fetch(self, lat: float, lon: float) -> Optional[WeatherConditions]: ...


class OpenMeteoWeatherClient(IWeatherClient):
    def fetch(self, lat: float, lon: float) -> Optional[WeatherConditions]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,uv_index,precipitation_probability",
            "timezone": "auto",
        }
        try:
            response = httpx.get(settings.weather_api_base_url, params=params,
                                  timeout=settings.weather_request_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            current = data.get("current", {})
            return WeatherConditions(
                temperature_c=current.get("temperature_2m"),
                humidity_pct=current.get("relative_humidity_2m"),
                wind_speed_kmh=current.get("wind_speed_10m"),
                rain_probability_pct=current.get("precipitation_probability", 0.0) or 0.0,
                uv_index=current.get("uv_index", 0.0) or 0.0,
                retrieved_at=datetime.now(timezone.utc),
            )
        except (httpx.HTTPError, httpx.TimeoutException, KeyError, ValueError) as exc:
            logger.warning("Weather fetch failed for (%s, %s): %s — degrading gracefully (NFR-AVAIL-2).",
                            lat, lon, exc)
            return None


class WeatherService:
    """Application-facing weather service with an in-memory freshness cache
    (BR7). A production deployment backs this cache with Redis (see
    infrastructure/external/redis_cache.py); this in-memory fallback keeps the
    service correct even if Redis is unavailable in a given environment."""

    def __init__(self, client: Optional[IWeatherClient] = None, cache=None):
        self.client = client or OpenMeteoWeatherClient()
        self._local_cache: dict = {}
        self.cache = cache  # optional ICache (Redis) — see redis_cache.py

    def get_conditions(self, lat: float, lon: float) -> Optional[WeatherConditions]:
        cache_key = f"weather:{round(lat, 3)}:{round(lon, 3)}"

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        conditions = self.client.fetch(lat, lon)
        if conditions is not None:
            self._write_cache(cache_key, conditions)
        return conditions

    def _read_cache(self, key: str) -> Optional[WeatherConditions]:
        entry = self._local_cache.get(key)
        if entry is None:
            return None
        conditions, cached_at = entry
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours <= settings.weather_cache_ttl_seconds / 3600:
            return conditions
        return None

    def _write_cache(self, key: str, conditions: WeatherConditions) -> None:
        self._local_cache[key] = (conditions, datetime.now(timezone.utc))
