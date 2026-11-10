"""
Outbreak feature engineering — the single implementation used both to build the
training table (ai.outbreak.preprocess) and to predict in the backend, so a model is
always fed features computed the same way it was trained on.

For an (area, crop, disease) and a reference date `as_of`, features describe:
  - history: observed positives/inspections in the cell and its 8 neighbours,
    and the same calendar window one year earlier;
  - weather: the 7 and 14 days up to `as_of` and the forecast window
    (as_of, as_of + horizon];
  - season: day of year as sin/cos.
Missing information stays None (NaN for the model) — it is never replaced by 0 or a
"normal" value, and `completeness()` reports how much was available.

Weather windows are aggregated only when at least MIN_WEATHER_COVERAGE of the days
are present.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

FEATURE_VERSION = "outbreak-features-v1"
MIN_WEATHER_COVERAGE = 0.7

HISTORY_FEATURES = [
    "area_inspections_30d", "area_positives_7d", "area_positives_30d", "area_positives_90d",
    "area_positive_rate_90d", "neighbor_positives_30d", "area_positives_same_window_last_year",
    "days_since_last_positive",
]
WEATHER_FEATURES = [
    "temp_mean_7d", "temp_min_mean_7d", "rh_mean_7d", "rh90_hours_7d", "precip_sum_7d",
    "rh_mean_14d", "precip_sum_14d",
    "fc_temp_mean", "fc_rh_mean", "fc_rh90_hours", "fc_precip_sum",
]
SEASON_FEATURES = ["doy_sin", "doy_cos", "horizon_days"]
FEATURE_NAMES = HISTORY_FEATURES + WEATHER_FEATURES + SEASON_FEATURES
CATEGORICAL = ["crop", "disease"]


@dataclass(frozen=True)
class Observation:
    observed_on: date
    is_positive: bool
    count: int = 1             # inspections represented by the record
    positive_count: Optional[int] = None


@dataclass(frozen=True)
class DailyWeather:
    day: date
    temperature_mean_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    relative_humidity_mean_pct: Optional[float] = None
    rh_hours_ge_90: Optional[float] = None
    precipitation_mm: Optional[float] = None


def _positives(obs: Observation) -> int:
    if obs.positive_count is not None:
        return obs.positive_count
    return obs.count if obs.is_positive else 0


def _in_window(observations: Iterable[Observation], start: date, end: date) -> List[Observation]:
    return [o for o in observations if start <= o.observed_on <= end]


def _aggregate(weather: Dict[date, DailyWeather], start: date, end: date, attr: str, how: str) -> Optional[float]:
    days = (end - start).days + 1
    values = [getattr(weather[d], attr) for d in (start + timedelta(i) for i in range(days))
              if d in weather and getattr(weather[d], attr) is not None]
    if days <= 0 or len(values) < MIN_WEATHER_COVERAGE * days:
        return None
    if how == "sum":
        # Scale a partially-covered window up to its full length rather than undercount it.
        return round(sum(values) * days / len(values), 3)
    return round(sum(values) / len(values), 3)


def build_features(as_of: date, horizon_days: int, area_obs: List[Observation], neighbor_obs: List[Observation],
                   weather: Dict[date, DailyWeather]) -> Dict[str, Optional[float]]:
    f: Dict[str, Optional[float]] = {}
    past30 = _in_window(area_obs, as_of - timedelta(29), as_of)
    past90 = _in_window(area_obs, as_of - timedelta(89), as_of)
    f["area_inspections_30d"] = float(sum(o.count for o in past30))
    f["area_positives_7d"] = float(sum(_positives(o) for o in _in_window(area_obs, as_of - timedelta(6), as_of)))
    f["area_positives_30d"] = float(sum(_positives(o) for o in past30))
    f["area_positives_90d"] = float(sum(_positives(o) for o in past90))
    inspections90 = sum(o.count for o in past90)
    f["area_positive_rate_90d"] = round(f["area_positives_90d"] / inspections90, 4) if inspections90 else None
    f["neighbor_positives_30d"] = float(sum(_positives(o) for o in _in_window(neighbor_obs, as_of - timedelta(29), as_of)))
    last_year = as_of - timedelta(365)
    f["area_positives_same_window_last_year"] = float(sum(
        _positives(o) for o in _in_window(area_obs, last_year - timedelta(15), last_year + timedelta(horizon_days + 15))))
    previous = [o.observed_on for o in area_obs if o.observed_on <= as_of and _positives(o) > 0]
    f["days_since_last_positive"] = float((as_of - max(previous)).days) if previous else None

    w7, w14 = as_of - timedelta(6), as_of - timedelta(13)
    f["temp_mean_7d"] = _aggregate(weather, w7, as_of, "temperature_mean_c", "mean")
    f["temp_min_mean_7d"] = _aggregate(weather, w7, as_of, "temperature_min_c", "mean")
    f["rh_mean_7d"] = _aggregate(weather, w7, as_of, "relative_humidity_mean_pct", "mean")
    f["rh90_hours_7d"] = _aggregate(weather, w7, as_of, "rh_hours_ge_90", "sum")
    f["precip_sum_7d"] = _aggregate(weather, w7, as_of, "precipitation_mm", "sum")
    f["rh_mean_14d"] = _aggregate(weather, w14, as_of, "relative_humidity_mean_pct", "mean")
    f["precip_sum_14d"] = _aggregate(weather, w14, as_of, "precipitation_mm", "sum")
    fc_start, fc_end = as_of + timedelta(1), as_of + timedelta(horizon_days)
    f["fc_temp_mean"] = _aggregate(weather, fc_start, fc_end, "temperature_mean_c", "mean")
    f["fc_rh_mean"] = _aggregate(weather, fc_start, fc_end, "relative_humidity_mean_pct", "mean")
    f["fc_rh90_hours"] = _aggregate(weather, fc_start, fc_end, "rh_hours_ge_90", "sum")
    f["fc_precip_sum"] = _aggregate(weather, fc_start, fc_end, "precipitation_mm", "sum")

    doy = as_of.timetuple().tm_yday
    f["doy_sin"] = round(math.sin(2 * math.pi * doy / 365.25), 6)
    f["doy_cos"] = round(math.cos(2 * math.pi * doy / 365.25), 6)
    f["horizon_days"] = float(horizon_days)
    return {name: f[name] for name in FEATURE_NAMES}


def completeness(features: Dict[str, Optional[float]]) -> float:
    """Share of weather + rate features that could be computed (counts are always
    defined, so they don't count toward completeness)."""
    considered = WEATHER_FEATURES + ["area_positive_rate_90d"]
    present = sum(1 for name in considered if features.get(name) is not None)
    return round(present / len(considered), 3)


def label_window(area_obs: List[Observation], as_of: date, horizon_days: int) -> Optional[int]:
    """Training target: 1 if any positive was observed in (as_of, as_of + horizon],
    0 if inspections happened there and all were negative, None if nothing was
    inspected (absence of reports is not evidence of absence of disease)."""
    window = _in_window(area_obs, as_of + timedelta(1), as_of + timedelta(horizon_days))
    if not window:
        return None
    return int(any(_positives(o) > 0 for o in window))
