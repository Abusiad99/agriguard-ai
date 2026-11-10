"""Report narrative: the executive summary and short plain-language notes.

An LLM (Gemini, when GEMINI_API_KEY is set) may *word* the summary, but only from a
numbered list of facts taken from the report itself. It must cite the fact ids behind
every sentence, and its JSON output is checked before use:
- schema: the response must parse into ReportNarrative;
- citations: every sentence cites at least one existing fact id;
- numbers: every number in a sentence must appear in the facts it cites;
- no doses or concentrations, no references/URLs/studies, no disease names that are
  not in the facts, no certainty words about predictions ("confirmed", "definitely");
- length limits.
If any check fails, or no LLM is configured, a deterministic template summary is used
instead and the reason is stored with the report. Generated text never changes the
structured facts, recommendations or provenance.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.application.reporting.i18n import humanize, num, pct, t

logger = logging.getLogger("agriguard.reports.narrative")

MAX_SENTENCE_CHARS = 400
MAX_SENTENCES = 6

_DOSE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:ml|mL|l|L|g|kg|mg|ppm|cc|oz|lb|gal|لتر|مل|غرام|غ|جم|كغ|كجم)\b"
                   r"|\b(?:per|/)\s*(?:liter|litre|hectare|acre|ha)\b|لكل\s*(?:لتر|هكتار|دونم)", re.IGNORECASE)
_REFERENCE = re.compile(r"https?://|www\.|doi\.org|\bdoi:|\bet al\.?|\[\d+\]|\(\s*(?:19|20)\d{2}\s*\)", re.IGNORECASE)
_CERTAINTY = re.compile(r"\b(?:confirmed|definitely|certainly|guaranteed|undoubtedly|without (?:a )?doubt|100% sure)\b"
                        r"|مؤكد|بالتأكيد|حتمًا|حتما|بلا شك|دون شك", re.IGNORECASE)
_NEGATION = re.compile(r"(?:\bnot|n't|\bnever|\bno|\bun|غير|ليس|ليست|لا|لم)\s*$", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_AR_TO_EN = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


class Statement(BaseModel):
    text: str = Field(max_length=MAX_SENTENCE_CHARS)
    fact_ids: List[str]


class RecommendationNote(BaseModel):
    recommendation_id: str
    text: str = Field(max_length=MAX_SENTENCE_CHARS)
    fact_ids: List[str] = Field(default_factory=list)


class ReportNarrative(BaseModel):
    executive_summary: List[Statement]
    recommendation_notes: List[RecommendationNote] = Field(default_factory=list)


# ------------------------------------------------------------------------------ facts
def facts_packet(content: dict) -> List[dict]:
    """The only material the LLM may use: report facts with stable ids (F1, F2, ...)."""
    items, seen = [], set()

    def add(f: dict):
        if f.get("key") in seen:
            return
        seen.add(f.get("key"))
        items.append({"id": f"F{len(items) + 1}", "key": f.get("key"), "label": f.get("label"),
                      "value": f.get("display"), "source": (f.get("provenance") or {}).get("kind"),
                      "available": f.get("available", True)})

    for f in content.get("key_facts", []):
        add(f)
    for sec in content.get("sections", []):
        for f in sec.get("facts", []):
            if f.get("lang") is None or len(str(f.get("display", ""))) < 240:
                add(f)
    return items


def _numbers(text: str) -> List[float]:
    out = []
    for m in _NUMBER.findall(text.translate(_AR_TO_EN)):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _asserts_certainty(text: str) -> bool:
    """A certainty word that is not negated ("not confirmed", "unconfirmed", "غير مؤكد" are fine)."""
    for m in _CERTAINTY.finditer(text):
        before = text[max(0, m.start() - 12):m.start()]
        if not _NEGATION.search(before) and not text[max(0, m.start() - 2):m.start()].lower().endswith("un"):
            return True
    return False


def validate_narrative(narrative: ReportNarrative, facts: List[dict], content: dict,
                       known_disease_names: List[str]) -> List[str]:
    errors = []
    by_id = {f["id"]: f for f in facts}
    allowed_names = " ".join(str(f.get("value", "")) for f in facts).lower()
    rec_ids = {r["id"] for r in content.get("recommendations", [])}
    if not narrative.executive_summary:
        errors.append("empty executive summary")
    if len(narrative.executive_summary) > MAX_SENTENCES:
        errors.append("executive summary too long")

    def check(text: str, ids: List[str], where: str):
        if not ids:
            errors.append(f"{where}: no cited facts")
            return
        missing = [i for i in ids if i not in by_id]
        if missing:
            errors.append(f"{where}: cites unknown facts {missing}")
            return
        cited_numbers = [n for i in ids for n in _numbers(str(by_id[i].get("value", "")))]
        for n in _numbers(text):
            if not any(abs(n - c) <= max(0.05, abs(c) * 0.005) for c in cited_numbers):
                errors.append(f"{where}: number {n:g} is not in the cited facts")
        if _DOSE.search(text):
            errors.append(f"{where}: contains a dose or concentration")
        if _REFERENCE.search(text):
            errors.append(f"{where}: contains a reference or link")
        if _asserts_certainty(text):
            errors.append(f"{where}: presents a prediction as certain")
        lowered = text.lower()
        for name in known_disease_names:
            if name and name.lower() in lowered and name.lower() not in allowed_names:
                errors.append(f"{where}: names a disease ({name}) that is not in the facts")

    for i, s in enumerate(narrative.executive_summary):
        check(s.text, s.fact_ids, f"summary[{i}]")
    for note in narrative.recommendation_notes:
        if note.recommendation_id not in rec_ids:
            errors.append(f"note for unknown recommendation {note.recommendation_id}")
            continue
        rec = next(r for r in content["recommendations"] if r["id"] == note.recommendation_id)
        evidence_ids = [f["id"] for f in facts if f.get("key") in {e.get("key") for e in rec.get("evidence", [])}]
        check(note.text, note.fact_ids or evidence_ids or ["(none)"], f"note[{note.recommendation_id}]")
    return errors


# --------------------------------------------------------------------------- template
def template_narrative(content: dict, locale: str, facts: List[dict]) -> dict:
    """Deterministic summary from the structured content (always available)."""
    ids = {f["key"]: f["id"] for f in facts}
    disp = {f["key"]: f["value"] for f in facts}
    out: List[dict] = []

    def say(text: str, *keys):
        cited = [ids[k] for k in keys if k in ids]
        if cited:
            out.append({"text": text, "fact_ids": cited})

    kind = content["type"]
    if kind == "diagnosis":
        plant = disp.get("plant", "")
        if content["status"]["code"] == "healthy_predicted":
            say(t(locale, "nar.dx.healthy", plant=plant, confidence=disp.get("confidence", "")), "plant", "confidence")
        else:
            say(t(locale, "nar.dx.disease", condition=disp.get("condition", ""), plant=plant,
                  confidence=disp.get("confidence", "")), "condition", "plant", "confidence")
        margin = next((f for f in facts if f["key"] == "margin" and f["available"]), None)
        if margin and (content.get("status") or {}).get("close_call"):
            say(t(locale, "nar.dx.close", margin=margin["value"]), "margin")
        recall = next((f for f in facts if f["key"] == "test_recall" and f["available"]), None)
        if recall:
            say(t(locale, "nar.dx.test", recall=recall["value"], n=disp.get("test_support", "")), "test_recall", "test_support")
        area = next((f for f in facts if f["key"] == "area_measured"), None)
        if area and area["available"]:
            say(t(locale, "nar.dx.area", area=area["value"]), "area_measured")
        elif "area_estimate" in disp:
            say(t(locale, "nar.dx.area_estimate", area=disp["area_estimate"]), "area_estimate")
        issues = next((f for f in facts if f["key"] == "quality_issues" and f["available"]), None)
        if issues and issues["value"] not in (t(locale, "v.none"),):
            say(t(locale, "nar.dx.quality", issues=issues["value"]), "quality_issues")
    elif kind == "plant_progress":
        say(t(locale, "nar.pp.status", status=disp.get("recovery_status", ""), n=disp.get("count.scans", ""),
              days=disp.get("count.days", "")), "recovery_status", "count.scans", "count.days")
        change = next((f for f in facts if f["key"] == "area_change"), None)
        if change and change["available"]:
            first, _, last = str(change["value"]).partition(" → ")
            say(t(locale, "nar.pp.area", first=first, last=last), "area_change")
        else:
            say(t(locale, "nar.pp.no_area"), "area_change")
        say(t(locale, "nar.pp.treatments", n=disp.get("count.treatments", "")), "count.treatments")
    else:
        if "positives" in disp:
            say(t(locale, "nar.oa.observed", inspections=disp.get("inspections", ""), positives=disp["positives"]),
                "inspections", "positives")
        else:
            say(t(locale, "nar.oa.none_observed"), "inspections")
        if "region_positives" in disp and "region_inspections" in disp:
            say(t(locale, "nar.oa.region", inspections=disp["region_inspections"], positives=disp["region_positives"]),
                "region_inspections", "region_positives")
        risk = next((f for f in facts if f["key"] == "risk_level"), None)
        if risk and risk["available"]:
            say(t(locale, "nar.oa.risk", risk=risk["value"], confidence=disp.get("risk_confidence", "")),
                "risk_level", "risk_confidence")
        else:
            say(t(locale, "nar.oa.no_risk"), "risk_level")
    return {"executive_summary": out, "recommendation_notes": []}


# -------------------------------------------------------------------------------- LLM
def _prompt(content: dict, locale: str, facts: List[dict]) -> str:
    language = "Arabic (Modern Standard Arabic)" if locale == "ar" else "English"
    recs = [{"id": r["id"], "title": r["title"], "reason": r["reason"]} for r in content.get("recommendations", [])]
    return (
        f"You write the executive summary of an agricultural report in {language} for a farmer.\n"
        "STRICT RULES:\n"
        "- Use ONLY the facts below. Do not add diagnoses, symptoms, causes, products, doses, results or references.\n"
        "- Every sentence must list the ids of the facts it is based on in fact_ids.\n"
        "- Copy numbers exactly as written in the facts. Never compute new numbers.\n"
        "- AI predictions and estimates are not confirmed: never call them confirmed, certain or definite.\n"
        "- Do not mention chemical products, concentrations or doses at all.\n"
        "- If information is marked unavailable, say it is not available; do not guess it.\n"
        f"- At most {MAX_SENTENCES} short sentences in executive_summary. Optionally one short note per recommendation id.\n\n"
        f"FACTS:\n{json.dumps(facts, ensure_ascii=False)}\n\nRECOMMENDATIONS:\n{json.dumps(recs, ensure_ascii=False)}\n"
    )


def gemini_generator() -> Optional[Callable[[str], str]]:
    """A prompt -> JSON-text callable using the configured Gemini model, or None."""
    from app.core.config import get_settings

    settings = get_settings()
    if not getattr(settings, "gemini_api_key", None) or not getattr(settings, "reports_llm_enabled", True):
        return None

    def generate(prompt: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model, contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, response_mime_type="application/json", response_schema=ReportNarrative,
                http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000))))
        return response.text or ""

    generate.model_name = settings.gemini_model  # type: ignore[attr-defined]
    return generate


def build_narrative(content: dict, locale: str, known_disease_names: List[str],
                    generator: Optional[Callable[[str], str]] = None) -> dict:
    facts = facts_packet(content)
    template = template_narrative(content, locale, facts)
    result = {"source": "template", "model": None, "facts": facts, **template,
              "validation": {"passed": True, "errors": [], "llm_attempted": generator is not None}}
    if generator is None:
        return result
    try:
        raw = generator(_prompt(content, locale, facts))
        narrative = ReportNarrative.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        result["validation"] = {"passed": False, "errors": [f"invalid LLM output: {exc.__class__.__name__}"], "llm_attempted": True}
        return result
    except Exception as exc:  # noqa: BLE001 - network/API errors: keep the template summary
        logger.warning("Report narrative generation failed: %s", exc)
        result["validation"] = {"passed": False, "errors": [f"LLM unavailable: {exc.__class__.__name__}"], "llm_attempted": True}
        return result
    errors = validate_narrative(narrative, facts, content, known_disease_names)
    if errors:
        result["validation"] = {"passed": False, "errors": errors[:20], "llm_attempted": True}
        return result
    return {"source": "llm", "model": getattr(generator, "model_name", "llm"), "facts": facts,
            "executive_summary": [s.model_dump() for s in narrative.executive_summary],
            "recommendation_notes": [n.model_dump() for n in narrative.recommendation_notes],
            "validation": {"passed": True, "errors": [], "llm_attempted": True}}
