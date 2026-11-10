"""Keeps AI-written text (the optional Gemini explanation) from giving weather-based advice.

AgriGuard gives spraying guidance only from measured weather and verified sources
(app/application/reporting/weather_guidance.py). An LLM sentence such as "conditions are
favourable for spraying" or "high humidity favours fungal spread" has neither, so any
sentence that pairs a weather term with an advice or suitability term is removed before
the explanation is shown. The raw model output stays stored unchanged for audit; this
filter runs whenever a diagnosis is read, so older stored analyses are covered too.

Deliberately conservative: it removes a sentence when in doubt. A removed sentence is
replaced by a pointer to the sourced spraying-conditions section, never by new advice.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Tuple

_AR = r"(?<![؀-ۿ])(?:{})(?![؀-ۿ])"
_WEATHER = re.compile(
    r"\b(?:weather|rain\w*|wind\w*|humid\w*|temperatures?|forecast\w*|dew|drizzle|storm\w*|frost\w*|"
    r"(?:dry|wet|moist|warm|hot|cool|cold|damp) (?:conditions|weather|spells?|periods?|air|days?)|"
    r"(?:current|these|such|present|prevailing|local|environmental|climatic|weather) conditions|"
    r"environment(?:al)?|climat\w*)\b|"
    + _AR.format("طقس|الطقس|أمطار|الأمطار|مطر|المطر|رياح|الرياح|رطوبة|الرطوبة|حرارة|الحرارة|توقعات|التوقعات|ندى|الندى"),
    re.IGNORECASE)
_ADVICE = re.compile(
    r"\b(?:spray\w*|apply\w*|applications?|irrigat\w*|water(?:ing)?|fertili[sz]\w*|delay\w*|postpon\w*|wait\w*|"
    r"avoid\w*|favou?r\w*|suitable|unsuitable|ideal|conducive|promot\w*|optimal|encourag\w*|"
    r"(?:good|best|right) time)\b|"
    + _AR.format("رش|الرش|رشّ|ري|الري|تسميد|التسميد|تأجيل|أجّل|أجل|انتظر|تجنب|تجنّب|ملائم|ملائمة|مناسب|مناسبة|يساعد|تساعد|يشجع|تشجع"),
    re.IGNORECASE)
_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n+")


def is_weather_advice(sentence: str) -> bool:
    return bool(_WEATHER.search(sentence) and _ADVICE.search(sentence))


def strip_weather_advice(text: str) -> Tuple[str, int]:
    """Text with weather-advice sentences removed, and how many were removed."""
    if not text:
        return text or "", 0
    sentences = [s for s in _SPLIT.split(text) if s.strip()]
    kept = [s for s in sentences if not is_weather_advice(s)]
    return " ".join(kept).strip(), len(sentences) - len(kept)


def strip_list(items: Iterable[str]) -> Tuple[List[str], int]:
    kept, removed = [], 0
    for item in items or []:
        text, n = strip_weather_advice(item)
        removed += n
        if text:
            kept.append(text)
    return kept, removed
