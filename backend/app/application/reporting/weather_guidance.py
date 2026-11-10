"""Weather guidance from measured values and verified sources only.

One implementation for every place AgriGuard talks about weather and spraying: the
diagnosis page (API), the per-scan PDF and v2 reports. The same scan therefore gets the
same advice, in the same words, everywhere.

What is assessed, and on what basis:
- Wind at scan time against 3-8 mph, the range advised when a product label gives no wind
  directions (ref-spray-wind). The limits are kept in the source's unit (mph,
  `spray_wind_*_mph` in rules.json) and converted exactly: 3 mph = 4.828032 km/h,
  8 mph = 12.874752 km/h. Both ends are inside the range ("at least 3 and no more than 8"):
  wind > max is "high", wind < min is "calm". Rounded km/h values are for display only.
- Rain: applying pesticides is generally best avoided when rain is likely (ref-rainfast).
  "Likely" means a rain probability AT OR ABOVE `spray_rain_probability_pct` (60 %, so
  exactly 60 % is "likely"). That threshold is AgriGuard's own and is labelled as one.
- Temperature and humidity are shown as measurements only. No general limit was verified,
  so none is applied; the guidance is to follow the product label (ref-spray-wind).

How the verdict is reached:
- "wait": any valid measurement is outside the advised range (one is enough).
- "within_limits": wind AND rain are both valid and both inside. Never otherwise.
- "incomplete": nothing is outside, but wind or rain is missing or invalid.
- "not_assessed": no weather was recorded for the scan.
- "not_applicable": no disease was predicted, so no spraying check is given.
Invalid values (not numbers, NaN, outside physical ranges) are never used, and never shown:
the text says only that the reading was not valid.

Nothing here gives irrigation, fertilizer or disease-risk advice: no verified source
supports the older rules that did (see docs/features/reports.md).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.application.reporting.i18n import LOCALES, day, num, pct, t
from app.application.reporting.references import Citations

# Physically possible ranges; values outside them are treated as invalid, not clipped.
VALID_RANGES = {"wind_speed_kmh": (0.0, 400.0), "rain_probability_pct": (0.0, 100.0),
                "temperature_c": (-80.0, 65.0), "humidity_pct": (0.0, 100.0), "uv_index": (0.0, 25.0)}
VERDICTS = ("within_limits", "wait", "incomplete", "not_assessed", "not_applicable")
MPH_TO_KMH = 1.609344  # exact: 1 international mile = 1609.344 m


def wind_limits(rules: dict) -> dict:
    """Spraying wind limits in km/h (exact) and in the source's mph."""
    if "spray_wind_min_mph" in rules:
        lo_mph, hi_mph = float(rules["spray_wind_min_mph"]), float(rules["spray_wind_max_mph"])
    else:  # older configs stated km/h
        lo_mph, hi_mph = float(rules["spray_wind_min_kmh"]) / MPH_TO_KMH, float(rules["spray_wind_max_kmh"]) / MPH_TO_KMH
    return {"min_mph": lo_mph, "max_mph": hi_mph, "min_kmh": lo_mph * MPH_TO_KMH, "max_kmh": hi_mph * MPH_TO_KMH}


def weather_dict(snapshot) -> Optional[dict]:
    """A stored weather snapshot (domain entity or ORM row) as the plain dict used here."""
    if snapshot is None:
        return None
    retrieved = getattr(snapshot, "retrieved_at", None)
    if isinstance(retrieved, datetime):
        # Stored in UTC. PostgreSQL returns it in the session's time zone and SQLite without one;
        # normalising keeps the API, the report date and the tests independent of the database.
        retrieved = (retrieved if retrieved.tzinfo else retrieved.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    return {"temperature_c": getattr(snapshot, "temperature_c", None), "humidity_pct": getattr(snapshot, "humidity_pct", None),
            "wind_speed_kmh": getattr(snapshot, "wind_speed_kmh", None),
            "rain_probability_pct": getattr(snapshot, "rain_probability_pct", None),
            "uv_index": getattr(snapshot, "uv_index", None),
            "retrieved_at": retrieved.isoformat() if hasattr(retrieved, "isoformat") else retrieved}


def measurements_text(weather: Optional[dict], locale: str = "en") -> Optional[str]:
    """One-line summary of the recorded values; missing values say so, never "None"."""
    if not weather:
        return None
    m = {k: _measure(weather, k) for k in VALID_RANGES}
    missing = t(locale, "u.weather_missing")

    def show(key, fmt):
        return fmt(m[key]["value"]) if m[key]["state"] == "ok" else (
            missing if m[key]["state"] == "missing" else t(locale, "u.weather_invalid"))

    parts = [f"{t(locale, 'f.temperature')}: {show('temperature_c', lambda v: f'{num(v, locale)} °C')}",
             f"{t(locale, 'f.humidity')}: {show('humidity_pct', lambda v: pct(v, locale, 0))}",
             f"{t(locale, 'f.wind')}: {show('wind_speed_kmh', lambda v: f'{num(v, locale)} km/h')}",
             f"{t(locale, 'f.rain_probability')}: {show('rain_probability_pct', lambda v: pct(v, locale, 0))}"]
    return "; ".join(parts)


def _measure(weather: Optional[dict], key: str) -> dict:
    raw = (weather or {}).get(key)
    if raw is None:
        return {"state": "missing", "value": None, "raw": None}
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return {"state": "invalid", "value": None, "raw": raw}
    lo, hi = VALID_RANGES[key]
    if math.isnan(value) or math.isinf(value) or not lo <= value <= hi:
        return {"state": "invalid", "value": None, "raw": raw}
    return {"state": "ok", "value": value, "raw": raw}


def assess(weather: Optional[dict], rules: dict, applicable: bool = True) -> dict:
    """Locale-free assessment: measurements, per-condition status and the verdict."""
    measurements = {k: _measure(weather, k) for k in VALID_RANGES}
    wind, rain = measurements["wind_speed_kmh"], measurements["rain_probability_pct"]
    limits = wind_limits(rules)
    if wind["state"] == "ok":
        v = wind["value"]
        wind["status"] = "high" if v > limits["max_kmh"] else "calm" if v < limits["min_kmh"] else "ok"
    else:
        wind["status"] = wind["state"]
    if rain["state"] == "ok":
        rain["status"] = "likely" if rain["value"] >= float(rules["spray_rain_probability_pct"]) else "not_likely"
    else:
        rain["status"] = rain["state"]
    if not applicable:
        verdict = "not_applicable"
    elif not weather:
        verdict = "not_assessed"
    elif wind["status"] in ("high", "calm") or rain["status"] == "likely":
        verdict = "wait"
    elif wind["status"] == "ok" and rain["status"] == "not_likely":
        verdict = "within_limits"
    else:
        verdict = "incomplete"
    return {"verdict": verdict, "measurements": measurements, "observed_at": (weather or {}).get("retrieved_at"),
            "limits": {"wind_min_kmh": limits["min_kmh"], "wind_max_kmh": limits["max_kmh"],
                       "wind_min_mph": limits["min_mph"], "wind_max_mph": limits["max_mph"],
                       "rain_likely_at_or_above_pct": float(rules["spray_rain_probability_pct"])}}


def guidance(weather: Optional[dict], rules: dict, locale: str, cites: Citations, applicable: bool = True) -> dict:
    """Assessment plus the sentences that explain it, in one language. Every item says
    what it rests on: a published source (cited), an AgriGuard rule, or missing data."""
    a = assess(weather, rules, applicable)
    m = a["measurements"]
    items: List[dict] = []
    if a["verdict"] in ("within_limits", "wait", "incomplete"):
        wind, rain = m["wind_speed_kmh"], m["rain_probability_pct"]
        lim = a["limits"]
        shown = {"lo": num(lim["wind_min_kmh"], locale), "hi": num(lim["wind_max_kmh"], locale),
                 "lo_mph": num(lim["wind_min_mph"], locale, 0), "hi_mph": num(lim["wind_max_mph"], locale, 0)}
        if wind["status"] in ("ok", "high", "calm"):
            items.append(_item("wind", "ok" if wind["status"] == "ok" else "caution", "reference",
                               t(locale, f"wx.wind.{wind['status']}", wind=num(wind["value"], locale), **shown),
                               cites.cite("guidance:spray_wind")))
        else:
            items.append(_item("wind", "unavailable", "missing_data",
                               t(locale, f"wx.wind.{wind['status']}"), []))
        threshold = pct(rules["spray_rain_probability_pct"], locale, 0)
        if rain["status"] in ("likely", "not_likely"):
            items.append(_item("rain", "caution" if rain["status"] == "likely" else "ok", "reference",
                               t(locale, f"wx.rain.{rain['status']}", rain=pct(rain["value"], locale, 0), threshold=threshold),
                               cites.cite("guidance:spray_rain")))
        else:
            items.append(_item("rain", "unavailable", "missing_data",
                               t(locale, f"wx.rain.{rain['status']}"), []))
        temp, hum = m["temperature_c"], m["humidity_pct"]
        # missing and invalid readings are named as such; an invalid value is never shown
        values = [t(locale, "wx.temp_value", value=num(temp["value"], locale)) if temp["state"] == "ok"
                  else t(locale, f"wx.temp_{'invalid' if temp['state'] == 'invalid' else 'unavailable'}"),
                  t(locale, "wx.humidity_value", value=pct(hum["value"], locale, 0)) if hum["state"] == "ok"
                  else t(locale, f"wx.humidity_{'invalid' if hum['state'] == 'invalid' else 'unavailable'}")]
        items.append(_item("label_limits", "info", "reference",
                           t(locale, "wx.label_limits", values=t(locale, "wx.list_sep").join(values)),
                           cites.cite("guidance:spray_temperature")))
    summary = t(locale, f"wx.verdict.{a['verdict']}", when=_when(a["observed_at"], locale))
    return {**a, "summary": summary, "items": items, "refs": sorted({r for i in items for r in i["refs"]})}


def _when(observed_at, locale: str) -> str:
    if not observed_at:
        return t(locale, "wx.when_unknown")
    try:
        return day(observed_at, locale)
    except (TypeError, ValueError):
        return t(locale, "wx.when_unknown")



def _item(code: str, status: str, basis: str, text: str, refs: List[str]) -> dict:
    return {"code": code, "status": status, "basis": basis, "text": text, "refs": list(refs)}


def guidance_all_locales(weather: Optional[dict], rules: dict, applicable: bool = True) -> dict:
    """For the diagnosis API: the same guidance in every report language, plus the cited
    sources (with what each is cited for, per language). The UI picks its language."""
    per = {}
    for loc in LOCALES:
        cites = Citations(loc)
        per[loc] = (guidance(weather, rules, loc, cites, applicable), cites)
    base, _ = per["en"]
    items = []
    for i, item in enumerate(base["items"]):
        items.append({"code": item["code"], "status": item["status"], "basis": item["basis"], "refs": item["refs"],
                      "text": {loc: per[loc][0]["items"][i]["text"] for loc in LOCALES}})
    references: Dict[str, dict] = {}
    for loc in LOCALES:
        for ref in per[loc][1].to_list():
            entry = references.setdefault(ref["id"], {k: ref.get(k) for k in ("id", "n", "title", "authors", "organization", "url",
                                                                                 "doi", "publication_date", "source_type",
                                                                                 "verified_on")} | {"claims": {}})
            entry["claims"][loc] = ref["claims"]
    return {"verdict": base["verdict"], "observed_at": base["observed_at"], "limits": base["limits"],
            "measurements": {k: {"state": v["state"], "value": v["value"], **({"status": v["status"]} if "status" in v else {})}
                             for k, v in base["measurements"].items()},
            "summary": {loc: per[loc][0]["summary"] for loc in LOCALES}, "items": items,
            "references": sorted(references.values(), key=lambda r: r["n"]), "rules_version": rules.get("rules_version")}
