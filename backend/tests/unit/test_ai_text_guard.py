"""AI text guard (app/application/services/ai_text_guard.py): weather-based advice written by
an LLM is removed; symptom analysis and non-weather guidance stay. SYNTHETIC sentences."""
from __future__ import annotations

import pytest

from app.application.services.ai_text_guard import is_weather_advice, strip_list, strip_weather_advice

REMOVED = [
    "Weather conditions are currently favorable for spraying.",
    "High humidity favours fungal spread; consider treatment soon.",
    "Apply copper fungicide when no rain is forecast for 24 hours.",
    "Wait for calmer wind before spraying.",
    "Rain is likely in the next few hours, so delay spraying.",
    "Delay irrigation; expected rainfall may be sufficient.",
    "Warm, humid conditions promote late blight.",
    "These conditions are conducive to disease development.",
    "Environmental conditions favour fungal growth.",
    "Hold off on fertilizer during hot weather.",
    "الطقس مناسب للرش الآن.",
    "تجنب الرش عند هبوب الرياح.",
    "الرطوبة العالية تساعد على انتشار المرض.",
]
KEPT = [
    "The lesions are dark brown with concentric rings, consistent with early blight.",
    "Symptoms match the CV model's prediction.",
    "Remove infected leaves and destroy them.",
    "Keep foliage dry by avoiding overhead irrigation.",
    "Confidence is high, but confirm with an agronomist.",
    "Current weather: temperature 22 °C; humidity 50%.",
    "البقع بنية داكنة مع حلقات متحدة المركز.",
    "أزل الأوراق المصابة.",
]


@pytest.mark.parametrize("sentence", REMOVED)
def test_weather_advice_is_detected(sentence):
    assert is_weather_advice(sentence)


@pytest.mark.parametrize("sentence", KEPT)
def test_unrelated_text_is_kept(sentence):
    assert not is_weather_advice(sentence)


def test_only_the_offending_sentences_are_removed():
    text = ("The leaves show water-soaked lesions typical of late blight. Weather conditions are favourable for spraying today. "
            "Severity is an estimate from the heatmap.")
    clean, removed = strip_weather_advice(text)
    assert removed == 1
    assert clean == "The leaves show water-soaked lesions typical of late blight. Severity is an estimate from the heatmap."


def test_arabic_sentences_are_split_and_filtered():
    clean, removed = strip_weather_advice("البقع بنية داكنة. الطقس مناسب للرش الآن. أزل الأوراق المصابة.")
    assert removed == 1 and "الرش" not in clean and "البقع بنية داكنة." in clean


def test_lists_drop_only_weather_advice_items():
    kept, removed = strip_list(["Remove infected leaves.", "Spray when wind is below 10 km/h.", "Rotate crops next season."])
    assert kept == ["Remove infected leaves.", "Rotate crops next season."] and removed == 1


def test_empty_input():
    assert strip_weather_advice("") == ("", 0) and strip_weather_advice(None) == ("", 0)
    assert strip_list(None) == ([], 0)
