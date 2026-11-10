"""
Disease-specific environmental suitability rules (configs/outbreak/suitability_profiles.json).

These are published, rule-based criteria — NOT a trained prediction — and are shown
as "weather suitability" next to (never instead of) the model's risk. Every profile
must cite its source; profiles without one are rejected. Add a disease by adding a
profile with a supported `rule` and its parameters.

Supported rules
  hutton_criteria   Two consecutive days, each with minimum temperature >= T and
                    >= H hours of relative humidity >= 90 %. Used for potato late
                    blight (Phytophthora infestans) risk in Great Britain.

If the weather needed by a rule is missing, the result is "insufficient_weather_data",
never "conditions not met".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ai.config import PROJECT_ROOT
from ai.outbreak.features import DailyWeather

PROFILES_PATH = PROJECT_ROOT / "configs" / "outbreak" / "suitability_profiles.json"


@dataclass
class SuitabilityProfile:
    id: str
    crop: str
    disease: str
    rule: str
    parameters: dict
    source: str
    description: str
    reference_id: Optional[str] = None   # entry in configs/reports/references.json, when catalogued


def load_profiles(path: Path = PROFILES_PATH) -> List[SuitabilityProfile]:
    if not Path(path).is_file():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = []
    for raw in data.get("profiles", []):
        if not str(raw.get("source", "")).strip():
            raise ValueError(f"suitability profile '{raw.get('id')}' has no source; every rule must cite one")
        if raw.get("rule") not in RULES:
            raise ValueError(f"suitability profile '{raw.get('id')}' uses unknown rule '{raw.get('rule')}'")
        profiles.append(SuitabilityProfile(**{k: raw[k] for k in SuitabilityProfile.__dataclass_fields__ if k != "reference_id"},
                                           reference_id=raw.get("reference_id")))
    return profiles


def profiles_for(crop: str, disease: str, profiles: Optional[List[SuitabilityProfile]] = None) -> List[SuitabilityProfile]:
    profiles = load_profiles() if profiles is None else profiles
    return [p for p in profiles if p.crop == crop and p.disease == disease]


def _hutton(profile: SuitabilityProfile, weather: Dict[date, DailyWeather], start: date, end: date) -> dict:
    p = profile.parameters
    min_temp, min_hours, run = float(p["min_temperature_c"]), float(p["min_rh90_hours"]), int(p.get("consecutive_days", 2))
    days = [start + timedelta(i) for i in range((end - start).days + 1)]
    missing = [d.isoformat() for d in days
               if d not in weather or weather[d].temperature_min_c is None or weather[d].rh_hours_ge_90 is None]
    if len(missing) > len(days) // 2:
        return {"status": "insufficient_weather_data", "missing_days": missing, "periods": []}
    qualifying = [d for d in days if d in weather and weather[d].temperature_min_c is not None
                  and weather[d].rh_hours_ge_90 is not None
                  and weather[d].temperature_min_c >= min_temp and weather[d].rh_hours_ge_90 >= min_hours]
    periods, streak = [], []
    for d in days:
        if d in qualifying:
            streak.append(d)
        else:
            streak = []
        if len(streak) >= run:
            periods.append({"start": streak[-run].isoformat(), "end": d.isoformat()})
    return {"status": "met" if periods else "not_met", "periods": periods, "missing_days": missing}


RULES = {"hutton_criteria": _hutton}


def evaluate(profile: SuitabilityProfile, weather: Dict[date, DailyWeather], start: date, end: date) -> dict:
    result = RULES[profile.rule](profile, weather, start, end)
    result.update({"profile_id": profile.id, "rule": profile.rule, "source": profile.source, "reference_id": profile.reference_id,
                   "description": profile.description, "window": {"start": start.isoformat(), "end": end.isoformat()},
                   "kind": "rule_based_suitability"})
    return result
