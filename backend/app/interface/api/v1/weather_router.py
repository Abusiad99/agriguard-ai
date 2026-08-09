"""Weather routes — FR-WEATHER-1, BR7. See API spec §8.

Contract: never returns a 5xx for weather unavailability — always a well-formed 200
body the caller can branch on (`available: false`), matching the API spec's explicit
design decision so a downstream scan can still complete without weather data
(NFR-AVAIL-2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.domain.entities.user import User
from app.infrastructure.external.weather_client import WeatherService
from app.interface.api.v1.dependencies import get_current_user, get_weather_service
from app.interface.schemas.common_schemas import WeatherResponseSchema

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("", response_model=WeatherResponseSchema)
def get_weather(
    lat: float = Query(...), lon: float = Query(...),
    current_user: User = Depends(get_current_user),
    weather_service: WeatherService = Depends(get_weather_service),
):
    conditions = weather_service.get_conditions(lat, lon)
    if conditions is None:
        return WeatherResponseSchema(available=False, reason="weather_provider_unreachable")
    return WeatherResponseSchema(
        available=True, temperature_c=conditions.temperature_c, humidity_pct=conditions.humidity_pct,
        wind_speed_kmh=conditions.wind_speed_kmh, rain_probability_pct=conditions.rain_probability_pct,
        uv_index=conditions.uv_index,
    )
