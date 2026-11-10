"""Shared weather guidance (app/application/reporting/weather_guidance.py) with SYNTHETIC
weather readings. Checks the verdict for every data situation, the exact thresholds, the
basis and sources of every sentence, English/Arabic equivalence, and that the v2 report
says exactly what the diagnosis API says for the same readings."""
from __future__ import annotations

import json
import math
import re

import pytest

from app.application.reporting import builders
from app.application.reporting.recommendations import diagnosis_recommendations, load_rules
from app.application.reporting.references import Citations, load_catalog
from app.application.reporting.weather_guidance import (MPH_TO_KMH, assess, guidance, guidance_all_locales,
                                                        measurements_text, weather_dict, wind_limits)

RULES = load_rules()
WHEN = "2026-11-01T10:00:00+00:00"
FULL = {"temperature_c": 22.0, "humidity_pct": 55.0, "wind_speed_kmh": 9.0, "rain_probability_pct": 10.0, "uv_index": 3.0,
        "retrieved_at": WHEN}
CATALOG_IDS = {r["id"] for r in load_catalog()["references"]}
OLD_PHRASES = re.compile(r"favou?rable|fungal|irrigat|fertili[sz]|consider treatment|next few hours", re.IGNORECASE)


def wx(**changes):
    out = dict(FULL)
    out.update(changes)
    return out


def g(weather, locale="en", applicable=True):
    return guidance(weather, RULES, locale, Citations(locale), applicable)


def items(result):
    return {i["code"]: i for i in result["items"]}


# ------------------------------------------------------------------ data situations
class TestVerdicts:
    def test_1_no_weather_is_not_assessed(self):
        r = g(None)
        assert r["verdict"] == "not_assessed" and r["items"] == [] and r["refs"] == []
        assert "could not be assessed" in r["summary"] and "within" not in r["summary"]

    def test_2_missing_wind_is_incomplete(self):
        r = g(wx(wind_speed_kmh=None))
        assert r["verdict"] == "incomplete"
        wind = items(r)["wind"]
        assert wind["status"] == "unavailable" and wind["basis"] == "missing_data" and wind["refs"] == []
        assert "not recorded" in wind["text"] and items(r)["rain"]["refs"] == ["ref-rainfast"]
        assert "could not be fully assessed" in r["summary"]

    def test_3_missing_rain_is_incomplete(self):
        r = g(wx(rain_probability_pct=None))
        assert r["verdict"] == "incomplete" and items(r)["rain"]["basis"] == "missing_data"
        assert items(r)["wind"]["status"] == "ok"

    def test_4_missing_temperature_does_not_change_the_verdict(self):
        r = g(wx(temperature_c=None))
        assert r["verdict"] == "within_limits"
        assert "temperature not recorded" in items(r)["label_limits"]["text"]

    def test_5_missing_humidity_does_not_change_the_verdict(self):
        r = g(wx(humidity_pct=None))
        assert r["verdict"] == "within_limits"
        assert "humidity not recorded" in items(r)["label_limits"]["text"]

    def test_6_valid_measurements_within_limits(self):
        r = g(FULL)
        assert r["verdict"] == "within_limits"
        assert items(r)["wind"]["status"] == "ok" and items(r)["rain"]["status"] == "ok"
        assert set(r["refs"]) == {"ref-spray-wind", "ref-rainfast"}
        assert "within the advised limits" in r["summary"] and "1 Nov 2026" in r["summary"]
        assert "AgriGuard threshold" in items(r)["rain"]["text"] and "time of the scan only" in items(r)["rain"]["text"]

    @pytest.mark.parametrize("wind, status", [(20.0, "high"), (2.0, "calm"), (0.0, "calm")])
    def test_7_wind_outside_the_range_means_wait(self, wind, status):
        r = g(wx(wind_speed_kmh=wind))
        assert r["verdict"] == "wait" and r["measurements"]["wind_speed_kmh"]["status"] == status
        assert items(r)["wind"]["status"] == "caution" and items(r)["wind"]["refs"] == ["ref-spray-wind"]

    def test_8_rain_above_the_threshold_means_wait(self):
        r = g(wx(rain_probability_pct=85.0))
        assert r["verdict"] == "wait" and items(r)["rain"]["status"] == "caution"
        assert "generally best avoided" in items(r)["rain"]["text"]

    def test_9_wind_and_rain_both_outside(self):
        r = g(wx(wind_speed_kmh=30.0, rain_probability_pct=90.0))
        assert r["verdict"] == "wait"
        assert [i["status"] for i in r["items"] if i["code"] in ("wind", "rain")] == ["caution", "caution"]

    def test_10_negative_values_are_invalid(self):
        r = g(wx(wind_speed_kmh=-3.0))
        assert r["measurements"]["wind_speed_kmh"]["state"] == "invalid" and r["verdict"] == "incomplete"
        assert "not a valid measurement" in items(r)["wind"]["text"] and items(r)["wind"]["basis"] == "missing_data"

    @pytest.mark.parametrize("key, value", [("rain_probability_pct", 140.0), ("humidity_pct", 120.0),
                                            ("temperature_c", 90.0), ("wind_speed_kmh", 500.0), ("uv_index", 40.0)])
    def test_11_impossible_values_are_invalid(self, key, value):
        r = g(wx(**{key: value}))
        assert r["measurements"][key]["state"] == "invalid" and r["measurements"][key]["value"] is None
        assert r["verdict"] in ("incomplete", "within_limits")  # never "wait" because of a reading that was not used
        if key in ("wind_speed_kmh", "rain_probability_pct"):
            assert r["verdict"] == "incomplete"

    @pytest.mark.parametrize("value", ["fast", "", [], {}, math.nan, math.inf, -math.inf])
    def test_12_non_numeric_values_are_invalid(self, value):
        r = g(wx(wind_speed_kmh=value))
        assert r["measurements"]["wind_speed_kmh"]["state"] == "invalid" and r["verdict"] == "incomplete"

    @pytest.mark.parametrize("value", ["x" * 200, -4.0, 777.0])
    def test_12b_invalid_values_are_never_shown(self, value):
        for locale in ("en", "ar"):
            r = g(wx(wind_speed_kmh=value), locale)
            text = json.dumps(r, ensure_ascii=False)
            assert str(value) not in json.dumps([i["text"] for i in r["items"]] + [r["summary"]], ensure_ascii=False)
            assert "not a valid measurement" in items(r)["wind"]["text"] or "ليست قياسًا صالحًا" in items(r)["wind"]["text"]

    def test_12c_invalid_temperature_and_humidity_are_named_invalid_not_missing(self):
        r_en, r_ar = g(wx(temperature_c=99.0, humidity_pct=150.0)), g(wx(temperature_c=99.0, humidity_pct=150.0), "ar")
        en_text, ar_text = items(r_en)["label_limits"]["text"], items(r_ar)["label_limits"]["text"]
        assert "temperature reading not valid" in en_text and "humidity reading not valid" in en_text
        assert "not recorded" not in en_text and "99" not in en_text and "150" not in en_text
        assert "قراءة الحرارة غير صالحة" in ar_text and "قراءة الرطوبة غير صالحة" in ar_text
        hum = r_en["measurements"]["humidity_pct"]
        assert hum["state"] == "invalid" and hum["value"] is None
        # a missing reading still says "not recorded"
        assert "humidity not recorded" in items(g(wx(humidity_pct=None)))["label_limits"]["text"]

    @pytest.mark.parametrize("weather, verdict", [
        (wx(rain_probability_pct=75.0), "wait"),                              # wind fine, rain likely
        (wx(wind_speed_kmh=None, rain_probability_pct=75.0), "wait"),         # one valid problem is enough
        (wx(wind_speed_kmh=25.0, rain_probability_pct=None), "wait"),
        (wx(wind_speed_kmh="bad", rain_probability_pct=None), "incomplete"),  # nothing usable, no problem shown
        (wx(wind_speed_kmh=None, rain_probability_pct=None, temperature_c=None, humidity_pct=None), "incomplete"),
    ])
    def test_13_conflicting_or_incomplete_measurements(self, weather, verdict):
        assert g(weather)["verdict"] == verdict

    @pytest.mark.parametrize("stamp", [None, "", "not-a-date"])
    def test_14_missing_or_unreadable_timestamp(self, stamp):
        r = g(wx(retrieved_at=stamp))
        assert "(time not recorded)" in r["summary"]
        assert "(الوقت غير مسجّل)" in g(wx(retrieved_at=stamp), "ar")["summary"]

    def test_not_applicable_without_a_disease(self):
        r = g(FULL, applicable=False)
        assert r["verdict"] == "not_applicable" and r["items"] == []


# --------------------------------------------------------------------- thresholds
class TestThresholds:
    def test_wind_limits_are_the_exact_conversion_of_the_source(self):
        lim = wind_limits(RULES)
        assert MPH_TO_KMH == 1.609344
        assert lim["min_mph"] == 3 and lim["max_mph"] == 8
        assert lim["min_kmh"] == pytest.approx(4.828032, abs=1e-12)
        assert lim["max_kmh"] == pytest.approx(12.874752, abs=1e-12)

    @pytest.mark.parametrize("wind, status", [
        (12.874752, "ok"),     # exactly 8 mph: "no more than 8" includes 8
        (12.874753, "high"),
        (12.9, "high"),        # the rounded display value is already above 8 mph
        (4.828032, "ok"),      # exactly 3 mph: "at least 3" includes 3
        (4.828031, "calm"),
        (4.8, "calm"),
    ])
    def test_wind_boundaries(self, wind, status):
        assert assess(wx(wind_speed_kmh=wind), RULES)["measurements"]["wind_speed_kmh"]["status"] == status

    @pytest.mark.parametrize("rain, status", [(60.0, "likely"), (59.999, "not_likely"), (60.0001, "likely"), (0.0, "not_likely"),
                                              (100.0, "likely")])
    def test_rain_boundary_at_or_above_60_is_likely(self, rain, status):
        assert assess(wx(rain_probability_pct=rain), RULES)["measurements"]["rain_probability_pct"]["status"] == status

    def test_limits_are_reported_with_the_assessment(self):
        lim = assess(FULL, RULES)["limits"]
        assert lim["wind_max_kmh"] == pytest.approx(12.874752) and lim["rain_likely_at_or_above_pct"] == 60

    def test_older_configs_in_kmh_still_work(self):
        legacy = {k: v for k, v in RULES.items() if not k.startswith("spray_wind_")}
        legacy.update(spray_wind_min_kmh=4.828032, spray_wind_max_kmh=12.874752)
        assert wind_limits(legacy)["max_mph"] == pytest.approx(8.0)
        assert assess(wx(wind_speed_kmh=12.874752), legacy)["measurements"]["wind_speed_kmh"]["status"] == "ok"

    def test_displayed_limits_match_the_source(self):
        text = items(g(FULL))["wind"]["text"]
        assert "4.8–12.9 km/h (3–8 mph)" in text


# ----------------------------------------------------------- sources and languages
SCENARIOS = [None, FULL, wx(wind_speed_kmh=None), wx(wind_speed_kmh=20.0), wx(rain_probability_pct=80.0),
             wx(wind_speed_kmh=-1.0, humidity_pct=150.0), wx(retrieved_at=None)]


class TestSourcesAndLanguages:
    @pytest.mark.parametrize("weather", SCENARIOS)
    def test_every_sentence_states_its_basis_and_cites_real_sources(self, weather):
        r = g(weather)
        for i in r["items"]:
            assert i["basis"] in ("reference", "missing_data")
            assert (i["basis"] == "reference") == bool(i["refs"])
            assert set(i["refs"]) <= CATALOG_IDS
        assert not OLD_PHRASES.search(json.dumps(r))

    @pytest.mark.parametrize("weather", SCENARIOS + [wx(humidity_pct=95.0, temperature_c=40.0)])
    def test_english_and_arabic_say_the_same_thing(self, weather):
        en, ar = g(weather, "en"), g(weather, "ar")
        assert en["verdict"] == ar["verdict"]
        assert [(i["code"], i["status"], i["basis"], i["refs"]) for i in en["items"]] == \
               [(i["code"], i["status"], i["basis"], i["refs"]) for i in ar["items"]]
        for text in [ar["summary"]] + [i["text"] for i in ar["items"]]:
            assert re.search(r"[؀-ۿ]", text) and "{" not in text
        if weather and weather.get("wind_speed_kmh") == 20.0:
            assert "٢٠٫٠" in items(ar)["wind"]["text"]  # Arabic digits

    def test_all_locales_payload_for_the_api(self):
        out = guidance_all_locales(wx(rain_probability_pct=70.0), RULES)
        assert out["verdict"] == "wait" and set(out["summary"]) == {"en", "ar"}
        assert all(set(i["text"]) == {"en", "ar"} for i in out["items"])
        assert [r["id"] for r in out["references"]] == ["ref-spray-wind", "ref-rainfast"]
        assert all(set(r["claims"]) == {"en", "ar"} and r["url"].startswith("https://") for r in out["references"])
        assert out["measurements"]["rain_probability_pct"] == {"state": "ok", "value": 70.0, "status": "likely"}

    def test_measurement_text_never_prints_none(self):
        text = measurements_text(wx(humidity_pct=None, wind_speed_kmh=-4.0))
        assert "None" not in text and "Not recorded by the weather service" in text and "Not a valid measurement" in text
        assert measurements_text(None) is None

    def test_weather_dict_from_a_stored_snapshot(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        snap = SimpleNamespace(temperature_c=21.5, humidity_pct=None, wind_speed_kmh=7.0, rain_probability_pct=5.0, uv_index=None,
                               retrieved_at=datetime(2026, 11, 1, 10, tzinfo=timezone.utc))
        d = weather_dict(snap)
        assert d["retrieved_at"] == WHEN and d["humidity_pct"] is None and weather_dict(None) is None
        # PostgreSQL returns the session's time zone, SQLite no zone: both become the same UTC instant
        from datetime import timedelta
        for stamp in (datetime(2026, 11, 1, 13, tzinfo=timezone(timedelta(hours=3))), datetime(2026, 11, 1, 10)):
            assert weather_dict(SimpleNamespace(**{**vars(snap), "retrieved_at": stamp}))["retrieved_at"] == WHEN


# ------------------------------------------------- one guidance in reports and API
class TestConsistencyWithReports:
    @pytest.mark.parametrize("weather", [FULL, wx(wind_speed_kmh=25.0), wx(rain_probability_pct=None), wx(wind_speed_kmh="x")])
    @pytest.mark.parametrize("locale", ["en", "ar"])
    def test_v2_report_says_what_the_diagnosis_api_says(self, weather, locale):
        from tests.unit.test_report_v2 import diagnosis_ev, generate

        ev = diagnosis_ev()
        ev["diagnosis"]["weather"] = weather
        content = generate(builders.build_diagnosis, diagnosis_recommendations, ev, locale)
        env = next(s for s in content["sections"] if s["id"] == "environment")
        api = guidance_all_locales(weather, RULES)
        assert env["weather_verdict"] == api["verdict"]
        report_texts = [st["text"] for st in env["statements"]]
        assert report_texts == [api["summary"][locale]] + [i["text"][locale] for i in api["items"]]
        rec = next(r for r in content["recommendations"] if r["rule"] == "R-DX-SPRAY-CONDITIONS")
        assert rec["reason"].startswith(api["summary"][locale])
        # invalid or missing readings appear as "not available", never as values
        facts = {f["key"]: f for f in env["facts"]}
        for key, src in (("wind", "wind_speed_kmh"), ("rain_probability", "rain_probability_pct")):
            assert facts[key]["available"] == (api["measurements"][src]["state"] == "ok")

    def test_report_without_weather_has_no_spraying_recommendation(self):
        from tests.unit.test_report_v2 import diagnosis_ev, generate

        ev = diagnosis_ev()
        ev["diagnosis"]["weather"] = None
        content = generate(builders.build_diagnosis, diagnosis_recommendations, ev)
        assert not any(r["rule"] == "R-DX-SPRAY-CONDITIONS" for r in content["recommendations"])
        env = next(s for s in content["sections"] if s["id"] == "environment")
        assert env["weather_verdict"] == "not_assessed" and env["statements"][0]["kind"] == "missing"
