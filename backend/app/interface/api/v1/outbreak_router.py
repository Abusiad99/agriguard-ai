"""Outbreak risk routes (docs/features/outbreak-prediction.md). All require login.
Responses are area-level aggregates; no individual scan location is ever returned."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.application.services.outbreak_service import OutbreakService, utc_today
from app.core.exceptions import ValidationError
from app.domain.entities.user import User
from app.interface.api.v1.dependencies import get_current_user, get_outbreak_service
from app.interface.schemas.ai_features_schemas import PredictionRequest

router = APIRouter(prefix="/outbreak", tags=["Outbreak Risk"])


def _window(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise ValidationError("date_from must be on or before date_to.")
    if date_from and (date_to or utc_today()) - date_from > timedelta(days=3 * 366):
        raise ValidationError("The time window can be at most 3 years.")


def _bbox(value: Optional[str]):
    if not value:
        return None
    try:
        west, south, east, north = (float(x) for x in value.split(","))
    except ValueError:
        raise ValidationError("bbox must be 'west,south,east,north' in degrees.")
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValidationError("bbox is out of range or inverted.")
    return west, south, east, north


@router.get("/readiness")
def readiness(current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    return service.readiness()


@router.get("/filters")
def filters(current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    return service.filters()


@router.get("/map")
def map_layer(crop: Optional[str] = Query(default=None, max_length=100),
              disease: Optional[str] = Query(default=None, max_length=150),
              date_from: Optional[date] = None, date_to: Optional[date] = None,
              bbox: Optional[str] = Query(default=None, description="west,south,east,north"),
              horizon_days: int = Query(default=7, ge=1, le=14),
              page: int = Query(default=1, ge=1), page_size: int = Query(default=200, ge=1, le=500),
              current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    date_to = date_to or utc_today()
    date_from = date_from or date_to - timedelta(days=90)
    _window(date_from, date_to)
    return service.map_layer(crop, disease, date_from, date_to, _bbox(bbox), horizon_days, page, page_size)


@router.get("/areas/lookup")
def lookup_area(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
                current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    return service.lookup(lat, lon)


@router.get("/areas/{area_id}")
def area_detail(area_id: UUID, crop: Optional[str] = Query(default=None, max_length=100),
                disease: Optional[str] = Query(default=None, max_length=150), weeks: int = Query(default=26, ge=1, le=156),
                date_from: Optional[date] = None, date_to: Optional[date] = None,
                current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    _window(date_from, date_to)
    return service.area_detail(area_id, crop, disease, weeks, date_from, date_to)


@router.post("/predictions")
def predict(body: PredictionRequest, current_user: User = Depends(get_current_user),
            service: OutbreakService = Depends(get_outbreak_service)):
    try:
        area_id = UUID(body.area_id) if body.area_id else None
    except ValueError:
        raise ValidationError("area_id is not a valid id.")
    return service.predict(current_user.id, body.crop, body.disease, body.horizon_days, area_id=area_id,
                           lat=body.latitude, lon=body.longitude)


@router.get("/predictions")
def list_predictions(area_id: Optional[UUID] = None, crop: Optional[str] = Query(default=None, max_length=100),
                     disease: Optional[str] = Query(default=None, max_length=150),
                     page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
                     current_user: User = Depends(get_current_user), service: OutbreakService = Depends(get_outbreak_service)):
    return service.list_predictions(area_id, crop, disease, page, page_size)


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: UUID, current_user: User = Depends(get_current_user),
                   service: OutbreakService = Depends(get_outbreak_service)):
    return service.get_prediction(prediction_id)
