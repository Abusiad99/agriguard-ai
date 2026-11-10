"""
Outbreak risk intelligence (docs/features/outbreak-prediction.md).

What it estimates: the risk that a disease is found in a grid area within a forecast
horizon — never that an outbreak has happened.

Privacy: only scans whose owner chose to attach a location become observations, and
only as a grid cell. Public map/area counts derived from app scans are shown only when
at least `outbreak_min_contributors` distinct users contributed to that cell;
otherwise they are suppressed. Individual coordinates are never returned.

Honesty: a risk level comes only from a trained model that covers the requested
crop/disease, with enough feature completeness. Otherwise the result says why
(model_unavailable / insufficient_data). Missing weather is reported, never assumed.
Rule-based weather suitability (sourced criteria) is returned separately.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.infrastructure.db.models.ai_features_model import DiseaseObservationModel, OutbreakPredictionModel
from app.infrastructure.external.model_clients import ModelUnavailable, OutbreakModelClient
from app.infrastructure.external.weather_client import IDailyWeatherProvider, WeatherProviderError
from app.infrastructure.repositories.ai_features_repository import SqlAlchemyOutbreakRepository

from ai.outbreak import grid, suitability
from ai.outbreak.features import HISTORY_FEATURES, DailyWeather, Observation, build_features, completeness

logger = logging.getLogger("agriguard.outbreak")
settings = get_settings()

PREDICTION_FRESHNESS = timedelta(days=2)  # map shows predictions made within this window
MAX_HORIZON_DAYS = 14
# Added to a prediction's limitations when its history features were withheld from the
# response (see OutbreakService._history_withheld).
HISTORY_WITHHELD = "history_withheld_for_privacy"


def utc_today() -> date:
    """Observations are dated by the scan's UTC timestamp, so windows use the UTC date
    too (the server's local date can be a day off around midnight)."""
    return datetime.now(timezone.utc).date()


def _round(value):
    return round(float(value), 4) if value is not None else None


class OutbreakService:
    def __init__(self, repo: SqlAlchemyOutbreakRepository, model_client: OutbreakModelClient,
                 weather: Optional[IDailyWeatherProvider]):
        self.repo = repo
        self.model_client = model_client
        self.weather = weather

    # ------------------------------------------------------------------ ingestion
    def record_scan_observation(self, diagnosis, crop: Optional[str]) -> Optional[DiseaseObservationModel]:
        """Turn an opted-in, located scan into an area observation. Skips scans without
        a location, unrecognized plants and low-confidence results (they are too
        uncertain to count as evidence)."""
        if diagnosis.location_lat is None or diagnosis.location_lon is None or not crop or not diagnosis.predicted_condition:
            return None
        if diagnosis.unrecognized_plant or diagnosis.low_confidence_flag:
            return None
        if self.repo.observation_for_diagnosis(diagnosis.id):
            return None
        cell = grid.cell_for(float(diagnosis.location_lat), float(diagnosis.location_lon), settings.outbreak_grid_resolution_deg)
        area = self.repo.get_or_create_area(cell)
        positive = diagnosis.predicted_condition != "healthy"
        # Dated by the scan's UTC day, like every outbreak window (utc_today). PostgreSQL
        # returns timestamps in its session time zone, so in a zone ahead of UTC a scan made
        # before UTC midnight would otherwise land on the next day and drop out of a window
        # that ends today.
        observed = _aware(diagnosis.diagnosed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
        return self.repo.add_observation(DiseaseObservationModel(
            area_id=area.id, source="app_scan", diagnosis_id=diagnosis.id, crop=crop,
            disease=diagnosis.predicted_condition, is_positive=positive, inspected_count=1,
            positive_count=1 if positive else 0, observed_on=observed))

    # ------------------------------------------------------------------ readiness
    def readiness(self) -> dict:
        card = self.model_client.status()
        counts = self.repo.readiness_counts()
        limitations = []
        if not card.is_ready:
            limitations.append("model_not_ready")
        if counts["app_scan_observations"] + counts["dataset_observations"] == 0:
            limitations.append("no_observations")
        if self.weather is None:
            limitations.append("weather_provider_not_configured")
        profiles = suitability.load_profiles()
        return {
            "model": card.public_dict(),
            "data": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in counts.items()},
            "suitability_profiles": [{"id": p.id, "crop": p.crop, "disease": p.disease, "source": p.source} for p in profiles],
            "privacy": {"grid_resolution_deg": settings.outbreak_grid_resolution_deg,
                        "min_contributors": settings.outbreak_min_contributors},
            "can_predict": card.is_ready,
            "limitations": limitations,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def filters(self) -> dict:
        values = self.repo.filter_values()
        card = self.model_client.status()
        model_pairs = [{"crop": c.split("/")[0], "disease": c.split("/")[1]} for c in card.classes if "/" in c]
        profile_pairs = [{"crop": p.crop, "disease": p.disease} for p in suitability.load_profiles()]
        pairs = {(p["crop"], p["disease"]) for p in values["pairs"] + model_pairs + profile_pairs if p["disease"] != "healthy"}
        return {"crops": sorted({c for c, _ in pairs} | set(values["crops"])),
                "pairs": [{"crop": c, "disease": d, "model_trained": {"crop": c, "disease": d} in model_pairs}
                          for c, d in sorted(pairs)],
                "horizons_days": [3, 7, 14]}

    # ------------------------------------------------------------------ map
    def _visible_counts(self, row) -> dict:
        suppressed = 0 < row.app_contributors < settings.outbreak_min_contributors
        app_inspections = None if suppressed else int(row.app_inspections or 0)
        app_positives = None if suppressed else int(row.app_positives or 0)
        inspections = (app_inspections or 0) + int(row.dataset_inspections or 0)
        positives = (app_positives or 0) + int(row.dataset_positives or 0)
        # latest_observation covers both sources, so when app counts are suppressed only the
        # survey date is shown (it could otherwise be a suppressed scan's date).
        latest = getattr(row, "latest_dataset_observation", None) if suppressed else row.latest_observation
        return {"app_inspections": app_inspections, "app_positives": app_positives,
                "dataset_inspections": int(row.dataset_inspections or 0), "dataset_positives": int(row.dataset_positives or 0),
                "app_counts_suppressed": suppressed, "inspections": inspections, "positives": positives,
                "positive_rate": round(positives / inspections, 4) if inspections else None,
                "latest_observation": latest.isoformat() if latest else None}

    def _history_withheld(self, area, crop: str, since: date) -> bool:
        """True when the app scans behind this cell's or a neighbouring cell's history come
        from fewer than OUTBREAK_MIN_CONTRIBUTORS distinct users. The history features
        (case counts, days since the last case) would then reveal those users' results,
        which the map and the area panel suppress, so responses leave them out. The
        model itself still uses them; the stored prediction keeps them."""
        cell = grid.cell_from_key(area.grid_key)
        area_ids = [area.id] + [a.id for a in self.repo.areas_by_keys([n.key for n in grid.neighbors(cell)])]
        counts = self.repo.app_contributors(area_ids, crop, since)
        return any(0 < n < settings.outbreak_min_contributors for n in counts.values())

    def map_layer(self, crop: Optional[str], disease: Optional[str], date_from: date, date_to: date,
                  bbox: Optional[Tuple[float, float, float, float]], horizon_days: int, page: int, page_size: int) -> dict:
        if date_from > date_to:
            raise ValidationError("date_from must not be after date_to.")
        rows, total = self.repo.aggregate(crop, disease, date_from, date_to, bbox, page, page_size)
        predictions = {}
        if crop and disease:
            predictions = self.repo.latest_predictions([r[0].id for r in rows], crop, disease, horizon_days,
                                                       datetime.now(timezone.utc) - PREDICTION_FRESHNESS)
        cells, hidden = [], 0
        for row in rows:
            area = row[0]
            counts = self._visible_counts(row)
            prediction = predictions.get(area.id)
            if counts["inspections"] == 0 and prediction is None:
                hidden += 1  # everything in this cell is below the privacy threshold
                continue
            cells.append({"area": _area(area), **counts,
                          "prediction": _prediction_summary(prediction) if prediction else None})
        return {"cells": cells, "total_areas": total, "page": page, "page_size": page_size,
                "hidden_for_privacy": hidden, "filters": {"crop": crop, "disease": disease, "date_from": date_from.isoformat(),
                                                          "date_to": date_to.isoformat(), "horizon_days": horizon_days},
                "privacy": {"min_contributors": settings.outbreak_min_contributors,
                            "grid_resolution_deg": settings.outbreak_grid_resolution_deg},
                "generated_at": datetime.now(timezone.utc).isoformat()}

    # ------------------------------------------------------------------ area detail
    def lookup(self, lat: float, lon: float) -> dict:
        try:
            cell = grid.cell_for(lat, lon, settings.outbreak_grid_resolution_deg)
        except ValueError as exc:
            raise ValidationError(str(exc))
        area = self.repo.get_area_by_key(cell.key)
        lat_c, lon_c = cell.center
        return {"area_id": str(area.id) if area else None, "grid_key": cell.key,
                "bounds": {"south": cell.south, "west": cell.west, "north": cell.north, "east": cell.east},
                "center": {"lat": lat_c, "lon": lon_c}}

    def area_detail(self, area_id: UUID, crop: Optional[str], disease: Optional[str], weeks: int,
                    date_from: Optional[date] = None, date_to: Optional[date] = None) -> dict:
        """Counts and weekly trend over [date_from, date_to] (the map's window, so the
        panel matches the cell that was clicked); without a window, the last `weeks`."""
        area = self.repo.get_area(area_id)
        if area is None:
            raise NotFoundError("Area not found.")
        today = utc_today()
        until = date_to or today
        since = date_from or until - timedelta(weeks=weeks)
        rows, _ = self.repo.aggregate(crop, disease, since, until, None, 1, 1, area_id=area.id)
        row = rows[0] if rows else None
        summary = self._visible_counts(row) if row else None
        trend = self._trend(area, crop, disease, since, until, summary)
        weather_rows = self.repo.weather_days(area.id, today - timedelta(days=14), today + timedelta(days=MAX_HORIZON_DAYS))
        weather = {w.day: _daily(w) for w in weather_rows}
        suit = [suitability.evaluate(p, weather, today - timedelta(days=6), today + timedelta(days=7))
                for p in suitability.profiles_for(crop, disease)] if crop and disease and weather else []
        predictions, _ = self.repo.list_predictions(area.id, crop, disease, 1, 10)
        return {
            "area": _area(area), "summary": summary, "trend": trend,
            "weather": {"days": [_weather_out(w) for w in weather_rows],
                        "retrieved_at": max((w.retrieved_at for w in weather_rows), default=None)},
            "suitability": suit,
            "predictions": [_prediction_summary(p) for p in predictions],
            "model": self.model_client.status().public_dict(),
        }

    def _trend(self, area, crop, disease, since, until, summary) -> List[dict]:
        """Weekly inspections/positives. App-derived counts are left out when the cell is
        below the privacy threshold (same rule as the summary)."""
        if not crop:
            return []
        include_app = bool(summary) and not summary["app_counts_suppressed"]
        weeks: Dict[date, dict] = {}
        for o in self.repo.observations([area.id], crop, since):
            if o.observed_on > until:
                continue
            if o.source == "app_scan" and not include_app:
                continue
            if o.source == "dataset" and disease and o.disease != disease:
                continue
            week = o.observed_on - timedelta(days=o.observed_on.weekday())
            bucket = weeks.setdefault(week, {"week_start": week.isoformat(), "inspections": 0, "positives": 0})
            bucket["inspections"] += o.inspected_count
            positive = o.positive_count if o.source == "dataset" else int(o.is_positive and (not disease or o.disease == disease))
            bucket["positives"] += positive
        return [weeks[k] for k in sorted(weeks)]

    # ------------------------------------------------------------------ prediction
    def _ensure_weather(self, area, start: date, end: date, limitations: List[str]) -> Dict[date, DailyWeather]:
        rows = self.repo.weather_days(area.id, start, end)
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=settings.weather_forecast_cache_hours)
        have = {r.day: r for r in rows}
        needed = [start + timedelta(i) for i in range((end - start).days + 1)]
        missing = [d for d in needed if d not in have or (have[d].kind == "forecast" and _aware(have[d].retrieved_at) < stale_cutoff)]
        if missing and self.weather is not None:
            try:
                records = self.weather.daily(float(area.center_lat), float(area.center_lon), min(missing), max(missing))
                self.repo.upsert_weather(area.id, records)
                rows = self.repo.weather_days(area.id, start, end)
            except WeatherProviderError as exc:
                logger.warning("Weather unavailable for area %s: %s", area.grid_key, exc)
                limitations.append("weather_unavailable")
        elif missing:
            limitations.append("weather_provider_not_configured")
        return {r.day: _daily(r) for r in rows}

    def _observations(self, area, crop: str, disease: str, as_of: date) -> Tuple[List[Observation], List[Observation]]:
        cell = grid.cell_from_key(area.grid_key)
        neighbor_areas = self.repo.areas_by_keys([n.key for n in grid.neighbors(cell)])
        since = as_of - timedelta(days=settings.outbreak_history_days)
        rows = self.repo.observations([area.id] + [a.id for a in neighbor_areas], crop, since)

        def to_obs(o):
            if o.source == "dataset":
                return Observation(o.observed_on, o.is_positive, o.inspected_count, o.positive_count) if o.disease == disease else None
            hit = o.is_positive and o.disease == disease
            return Observation(o.observed_on, hit, 1, 1 if hit else 0)

        own = [x for x in (to_obs(o) for o in rows if o.area_id == area.id) if x]
        neighbors = [x for x in (to_obs(o) for o in rows if o.area_id != area.id) if x]
        return own, neighbors

    def predict(self, user_id: UUID, crop: str, disease: str, horizon_days: int,
                area_id: Optional[UUID] = None, lat: Optional[float] = None, lon: Optional[float] = None) -> dict:
        if not 1 <= horizon_days <= MAX_HORIZON_DAYS:
            raise ValidationError(f"horizon_days must be between 1 and {MAX_HORIZON_DAYS}.")
        crop, disease = crop.strip().lower(), disease.strip().lower()
        if area_id:
            area = self.repo.get_area(area_id)
            if area is None:
                raise NotFoundError("Area not found.")
        else:
            try:
                area = self.repo.get_or_create_area(grid.cell_for(lat, lon, settings.outbreak_grid_resolution_deg))
            except (TypeError, ValueError) as exc:
                raise ValidationError(str(exc) or "latitude and longitude are required")
            self.repo.db.commit()

        as_of = utc_today()
        start, end = as_of + timedelta(days=1), as_of + timedelta(days=horizon_days)
        limitations: List[str] = []
        weather = self._ensure_weather(area, as_of - timedelta(days=13), end, limitations)
        own, neighbors = self._observations(area, crop, disease, as_of)
        features = build_features(as_of, horizon_days, own, neighbors, weather)
        filled = completeness(features)
        withheld = self._history_withheld(area, crop, as_of - timedelta(days=settings.outbreak_history_days))
        shown = [HISTORY_WITHHELD] if withheld else []  # response-only: re-checked whenever it is read
        suit = [suitability.evaluate(p, weather, as_of - timedelta(days=6), end)
                for p in suitability.profiles_for(crop, disease)]
        base = {"area": _area(area), "crop": crop, "disease": disease, "horizon_days": horizon_days,
                "as_of": as_of.isoformat(), "forecast_start": start.isoformat(), "forecast_end": end.isoformat(),
                "data_completeness": filled, "features": _public_features(features, withheld), "suitability": suit}

        card = self.model_client.status()
        reason = None
        model = None
        if not card.is_ready:
            reason = card.readiness.value
        else:
            try:
                model = self.model_client.get()
            except ModelUnavailable as exc:
                card, reason = exc.card, exc.card.readiness.value
            if model is not None and not model.supports(crop, disease):
                reason = "not_trained_for_crop_disease"
            elif model is not None and model.grid_resolution_deg and \
                    abs(model.grid_resolution_deg - settings.outbreak_grid_resolution_deg) > 1e-9:
                # Count features mean "per cell"; a different cell size changes their meaning.
                reason = "grid_resolution_mismatch"
        if reason:
            return {**base, "status": "model_unavailable", "risk_level": "unavailable", "reason": reason,
                    "model": card.public_dict(), "limitations": sorted(set(limitations + ["model_not_ready"] + shown)),
                    "persisted": False}

        # Never score places the model knows nothing about: zero counts there mean "nobody
        # looked", not "no disease", and the model would read them as low risk.
        cell = grid.cell_from_key(area.grid_key)
        if model.covers(cell.lat_index, cell.lon_index) is False:
            limitations.append("outside_training_region")
        if sum(o.count for o in own + neighbors) < settings.outbreak_min_local_inspections:
            limitations.append("no_local_history")
        min_completeness = float(card.details.get("min_completeness", 0.5))
        if filled < min_completeness:
            limitations.append("low_data_completeness")
        if {"outside_training_region", "no_local_history", "low_data_completeness"} & set(limitations):
            row = self._save(user_id, area, base, card, features, status="insufficient_data",
                             risk_level="insufficient_data", limitations=limitations)
            return {**base, **_prediction_summary(row), "status": "insufficient_data", "model": card.public_dict(),
                    "limitations": sorted(set(limitations + shown)), "persisted": True}

        result = self.model_client.call(lambda m: m.predict(features, crop, disease))
        factors = self.model_client.call(lambda m: m.explain(features))
        inspections_90 = sum(o.count for o in own if o.observed_on >= as_of - timedelta(days=89))
        confidence = ("high" if result["score_kind"] == "calibrated_probability" and filled >= 0.9 and inspections_90 >= 10
                      else "medium" if filled >= 0.7 else "low")
        if result["score_kind"] != "calibrated_probability":
            limitations.append("score_not_calibrated")
        row = self._save(user_id, area, base, card, features, status="ok", risk_level=result["risk_level"],
                         score=result["score"], score_kind=result["score_kind"], confidence=confidence, factors=factors,
                         limitations=limitations)
        return {**base, **_prediction_summary(row), "factors": _public_factors(factors, withheld),
                "model": card.public_dict(), "limitations": sorted(set(limitations + shown)), "persisted": True}

    def _save(self, user_id, area, base, card, features, status, risk_level, score=None, score_kind=None,
              confidence=None, factors=None, limitations=None) -> OutbreakPredictionModel:
        # The stored row keeps the complete features and factors (the model's actual input);
        # responses apply the privacy rule on top (_public_features / _public_factors).
        return self.repo.add_prediction(OutbreakPredictionModel(
            area_id=area.id, crop=base["crop"], disease=base["disease"], horizon_days=base["horizon_days"],
            as_of=date.fromisoformat(base["as_of"]), forecast_start=date.fromisoformat(base["forecast_start"]),
            forecast_end=date.fromisoformat(base["forecast_end"]), status=status, risk_level=risk_level, score=score,
            score_kind=score_kind, confidence_level=confidence, data_completeness=base["data_completeness"],
            model_name=card.name, model_version=card.version, factors_json=factors, features_json=features,
            suitability_json=base["suitability"], limitations_json=sorted(set(limitations or [])), requested_by=user_id))

    def get_prediction(self, prediction_id: UUID) -> dict:
        row = self.repo.get_prediction(prediction_id)
        if row is None:
            raise NotFoundError("Prediction not found.")
        area = self.repo.get_area(row.area_id)
        withheld = self._history_withheld(area, row.crop, row.as_of - timedelta(days=settings.outbreak_history_days))
        limitations = sorted(set((row.limitations_json or []) + ([HISTORY_WITHHELD] if withheld else [])))
        return {**_prediction_summary(row), "area": _area(area), "crop": row.crop, "disease": row.disease,
                "horizon_days": row.horizon_days, "as_of": row.as_of.isoformat(),
                "forecast_start": row.forecast_start.isoformat(), "forecast_end": row.forecast_end.isoformat(),
                "factors": _public_factors(row.factors_json or [], withheld),
                "features": _public_features(row.features_json or {}, withheld),
                "suitability": row.suitability_json or [], "limitations": limitations}

    def list_predictions(self, area_id, crop, disease, page, page_size) -> dict:
        rows, total = self.repo.list_predictions(area_id, crop, disease, page, page_size)
        return {"items": [{**_prediction_summary(r), "area_id": str(r.area_id), "crop": r.crop, "disease": r.disease,
                           "horizon_days": r.horizon_days} for r in rows],
                "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------- helpers
def _public_features(features: dict, withheld: bool) -> dict:
    """Features as returned by the API: history features are None when withheld."""
    if not withheld:
        return dict(features)
    return {name: (None if name in HISTORY_FEATURES else value) for name, value in features.items()}


def _public_factors(factors: Optional[list], withheld: bool) -> Optional[list]:
    """Factors carry the feature's value, so history factors are dropped when withheld."""
    if factors is None or not withheld:
        return factors
    return [f for f in factors if f.get("feature") not in HISTORY_FEATURES]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _area(area) -> dict:
    return {"id": str(area.id), "grid_key": area.grid_key, "resolution_deg": float(area.resolution_deg),
            "bounds": {"south": float(area.south), "west": float(area.west), "north": float(area.north), "east": float(area.east)},
            "center": {"lat": float(area.center_lat), "lon": float(area.center_lon)}, "name": area.name}


def _prediction_summary(p: OutbreakPredictionModel) -> dict:
    return {"prediction_id": str(p.id), "status": p.status, "risk_level": p.risk_level, "score": _round(p.score),
            "score_kind": p.score_kind, "confidence_level": p.confidence_level,
            "data_completeness": _round(p.data_completeness), "model_name": p.model_name, "model_version": p.model_version,
            "horizon_days": p.horizon_days, "created_at": _aware(p.created_at).isoformat() if p.created_at else None,
            "forecast_end": p.forecast_end.isoformat() if p.forecast_end else None}


def _daily(w) -> DailyWeather:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return DailyWeather(w.day, f(w.temperature_mean_c), f(w.temperature_min_c), f(w.temperature_max_c),
                        f(w.relative_humidity_mean_pct), f(w.rh_hours_ge_90), f(w.precipitation_mm))


def _weather_out(w) -> dict:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"day": w.day.isoformat(), "kind": w.kind, "source": w.source, "temperature_mean_c": f(w.temperature_mean_c),
            "temperature_min_c": f(w.temperature_min_c), "temperature_max_c": f(w.temperature_max_c),
            "relative_humidity_mean_pct": f(w.relative_humidity_mean_pct), "rh_hours_ge_90": f(w.rh_hours_ge_90),
            "precipitation_mm": f(w.precipitation_mm)}
