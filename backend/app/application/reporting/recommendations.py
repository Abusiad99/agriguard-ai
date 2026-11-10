"""Deterministic recommendation engine for reports (v2).

Every recommendation comes from a named rule and carries:
- a time horizon (immediate, short-term, long-term) and an action type (inspection,
  monitoring, environment, expert, treatment, prevention, data);
- priority, reason, the evidence (facts from the report), timing, objective, warnings;
- its *basis*, one of:
    reference       — the action rests on a verified source (refs list it);
    knowledge_base  — copied from the knowledge base (with any references attached there);
    agriguard_rule  — a procedural rule triggered by this report's data (retake a photo,
                      track the plant, inspect cells with confirmed cases), no agronomic claim;
    general_guidance — general advice without a verified source, labelled as such.
Context used: crop, predicted disease, estimated severity, measured area, weather at scan
time, the area's observations and estimates, recorded treatments and earlier scans.

Never generated here: product names, concentrations, doses, or claims that a treatment
works. Treatment instructions are copied verbatim from the knowledge base and shown only
when the knowledge base cites a source (Treatment.may_display_instructions); otherwise
the user is referred to their agricultural authority.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from app.application.reporting.content import HORIZONS, provenance
from app.application.reporting.i18n import day, humanize, num, t
from app.application.reporting.references import Citations
from app.core.config import CONFIGS_DIR

TYPES = ("inspection", "monitoring", "environment", "expert", "treatment", "prevention", "data")
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_RULES_PATH = CONFIGS_DIR / "reports" / "rules.json"
_DEFAULT_RULES = {"rules_version": "report-rules-v3", "rescan_days_disease": 7, "rescan_days_healthy": 30,
                  "region_radius_cells": 2, "high_risk_levels": ["high", "critical"], "recent_positive_days": 30,
                  "close_margin_pp": 15, "min_class_precision_pct": 80, "spray_wind_min_mph": 3,
                  "spray_wind_max_mph": 8, "spray_rain_probability_pct": 60, "follow_up_gap_factor": 2,
                  "max_history_scans": 4}


def _rescan_timing(locale: str, days: int) -> str:
    # Arabic counts above ten take a different noun form; digits follow the report language.
    return t(locale, "rec.rescan.timing_many" if days > 10 else "rec.rescan.timing", days=num(days, locale, 0))


def load_rules() -> dict:
    try:
        data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**_DEFAULT_RULES, **{k: v for k, v in data.items() if not k.startswith("_")}}


class _Recs:
    def __init__(self, locale: str, rules_version: str, cites: Citations):
        self.locale, self.items, self.rules_version, self.cites = locale, [], rules_version, cites

    def add(self, rule: str, horizon: str, kind: str, priority: str, title: str, reason: str, objective: str, timing: str,
            basis: str, evidence: Optional[List[dict]] = None, warnings: Optional[List[str]] = None,
            prov: Optional[dict] = None, refs: Optional[List[str]] = None, details: Optional[dict] = None,
            general_practice: bool = False) -> None:
        assert horizon in HORIZONS and kind in TYPES, (horizon, kind)
        if basis == "reference" and not refs:
            # A sourced rule whose source is missing from the catalog degrades honestly.
            basis, prov = "general_guidance", provenance("general_guidance", rule)
        if prov is None:
            prov = (provenance("reference", f"{self.rules_version}:{rule}") if basis == "reference"
                    else provenance("general_guidance", rule) if basis == "general_guidance"
                    else provenance("rule", f"{self.rules_version}:{rule}"))
        self.items.append({
            "id": f"rec-{len(self.items) + 1}", "rule": rule, "horizon": horizon,
            "horizon_label": t(self.locale, f"rec.hz.{horizon}"), "category": kind,
            "category_label": t(self.locale, f"rec.type.{kind}"), "priority": priority,
            "priority_label": t(self.locale, f"rec.pri.{priority}"), "title": title, "reason": reason,
            "objective": objective, "timing": timing, "basis": basis, "basis_label": t(self.locale, f"rec.basis.{basis}"),
            "refs": list(dict.fromkeys(refs or [])),
            "evidence": [{"key": e.get("key"), "label": e.get("label"), "display": e.get("display")} for e in (evidence or []) if e],
            "warnings": [w for w in (warnings or []) if w], "provenance": prov,
            **({"details": details} if details else {}),
            **({"general_practice": True} if general_practice else {}),
        })

    def result(self) -> List[dict]:
        order = {h: i for i, h in enumerate(HORIZONS)}
        items = sorted(self.items, key=lambda r: (order[r["horizon"]], PRIORITY_ORDER[r["priority"]]))
        for i, item in enumerate(items):
            item["id"] = f"rec-{i + 1}"
        return items


def _find(content: dict, key: str) -> Optional[dict]:
    for f in content.get("key_facts", []):
        if f.get("key") == key:
            return f
    for sec in content.get("sections", []):
        for f in sec.get("facts", []):
            if f.get("key") == key:
                return f
    return None


def _d(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


# ------------------------------------------------------------------ shared rule blocks
def _kb_treatments(r: _Recs, ev: dict, disease_label: str, uncertain: bool, severe: bool,
                   recent: Optional[List[dict]] = None) -> None:
    loc = r.locale
    for tr in ev.get("kb_treatments", []):
        warnings = []
        if tr["category"] == "chemical":
            warnings.append(t(loc, "rec.kb_treatment.warning_chemical"))
        if uncertain:
            warnings.append(t(loc, "rec.kb_treatment.warning_confirm"))
        if tr.get("safety_notes"):
            warnings.append(tr["safety_notes"])
        same = [x for x in recent or [] if x.get("category") == tr["category"]]
        if same:
            warnings.append(t(loc, "rec.kb_treatment.warning_recent", date=day(same[0]["applied_on"], loc)))
        refs = r.cites.cite_kb(f"treatment:{tr['id']}")
        if tr.get("citation") and not refs:
            warnings.append(t(loc, "rec.kb_treatment.citation_unstructured"))
        r.add("R-KB-TREATMENT", "short_term", "treatment", "high" if severe and not uncertain else "medium",
              t(loc, "rec.kb_treatment.title", category=t(loc, f"v.category.{tr['category']}")),
              t(loc, "rec.kb_treatment.reason", disease=disease_label), t(loc, "rec.kb_treatment.objective"),
              t(loc, "rec.timing.after_confirmation") if uncertain else t(loc, "rec.timing.this_week"),
              "knowledge_base", warnings=warnings, refs=refs,
              prov=provenance("knowledge_base", "treatments", f"treatments/{tr['id']}", version=tr.get("version"),
                              citation=tr.get("citation")),
              details={"text": tr["instructions"] if tr["displayable"] else t(loc, "v.referral_only"),
                       "lang": "en" if tr["displayable"] else loc, "citation": tr.get("citation"),
                       "verbatim_from_knowledge_base": tr["displayable"]})


def _practice_items(r: _Recs, subjects: List[str]) -> List[dict]:
    items = []
    for subject in subjects:
        refs = r.cites.cite(f"guidance:{subject}")
        items.append({"text": t(r.locale, f"rec.practice.{subject}"), "refs": refs,
                      "basis": "reference" if refs else "general_guidance"})
    return items


def _prevention(r: _Recs, disease_label: Optional[str], spread: bool, uncertain: bool) -> None:
    """General disease-prevention practice (UMN Extension), never presented as disease-specific."""
    loc = r.locale
    target = disease_label or t(loc, "rec.practice.any_disease")
    if spread:
        items = _practice_items(r, ["remove_infected", "sanitation"])
        r.add("R-PREVENT-SPREAD", "short_term", "prevention", "medium", t(loc, "rec.prevent_spread.title"),
              t(loc, "rec.prevent_spread.reason", disease=target), t(loc, "rec.prevent_spread.objective"),
              t(loc, "rec.timing.after_confirmation") if uncertain else t(loc, "rec.timing.dry_no_rain"),
              "reference", refs=[x for i in items for x in i["refs"]],
              warnings=[t(loc, "rec.practice.not_specific", disease=target)],
              details={"items": items}, general_practice=True)
    items = _practice_items(r, ["irrigation", "airflow", "rotation"] + (["resistant_varieties"] if spread else []))
    r.add("R-PREVENT-LONG", "long_term", "prevention", "low", t(loc, "rec.prevent_long.title"),
          t(loc, "rec.prevent_long.reason"), t(loc, "rec.prevent_long.objective"), t(loc, "rec.timing.season"),
          "reference", refs=[x for i in items for x in i["refs"]],
          warnings=[t(loc, "rec.practice.not_specific", disease=target)], details={"items": items}, general_practice=True)


# ======================================================================== diagnosis
def diagnosis_recommendations(ev: dict, content: dict, locale: str, cites: Optional[Citations] = None) -> List[dict]:
    rules = ev["rules"]
    cites = cites or Citations(locale)
    r = _Recs(locale, rules["rules_version"], cites)
    d, kb = ev["diagnosis"], ev.get("kb_disease")
    disease = not d["is_healthy"]
    conf, margin = _find(content, "confidence"), _find(content, "margin")
    precision = _find(content, "test_precision")
    close_call = bool(margin and margin.get("available") and margin["value"] is not None
                      and margin["value"] < float(rules["close_margin_pp"]))
    weak_class = bool(precision and precision.get("available") and precision["value"] is not None
                      and precision["value"] * 100 < float(rules["min_class_precision_pct"]))
    uncertain = d["low_confidence"] or close_call or weak_class
    tracked = ev.get("tracked") or {}
    history = tracked.get("history") or []
    disease_label = humanize(kb["name"]) if kb else humanize(d["predicted_condition"])

    # --- immediate
    if uncertain:
        triggers = []
        if d["low_confidence"]:
            triggers.append(t(locale, "rec.confirm.trigger_low", confidence=conf["display"] if conf else ""))
        if close_call:
            triggers.append(t(locale, "rec.confirm.trigger_close", margin=margin["display"]))
        if weak_class:
            triggers.append(t(locale, "rec.confirm.trigger_precision", precision=precision["display"]))
        r.add("R-DX-CONFIRM", "immediate", "expert", "high", t(locale, "rec.confirm.title"),
              t(locale, "rec.confirm.reason", triggers="; ".join(triggers)), t(locale, "rec.confirm.objective"),
              t(locale, "rec.timing.before_treatment"), "reference", [conf, margin, precision],
              refs=cites.cite("guidance:confirm_before_pesticide") + cites.cite("guidance:sample_stages"))
    if disease and not kb:
        r.add("R-DX-NOT-IN-KB", "immediate", "expert", "high", t(locale, "rec.not_in_kb.title"), t(locale, "rec.not_in_kb.reason"),
              t(locale, "rec.not_in_kb.objective"), t(locale, "rec.timing.before_treatment"), "agriguard_rule",
              [_find(content, "condition")])
    q = d.get("quality") or {}
    if q.get("issues"):
        issues = ", ".join(t(locale, f"v.quality.{i}") for i in q["issues"])
        r.add("R-DX-RETAKE", "immediate", "data", "medium" if uncertain else "low", t(locale, "rec.retake.title"),
              t(locale, "rec.retake.reason", issues=issues), t(locale, "rec.retake.objective"), t(locale, "rec.retake.timing"),
              "agriguard_rule", [_find(content, "quality_issues")])
    if history and history[-1].get("condition") and history[-1]["condition"] != d["predicted_condition"]:
        prev = history[-1]
        r.add("R-DX-LABEL-CHANGED", "immediate", "data", "medium", t(locale, "rec.label_changed.title"),
              t(locale, "rec.label_changed.reason", prev=humanize(prev["condition"]), date=day(prev["diagnosed_at"], locale),
                now=humanize(d["predicted_condition"])),
              t(locale, "rec.label_changed.objective"), t(locale, "rec.timing.before_treatment"), "agriguard_rule",
              [_find(content, "condition")])
    # Spraying conditions: the same assessment as the diagnosis page and the scan PDF
    # (weather_guidance.py). No recommendation without measurements behind it.
    from app.application.reporting.weather_guidance import guidance as weather_guidance

    wx = weather_guidance(d.get("weather"), rules, locale, cites, applicable=disease)
    if wx["verdict"] in ("within_limits", "wait", "incomplete"):
        problems = [i["text"] for i in wx["items"] if i["status"] in ("caution", "unavailable")]
        r.add("R-DX-SPRAY-CONDITIONS", "immediate", "environment", "low" if wx["verdict"] == "within_limits" else "medium",
              t(locale, f"wx.rec.title.{wx['verdict']}"), " ".join([wx["summary"]] + problems),
              t(locale, "wx.rec.objective"), t(locale, "wx.rec.timing"), "reference",
              [_find(content, "wind"), _find(content, "rain_probability")], refs=wx["refs"],
              warnings=[t(locale, "wx.label_first")])

    # --- short term
    if disease and kb:
        recent = [x for x in tracked.get("recent_treatments") or []]
        _kb_treatments(r, ev, disease_label, uncertain, d.get("severity_level") == "severe", recent)
    if d.get("severity_level") == "severe":
        r.add("R-DX-SEVERE", "short_term", "expert", "medium", t(locale, "rec.severe.title"), t(locale, "rec.severe.reason"),
              t(locale, "rec.severe.objective"), t(locale, "rec.timing.this_week"), "agriguard_rule", [_find(content, "severity")],
              warnings=[t(locale, "lim.severity_is_estimate")])
    area = ev.get("area") or {}
    if area.get("positives"):
        r.add("R-DX-AREA-CASES", "short_term", "inspection", "medium", t(locale, "rec.area_cases.title"),
              t(locale, "rec.area_cases.reason", n=num(area["positives"], locale, 0)), t(locale, "rec.area_cases.objective"),
              t(locale, "rec.timing.this_week"), "agriguard_rule", [_find(content, "positives")])
    diagnosed = _d(d["diagnosed_at"]) if d.get("diagnosed_at") else None
    recent_tr = [x for x in tracked.get("recent_treatments") or []
                 if diagnosed and 0 <= (diagnosed - _d(x["applied_on"])).days <= 14]
    if recent_tr:
        r.add("R-DX-RECENT-TREATMENT", "short_term", "monitoring", "medium", t(locale, "rec.recent_treatment.title"),
              t(locale, "rec.recent_treatment.reason", name=recent_tr[0].get("name"), date=day(recent_tr[0]["applied_on"], locale)),
              t(locale, "rec.recent_treatment.objective"), _rescan_timing(locale, rules["rescan_days_disease"]), "agriguard_rule")
    same = [h for h in history if h.get("condition") == d["predicted_condition"]]
    if disease and len(same) >= 2 and (tracked.get("latest_status") in ("worsening", "stable", "inconclusive", None)):
        r.add("R-DX-PERSISTENT", "short_term", "expert", "medium", t(locale, "rec.persistent.title"),
              t(locale, "rec.persistent.reason", n=num(len(same) + 1, locale, 0)), t(locale, "rec.persistent.objective"),
              t(locale, "rec.timing.this_week"), "agriguard_rule", [_find(content, "recovery_status")])
    days = int(rules["rescan_days_disease"] if disease else rules["rescan_days_healthy"])
    timing = _rescan_timing(locale, days)
    if tracked.get("next_reminder"):
        timing = day(tracked["next_reminder"], locale)
    scouting = cites.cite("guidance:scouting") if disease else []
    r.add("R-RESCAN", "short_term", "monitoring", "medium" if disease else "low", t(locale, "rec.rescan.title"),
          t(locale, "rec.rescan.reason_disease" if disease else "rec.rescan.reason_healthy"), t(locale, "rec.rescan.objective"),
          timing, "reference" if scouting else "agriguard_rule", [_find(content, "condition")], refs=scouting)
    if disease and not tracked:
        r.add("R-TRACK", "short_term", "monitoring", "low", t(locale, "rec.track.title"), t(locale, "rec.track.reason"),
              t(locale, "rec.track.objective"), t(locale, "rec.timing.now"), "agriguard_rule")

    # --- prevention (short and long term)
    _prevention(r, disease_label if disease else None, spread=disease, uncertain=uncertain)
    return r.result()


# =================================================================== plant progress
def plant_progress_recommendations(ev: dict, content: dict, locale: str, cites: Optional[Citations] = None) -> List[dict]:
    from app.application.reporting.builders import follow_up_gaps

    rules = ev["rules"]
    cites = cites or Citations(locale)
    r = _Recs(locale, rules["rules_version"], cites)
    status = ev["assessment"]["status"]
    scans = ev["scans"]
    latest = scans[-1] if scans else None
    latest_disease = bool(latest and not latest["is_healthy"])
    gaps = {g["code"]: g for g in follow_up_gaps(scans, ev["treatments"], ev.get("reminders") or [], rules, ev.get("today"))}

    if ev.get("overdue_reminders"):
        r.add("R-PP-OVERDUE", "immediate", "monitoring", "high", t(locale, "rec.overdue.title"),
              t(locale, "rec.overdue.reason", n=num(ev["overdue_reminders"], locale, 0)), t(locale, "rec.overdue.objective"),
              t(locale, "rec.timing.now"), "agriguard_rule")
    if "follow_up_due" in gaps:
        g = gaps["follow_up_due"]
        r.add("R-PP-FOLLOWUP-DUE", "immediate", "monitoring", "high", t(locale, "rec.followup_due.title"),
              t(locale, "rec.followup_due.reason", days=num(g["days"], locale, 0), date=day(g["last_date"], locale)),
              t(locale, "rec.followup_due.objective"), t(locale, "rec.timing.now"),
              "reference" if latest_disease else "agriguard_rule", refs=cites.cite("guidance:scouting") if latest_disease else [])
    if "no_scan_after_treatment" in gaps:
        g = gaps["no_scan_after_treatment"]
        r.add("R-PP-AFTER-TREATMENT", "immediate", "monitoring", "medium", t(locale, "rec.after_treatment.title"),
              t(locale, "rec.after_treatment.reason", date=day(g["treatment_date"], locale)), t(locale, "rec.after_treatment.objective"),
              _rescan_timing(locale, rules["rescan_days_disease"]), "agriguard_rule")
    if status == "worsening":
        r.add("R-PP-WORSENING", "immediate", "expert", "high", t(locale, "rec.worsening.title"), t(locale, "rec.worsening.reason"),
              t(locale, "rec.worsening.objective"), t(locale, "rec.timing.this_week"), "agriguard_rule", [_find(content, "area_change")])
    if latest and latest_disease and latest.get("low_confidence"):
        r.add("R-PP-CONFIRM", "immediate", "expert", "high", t(locale, "rec.confirm.title"),
              t(locale, "rec.confirm.reason", triggers=t(locale, "rec.confirm.trigger_low", confidence=num(latest.get("confidence"), locale))),
              t(locale, "rec.confirm.objective"), t(locale, "rec.timing.before_treatment"), "reference",
              refs=cites.cite("guidance:confirm_before_pesticide"))
    if status in ("inconclusive", "insufficient_data"):
        reasons = ", ".join(t(locale, f"rl.{code}") for code in ev["assessment"].get("limitations") or [])
        r.add("R-PP-COMPARABLE", "short_term", "data", "medium", t(locale, "rec.comparable.title"),
              t(locale, "rec.comparable.reason", reasons=reasons or t(locale, "chrome.missing")),
              t(locale, "rec.comparable.objective"), _rescan_timing(locale, rules["rescan_days_disease"]), "agriguard_rule",
              [_find(content, "recovery_status")])
    if "unmeasured_scans" in gaps:
        r.add("R-PP-MEASUREMENT", "short_term", "data", "low", t(locale, "rec.measurement.title"),
              t(locale, "rec.measurement.reason", n=num(gaps["unmeasured_scans"]["n"], locale, 0)),
              t(locale, "rec.measurement.objective"), t(locale, "rec.timing.next_scan"), "agriguard_rule")
    if latest_disease and ev.get("kb_disease"):
        _kb_treatments(r, ev, humanize(ev["kb_disease"]["name"]), bool(latest.get("low_confidence")), False,
                       sorted(ev["treatments"], key=lambda x: str(x["applied_on"]), reverse=True))
    if status in ("improving", "stable", "worsening") and "follow_up_due" not in gaps:
        scouting = cites.cite("guidance:scouting") if latest_disease else []
        r.add("R-RESCAN", "short_term", "monitoring", "medium" if status != "improving" else "low", t(locale, "rec.rescan.title"),
              t(locale, "rec.rescan.reason_disease" if latest_disease else "rec.rescan.reason_healthy"), t(locale, "rec.rescan.objective"),
              _rescan_timing(locale, rules["rescan_days_disease" if latest_disease else "rescan_days_healthy"]),
              "reference" if scouting else "agriguard_rule", [_find(content, "recovery_status")], refs=scouting)
    if latest_disease:
        _prevention(r, humanize(latest["condition"]), spread=True, uncertain=bool(latest.get("low_confidence")))
    return r.result()


# ==================================================================== outbreak area
def outbreak_recommendations(ev: dict, content: dict, locale: str, cites: Optional[Citations] = None) -> List[dict]:
    from app.application.reporting.builders import inspection_priorities

    rules = ev["rules"]
    cites = cites or Citations(locale)
    r = _Recs(locale, rules["rules_version"], cites)
    cells = ev["region"].get("cells", [])
    pred = ev.get("prediction")
    pri = inspection_priorities(cells, rules, ev["area"]["id"])
    if pri:
        listed = [f"{num(p['cell']['area']['bounds']['south'], locale, 2)}°, {num(p['cell']['area']['bounds']['west'], locale, 2)}°"
                  for p in pri[:3]]
        strong = any(x["code"] in ("positives", "high_estimate") for p in pri for x in p["reasons"])
        r.add("R-OA-INSPECT", "immediate", "inspection", "high" if strong else "medium", t(locale, "rec.inspect.title"),
              t(locale, "rec.inspect.reason", n=num(len(pri), locale, 0), cells="; ".join(listed)),
              t(locale, "rec.inspect.objective"),
              t(locale, "rec.timing.forecast", period=_find(content, "forecast_period")["display"])
              if pred and _find(content, "forecast_period") else t(locale, "rec.timing.this_week"),
              "agriguard_rule", [_find(content, "region_positives"), _find(content, "count.no_inspections")],
              warnings=[t(locale, "rec.inspect.warning")])
    for s in ev.get("suitability") or []:
        if s["status"] == "met":
            refs = cites.cite(f"rule:{s.get('rule')}") if s.get("reference_id") else []
            r.add("R-OA-SUITABILITY", "immediate", "monitoring", "medium", t(locale, "rec.suitability.title"),
                  t(locale, "rec.suitability.reason", rule=humanize(s.get("rule"))), t(locale, "rec.suitability.objective"),
                  t(locale, "rec.timing.ongoing"), "reference" if refs else "agriguard_rule", [_find(content, f"suit.{s['profile_id']}")],
                  refs=refs, prov=provenance("sourced_rule", s["profile_id"], citation=s.get("source")))
    positives = sum(c.get("positives") or 0 for c in cells)
    if positives:
        r.add("R-OA-SCOUTING", "short_term", "monitoring", "medium", t(locale, "rec.scouting.title"),
              t(locale, "rec.scouting.reason", n=num(positives, locale, 0)), t(locale, "rec.scouting.objective"),
              t(locale, "rec.timing.weekly"), "reference", [_find(content, "region_positives")], refs=cites.cite("guidance:scouting"))
    gaps = sum(1 for p in pri for x in p["reasons"] if x["code"] == "coverage_gap")
    if gaps:
        r.add("R-OA-COVERAGE", "short_term", "data", "medium", t(locale, "rec.coverage.title"),
              t(locale, "rec.coverage.reason", n=num(gaps, locale, 0)), t(locale, "rec.coverage.objective"),
              t(locale, "rec.timing.this_week"), "agriguard_rule", [_find(content, "count.no_inspections")])
    if not (pred and pred.get("status") == "ok"):
        r.add("R-OA-NO-ESTIMATE", "short_term", "data", "low", t(locale, "rec.no_estimate.title"), t(locale, "rec.no_estimate.reason"),
              t(locale, "rec.no_estimate.objective"), t(locale, "rec.timing.now"), "agriguard_rule", [_find(content, "risk_level")])
    if ev.get("data_gap"):
        r.add("R-OA-DATA-GAP", "long_term", "data", "low", t(locale, "rec.data_gap.title"), t(locale, "rec.data_gap.reason"),
              t(locale, "rec.data_gap.objective"), t(locale, "rec.timing.ongoing"), "agriguard_rule", [_find(content, "inspections")])
    if positives or (pred and pred.get("status") == "ok" and pred.get("risk_level") in rules["high_risk_levels"]):
        _prevention(r, humanize(ev.get("disease")), spread=False, uncertain=False)
    return r.result()
