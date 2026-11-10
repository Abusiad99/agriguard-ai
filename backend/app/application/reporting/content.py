"""Building blocks of a report's structured content (schema agriguard.report.v2).

Every value in a report is a *fact*: a label, the raw value, a display string in the
report language, and its provenance — which kind of source produced it (AI model, model
test results, segmentation measurement, attention-map estimate, rule, knowledge base,
published reference, user record, field observation, weather service) plus the record it
came from. Missing information is a fact too, with `available: False` and the reason, so
nothing is silently dropped.

v2 adds:
- *statements*: the report's reasoning, one sentence each, typed (measured, model output,
  estimate, test result, knowledge base, published source, AgriGuard rule, hypothesis,
  missing) with provenance, the facts they rest on and the references they cite;
- *references*: the sources cited, numbered (see references.py); facts, statements,
  media and recommendations point at them by id;
- *chapters*: the order of a professional assessment (summary, condition, evidence,
  visual results, interpretation, actions, monitoring, limitations, references);
- recommendations carry a time horizon and the basis they rest on.
`validate_content` enforces these rules before a report is stored. v1 reports (stored
before) stay readable; the viewer renders both.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "agriguard.report.v2"
GENERATOR_VERSION = "reports-v2"

PROVENANCE_KINDS = {
    "model", "model_evaluation", "model_measurement", "model_estimate", "rule", "sourced_rule", "reference",
    "knowledge_base", "general_guidance", "user_recorded", "observation", "historical", "weather_provider",
    "llm_summary", "system",
}
STATEMENT_KINDS = ("measured", "model", "estimate", "evaluation", "knowledge", "reference", "rule", "hypothesis",
                   "missing", "observation")
CHAPTERS = ("summary", "condition", "evidence", "visual", "interpretation", "actions", "monitoring", "limitations",
            "references")
HORIZONS = ("immediate", "short_term", "long_term")
BASES = ("reference", "knowledge_base", "agriguard_rule", "general_guidance")


def provenance(kind: str, source: Optional[str] = None, record: Optional[str] = None, **extra) -> dict:
    if kind not in PROVENANCE_KINDS:
        raise ValueError(f"unknown provenance kind {kind}")
    out = {"kind": kind}
    if source:
        out["source"] = source
    if record:
        out["record"] = record
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def fact(key: str, label: str, value: Any, display: str, prov: dict, unit: Optional[str] = None,
         note: Optional[str] = None, lang: Optional[str] = None, refs: Optional[List[str]] = None) -> dict:
    out = {"key": key, "label": label, "value": value, "display": display, "available": True, "provenance": prov}
    if unit:
        out["unit"] = unit
    if note:
        out["note"] = note
    if lang:
        out["lang"] = lang  # verbatim knowledge-base text: the language it was written in
    if refs:
        out["refs"] = list(dict.fromkeys(refs))
    return out


def unavailable(key: str, label: str, reason: str, reason_code: str) -> dict:
    return {"key": key, "label": label, "value": None, "display": reason, "available": False,
            "reason_code": reason_code, "provenance": provenance("system")}


def statement(text: str, kind: str, prov: dict, refs: Optional[List[str]] = None,
              evidence: Optional[List[str]] = None, lang: Optional[str] = None) -> dict:
    if kind not in STATEMENT_KINDS:
        raise ValueError(f"unknown statement kind {kind}")
    out = {"text": text, "kind": kind, "provenance": prov}
    if refs:
        out["refs"] = list(dict.fromkeys(refs))
    if evidence:
        out["evidence"] = [e for e in evidence if e]
    if lang:
        out["lang"] = lang
    return out


def section(section_id: str, title: str, facts: Optional[List[dict]] = None, chapter: Optional[str] = None,
            **extra) -> dict:
    out = {"id": section_id, "title": title, "facts": facts or []}
    if chapter:
        out["chapter"] = chapter
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def canonical_hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()


def iter_facts(content: dict) -> Iterable[dict]:
    yield from content.get("key_facts", [])
    for sec in content.get("sections", []):
        yield from sec.get("facts", [])
        for row in sec.get("rows", []) or []:
            yield from (row.get("cells") or [])


def missing_information(content: dict) -> List[dict]:
    """Every "not available" fact once, with its reason — the report's list of gaps."""
    seen, out = set(), []
    for sec in content.get("sections", []):
        for f in sec.get("facts", []):
            if f.get("available") or f.get("reason_code") in ("none",) or f["key"] in seen:
                continue
            seen.add(f["key"])
            out.append({"key": f["key"], "label": f.get("label"), "reason": f.get("display"),
                        "reason_code": f.get("reason_code"), "section": sec.get("id")})
    return out


def validate_content(content: dict) -> List[str]:
    """Problems that would make the report misleading; empty when it can be stored."""
    problems = []
    ref_ids = {r.get("id") for r in content.get("references", [])}

    def check_refs(where: str, refs):
        for ref in refs or []:
            if ref not in ref_ids:
                problems.append(f"{where} cites unknown reference {ref}")

    for f in iter_facts(content):
        prov = f.get("provenance") or {}
        if prov.get("kind") not in PROVENANCE_KINDS:
            problems.append(f"fact {f.get('key')} has no valid provenance")
        if f.get("available") and isinstance(f.get("value"), (int, float)) and prov.get("kind") == "system" \
                and not f.get("key", "").startswith(("meta.", "count.")):
            problems.append(f"numeric fact {f.get('key')} is attributed to no data source")
        if not f.get("available") and not f.get("reason_code"):
            problems.append(f"unavailable fact {f.get('key')} gives no reason")
        check_refs(f"fact {f.get('key')}", f.get("refs"))
    for sec in content.get("sections", []):
        if content.get("schema") == SCHEMA_VERSION and sec.get("chapter") not in CHAPTERS:
            problems.append(f"section {sec.get('id')} has no chapter")
        for i, st in enumerate(sec.get("statements", []) or []):
            if st.get("kind") not in STATEMENT_KINDS or (st.get("provenance") or {}).get("kind") not in PROVENANCE_KINDS:
                problems.append(f"statement {sec.get('id')}[{i}] has no valid kind or provenance")
            if st.get("kind") == "reference" and not st.get("refs"):
                problems.append(f"statement {sec.get('id')}[{i}] says it is sourced but cites nothing")
            check_refs(f"statement {sec.get('id')}[{i}]", st.get("refs"))
        check_refs(f"section {sec.get('id')}", sec.get("refs"))
        for i, item in enumerate(sec.get("items", []) or []):
            check_refs(f"item {sec.get('id')}[{i}]", item.get("refs"))
    for m in content.get("media", []):
        check_refs(f"media {m.get('id')}", m.get("refs"))
    for chart in content.get("charts", []):
        if not (chart.get("provenance") or {}).get("kind") in PROVENANCE_KINDS:
            problems.append(f"chart {chart.get('id')} has no provenance")
        lengths = {len(chart.get("x", []))} | {len(s.get("values", [])) for s in chart.get("series", [])}
        if len(lengths) != 1:
            problems.append(f"chart {chart.get('id')} has series of different lengths")
        for mk in chart.get("markers", []) or []:
            if not 0 <= mk.get("index", -1) < len(chart.get("x", [])):
                problems.append(f"chart {chart.get('id')} has a marker outside its axis")
    for rec in content.get("recommendations", []):
        rid = rec.get("id")
        if (rec.get("provenance") or {}).get("kind") not in PROVENANCE_KINDS:
            problems.append(f"recommendation {rid} has no provenance")
        if not rec.get("reason"):
            problems.append(f"recommendation {rid} has no reason")
        if content.get("schema") == SCHEMA_VERSION:
            if rec.get("horizon") not in HORIZONS:
                problems.append(f"recommendation {rid} has no time horizon")
            basis = rec.get("basis")
            if basis not in BASES:
                problems.append(f"recommendation {rid} has no basis")
            if basis == "reference" and not rec.get("refs"):
                problems.append(f"recommendation {rid} claims a reference but cites none")
            if basis == "knowledge_base" and (rec.get("provenance") or {}).get("kind") != "knowledge_base":
                problems.append(f"recommendation {rid} claims the knowledge base without a knowledge-base record")
            if basis == "general_guidance" and (rec.get("provenance") or {}).get("kind") != "general_guidance":
                problems.append(f"recommendation {rid} is general guidance but not labelled so")
        check_refs(f"recommendation {rid}", rec.get("refs"))
    return problems
