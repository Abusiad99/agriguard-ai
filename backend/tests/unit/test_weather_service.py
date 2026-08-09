"""
Unit tests for WeatherService — FR-WEATHER-1..3, BR7, NFR-AVAIL-2/3.

NOT EXECUTABLE IN THIS SANDBOX: app.infrastructure.external.weather_client imports
httpx and app.core.config, neither available offline here. Syntax-checked and
logically reviewed; expected to pass under real pytest with dependencies installed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.infrastructure.external.weather_client import IWeatherClient, WeatherConditions, WeatherService


class FakeWeatherClient(IWeatherClient):
    def __init__(self, conditions=None, call_count_holder=None):
        self._conditions = conditions
        self._calls = call_count_holder if call_count_holder is not None else []

    def fetch(self, lat, lon):
        self._calls.append((lat, lon))
        return self._conditions


class TestWeatherServiceCaching:
    def test_returns_conditions_from_client_on_first_call(self):
        conditions = WeatherConditions(
            temperature_c=30.0, humidity_pct=40.0, wind_speed_kmh=10.0,
            rain_probability_pct=5.0, uv_index=7.0, retrieved_at=datetime.now(timezone.utc),
        )
        calls = []
        service = WeatherService(client=FakeWeatherClient(conditions, calls))

        result = service.get_conditions(31.6, -7.9)
        assert result == conditions
        assert len(calls) == 1

    def test_second_call_within_freshness_window_uses_cache_not_client(self):
        conditions = WeatherConditions(
            temperature_c=28.0, humidity_pct=55.0, wind_speed_kmh=8.0,
            rain_probability_pct=10.0, uv_index=6.0, retrieved_at=datetime.now(timezone.utc),
        )
        calls = []
        service = WeatherService(client=FakeWeatherClient(conditions, calls))

        service.get_conditions(31.6, -7.9)
        service.get_conditions(31.6, -7.9)
        assert len(calls) == 1, "second call should be served from cache, not hit the client again"

    def test_different_coordinates_are_not_cached_together(self):
        conditions = WeatherConditions(
            temperature_c=25.0, humidity_pct=50.0, wind_speed_kmh=5.0,
            rain_probability_pct=0.0, uv_index=4.0, retrieved_at=datetime.now(timezone.utc),
        )
        calls = []
        service = WeatherService(client=FakeWeatherClient(conditions, calls))

        service.get_conditions(31.6, -7.9)
        service.get_conditions(40.0, 10.0)
        assert len(calls) == 2


class TestWeatherServiceGracefulDegradation:
    """NFR-AVAIL-2/3: a failed weather fetch must not raise — it returns None so the
    calling ScanOrchestrator can omit weather fields rather than fail the scan."""

    def test_client_returning_none_propagates_as_none_not_an_exception(self):
        service = WeatherService(client=FakeWeatherClient(conditions=None))
        result = service.get_conditions(0.0, 0.0)
        assert result is None
