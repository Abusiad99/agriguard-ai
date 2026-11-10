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
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger("agriguard.weather")
settings = get_settings()


@dataclass
class WeatherConditions:
    # None = the provider didn't report it. Never substitute 0 or a "normal" value:
    # downstream advice (e.g. "favorable for spraying") must not rest on invented data.
    temperature_c: Optional[float]
    humidity_pct: Optional[float]
    wind_speed_kmh: Optional[float]
    rain_probability_pct: Optional[float]
    uv_index: Optional[float]
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
                rain_probability_pct=current.get("precipitation_probability"),
                uv_index=current.get("uv_index"),
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


# ---------------------------------------------------------------------------
# Daily weather (history + forecast) for outbreak risk features.
# ---------------------------------------------------------------------------
MIN_HOURS_FOR_DAILY_VALUE = 20  # a daily aggregate needs >= 20 of 24 hourly values, else it stays None


@dataclass
class DailyWeatherRecord:
    day: date
    kind: str  # "observed" (day < today at the location) | "forecast"
    source: str
    temperature_mean_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    relative_humidity_mean_pct: Optional[float] = None
    rh_hours_ge_90: Optional[float] = None
    precipitation_mm: Optional[float] = None


class IDailyWeatherProvider(abc.ABC):
    @abc.abstractmethod
    def daily(self, lat: float, lon: float, start: date, end: date) -> list:
        """DailyWeatherRecords for the days the provider covers within [start, end].
        Raises WeatherProviderError when the provider can't be reached."""


class WeatherProviderError(Exception):
    pass


def aggregate_hourly(times: list, temperature: list, humidity: list, precipitation: list,
                     today: date, source: str) -> list:
    """Hourly Open-Meteo arrays -> one DailyWeatherRecord per local day. Missing hours
    stay missing; a value is only computed with >= MIN_HOURS_FOR_DAILY_VALUE hours."""
    buckets = defaultdict(lambda: {"t": [], "rh": [], "p": []})
    for i, stamp in enumerate(times):
        day = date.fromisoformat(str(stamp)[:10])
        for key, series in (("t", temperature), ("rh", humidity), ("p", precipitation)):
            value = series[i] if i < len(series) else None
            if value is not None:
                buckets[day][key].append(float(value))

    def enough(values):
        return len(values) >= MIN_HOURS_FOR_DAILY_VALUE

    records = []
    for day in sorted(buckets):
        b = buckets[day]
        records.append(DailyWeatherRecord(
            day=day, kind="observed" if day < today else "forecast", source=source,
            temperature_mean_c=round(sum(b["t"]) / len(b["t"]), 2) if enough(b["t"]) else None,
            temperature_min_c=round(min(b["t"]), 2) if enough(b["t"]) else None,
            temperature_max_c=round(max(b["t"]), 2) if enough(b["t"]) else None,
            relative_humidity_mean_pct=round(sum(b["rh"]) / len(b["rh"]), 2) if enough(b["rh"]) else None,
            rh_hours_ge_90=float(sum(1 for v in b["rh"] if v >= 90)) if enough(b["rh"]) else None,
            precipitation_mm=round(sum(b["p"]), 2) if enough(b["p"]) else None,
        ))
    return records


class OpenMeteoDailyProvider(IDailyWeatherProvider):
    """Open-Meteo (no API key). Recent past + forecast come from the forecast API
    (past_days <= 92, forecast_days <= 16); older history from the archive API."""

    HOURLY = "temperature_2m,relative_humidity_2m,precipitation"

    def _get(self, url: str, params: dict) -> dict:
        try:
            response = httpx.get(url, params=params, timeout=settings.weather_request_timeout_seconds)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WeatherProviderError(f"{url}: {exc.__class__.__name__}") from exc

    def daily(self, lat, lon, start, end):
        today = datetime.now(timezone.utc).date()  # same "today" as the outbreak service
        records = []
        recent_start = max(start, today - timedelta(days=92))
        if end >= recent_start:
            data = self._get(settings.weather_api_base_url, {
                "latitude": lat, "longitude": lon, "hourly": self.HOURLY, "timezone": "auto",
                "past_days": min(92, max(0, (today - recent_start).days)),
                "forecast_days": min(16, max(1, (end - today).days + 1))})
            hourly = data.get("hourly", {})
            records += aggregate_hourly(hourly.get("time", []), hourly.get("temperature_2m", []),
                                        hourly.get("relative_humidity_2m", []), hourly.get("precipitation", []),
                                        today, "open-meteo-forecast")
        if start < recent_start:
            data = self._get(settings.weather_archive_base_url, {
                "latitude": lat, "longitude": lon, "hourly": self.HOURLY, "timezone": "auto",
                "start_date": start.isoformat(), "end_date": (recent_start - timedelta(days=1)).isoformat()})
            hourly = data.get("hourly", {})
            records += aggregate_hourly(hourly.get("time", []), hourly.get("temperature_2m", []),
                                        hourly.get("relative_humidity_2m", []), hourly.get("precipitation", []),
                                        today, "open-meteo-archive")
        return [r for r in records if start <= r.day <= end]
