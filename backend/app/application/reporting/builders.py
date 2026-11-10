"""Report builders: collected evidence (plain data read from the database and models) ->
structured report content (schema v2, see content.py). Pure functions: the same evidence
always gives the same report, which is what makes stored reports reproducible.

Rules that keep the content honest:
- predictions are labelled as predictions, estimates as estimates, measurements carry
  the model that made them, test-set results are labelled as such;
- model confidence is never presented as accuracy; where the model's own held-out test
  results exist they are shown next to it, with the caveat that field photos differ;
- the attention heatmap (Grad-CAM) is an explanation of the classifier, never a lesion
  outline or a measured area; only the segmentation model measures area;
- severity is never "critical" and measured area is never turned into a grade: no
  validated grading scale is configured;
- knowledge-base text is copied verbatim with its language; claims made by AgriGuard's
  own rules cite a verified reference (references.py) or are labelled general guidance;
- every number is computed here from stored values, with its inputs named;
- anything missing becomes an explicit "not available" fact with the reason.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from app.application.reporting.content import fact, missing_information, provenance, section, statement, unavailable
from app.application.reporting.i18n import day, humanize, num, pct, t
from app.application.reporting.references import Citations
from app.application.reporting.weather_guidance import guidance as weather_guidance

KB_LANG = "en"  # knowledge-base text is maintained in English
_SEVERITY_RANK = {"mild": 1, "moderate": 2, "severe": 3}


class Ctx:
    def __init__(self, locale: str):
        self.locale = locale

    def t(self, key: str, **kw) -> str:
        return t(self.locale, key, **kw)

    def num(self, v, d: int = 1) -> str:
        return num(v, self.locale, d)

    def pct(self, v, d: int = 1) -> str:
        return pct(v, self.locale, d)

    def day(self, v) -> str:
        return day(v, self.locale)

    def pp(self, v, d: int = 1) -> str:
        """Signed percentage points."""
        if v is None:
            return self.t("chrome.missing")
        sign = "+" if v > 0 else ("−" if v < 0 else "±")
        return f"{sign}{self.num(abs(v), d)} {self.t('unit.pp')}"


def _model_prov(kind: str, model: Optional[dict], record: Optional[str] = None) -> dict:
    model = model or {}
    name = model.get("name") or "model"
    return provenance(kind, f"{name}@{model.get('version') or 'unknown'}", record)


def _kb_prov(entity: str, row: dict) -> dict:
    return provenance("knowledge_base", entity, f"{entity}/{row['id']}", version=row.get("version"),
                      citation=row.get("citation"))


def _d(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _label(plant: Optional[str], condition: Optional[str], c: Ctx) -> str:
    cond = c.t("v.healthy") if condition == "healthy" else humanize(condition)
    return f"{humanize(plant)} — {cond}" if plant else cond


def _finish(content: dict, cites: Citations, c: Ctx, chapter_order: List[str], titles: Optional[dict] = None) -> dict:
    content["missing"] = missing_information(content)
    content["chapters"] = [{"id": ch, "title": (titles or {}).get(ch) or c.t(f"ch.{ch}")} for ch in chapter_order]
    content["references"] = cites.to_list()
    return content


# =============================================================================== diagnosis
def build_diagnosis(ev: dict, locale: str, cites: Optional[Citations] = None) -> dict:
    c = Ctx(locale)
    cites = cites or Citations(locale)
    rules = ev["rules"]
    d, clf, seg, kb = ev["diagnosis"], ev.get("classifier") or {}, ev.get("segmentation"), ev.get("kb_disease")
    rec_id = f"diagnoses/{d['id']}"
    disease = not d["is_healthy"]
    condition = humanize((kb or {}).get("name")) or (c.t("v.healthy") if d["is_healthy"] else humanize(d["predicted_condition"]))
    plant = humanize(d.get("plant_name")) or c.t("chrome.missing")
    clf_prov = _model_prov("model", clf, rec_id)
    seg_ok = bool(seg and seg.get("status") == "ok")
    seg_prov = _model_prov("model_measurement", {"name": (seg or {}).get("model_name"), "version": (seg or {}).get("model_version")},
                           f"diagnosis_segmentations/{(seg or {}).get('id')}") if seg else None
    sections: List[dict] = []
    media: List[dict] = []
    charts: List[dict] = []
    limitations = ["lim.prediction_not_diagnosis", "lim.confidence_not_accuracy", "lim.classifier_scope"]
    ref_conf = cites.cite("method:confidence")
    ref_field = cites.cite("method:test_vs_field")
    ref_gradcam = cites.cite("method:gradcam")

    # ------------------------------------------------------------------ 2. condition
    f_plant = fact("plant", c.t("f.plant"), d.get("plant_name"), plant, clf_prov)
    f_condition = fact("condition", c.t("f.condition"), d["predicted_condition"], condition, clf_prov,
                       note=c.t("note.prediction"))
    f_conf = fact("confidence", c.t("f.confidence"), d["confidence"], c.pct(d["confidence"]), clf_prov, unit="%",
                  note=c.t("note.confidence_not_accuracy"), refs=ref_conf)
    ident = [f_plant, f_condition, f_conf,
             fact("low_confidence", c.t("f.low_confidence"), d["low_confidence"],
                  c.t("v.yes") if d["low_confidence"] else c.t("v.no"), clf_prov)]
    if kb:
        ident.append(fact("kb_match", c.t("f.kb_match"), kb["name"], humanize(kb["name"]), _kb_prov("diseases", kb), lang=KB_LANG))
    elif disease:
        ident.append(unavailable("kb_match", c.t("f.kb_match"), c.t("u.no_kb"), "no_kb"))
    sections.append(section("identification", c.t("sec.identification"), ident, chapter="condition"))

    # ------------------------------------------------------------------- 3. evidence
    top = d.get("top_predictions")
    alts = [p for p in (top or []) if not (p.get("condition") == d["predicted_condition"] and p.get("plant") == d.get("plant_name"))]
    second = alts[0] if alts else None
    margin = round(d["confidence"] - second["confidence"], 1) if second and d.get("confidence") is not None else None
    close_call = margin is not None and margin < float(rules["close_margin_pp"])
    test = clf.get("test") or {}
    own_key = f"{d.get('plant_name')}___{d['predicted_condition']}"
    own_metrics = (test.get("classes") or {}).get(own_key)

    reasoning = [statement(c.t("st.dx.ranked", condition=condition, confidence=c.pct(d["confidence"]),
                                n=c.num(clf.get("num_classes"), 0) if clf.get("num_classes") else c.t("chrome.missing")),
                           "model", clf_prov, evidence=["condition", "confidence"])]
    if second:
        reasoning.append(statement(c.t("st.dx.second", alt=_label(second.get("plant"), second.get("condition"), c),
                                       confidence=c.pct(second["confidence"]), margin=c.num(margin)),
                                   "model", clf_prov, evidence=["margin"]))
        if close_call:
            reasoning.append(statement(c.t("st.dx.close_call", threshold=c.num(rules["close_margin_pp"], 0)), "rule",
                                       provenance("rule", f"{rules['rules_version']}:close_margin_pp"), evidence=["margin"]))
    elif top is None:
        reasoning.append(statement(c.t("st.dx.no_alternatives_stored"), "missing", provenance("system")))
    if own_metrics:
        reasoning.append(statement(c.t("st.dx.test_metrics", condition=condition, n=c.num(own_metrics.get("support"), 0),
                                       recall=c.pct((own_metrics.get("recall") or 0) * 100, 0),
                                       precision=c.pct((own_metrics.get("precision") or 0) * 100, 0)),
                                   "evaluation", _model_prov("model_evaluation", clf, test.get("record")),
                                   evidence=["test_recall", "test_precision"]))
    else:
        reasoning.append(statement(c.t("st.dx.no_test_metrics"), "missing", provenance("system")))
    reasoning.append(statement(c.t("st.dx.confidence_vs_accuracy"), "reference", provenance("reference", "literature"),
                               refs=ref_conf + ref_field))
    if d.get("gradcam_area_pct") is not None:
        reasoning.append(statement(c.t("st.dx.gradcam", area=c.pct(d["gradcam_area_pct"])), "estimate",
                                   provenance("model_estimate", "grad-cam", rec_id), refs=ref_gradcam, evidence=["area_estimate"]))
    if seg_ok and seg.get("affected_pct") is not None:
        reasoning.append(statement(c.t("st.dx.segmentation", n=c.num(len(seg.get("regions") or []), 0),
                                       area=c.pct(seg["affected_pct"]), affected=c.num(seg.get("affected_pixels"), 0),
                                       plant_px=c.num(seg.get("plant_pixels"), 0)),
                                   "measured", seg_prov, evidence=["area_measured", "regions"]))
    elif seg_ok:
        reasoning.append(statement(c.t(f"u.{_area_reason(seg)}"), "missing", provenance("system")))
    else:
        reasoning.append(statement(c.t("st.dx.no_segmentation"), "missing", provenance("system")))
    if kb and kb.get("symptoms"):
        kb_refs = cites.cite_kb(f"disease:{kb.get('plant')}/{kb['name']}")
        reasoning.append(statement(c.t("st.dx.kb_symptoms", disease=humanize(kb["name"])), "knowledge",
                                   _kb_prov("diseases", kb), refs=kb_refs, evidence=["symptoms"]))
    q = d.get("quality") or {}
    if q.get("issues"):
        reasoning.append(statement(c.t("st.dx.quality", issues=", ".join(c.t(f"v.quality.{i}") for i in q["issues"])), "rule",
                                   provenance("rule", "image_quality_checks", rec_id), evidence=["quality_issues"]))
    sections.append(section("reasoning", c.t("sec.reasoning"), [], chapter="evidence", statements=reasoning,
                            note=c.t("note.reasoning")))

    # model reliability: confidence next to the model's own test results
    rel = [f_conf]
    if second:
        rel.append(fact("margin", c.t("f.margin"), margin, f"{c.num(margin)} {c.t('unit.pp')}",
                        provenance("rule", "confidence_margin", rec_id), unit="pp",
                        note=c.t("note.close_call") if close_call else None))
    else:
        rel.append(unavailable("margin", c.t("f.margin"), c.t("u.no_alternatives" if top is None else "u.single_candidate"),
                               "older_scan" if top is None else "single_candidate"))
    test_prov = _model_prov("model_evaluation", clf, test.get("record"))
    if own_metrics:
        rel += [fact("test_precision", c.t("f.test_precision"), own_metrics.get("precision"),
                     c.pct((own_metrics.get("precision") or 0) * 100, 0), test_prov, unit="%", note=c.t("note.test_precision")),
                fact("test_recall", c.t("f.test_recall"), own_metrics.get("recall"),
                     c.pct((own_metrics.get("recall") or 0) * 100, 0), test_prov, unit="%", note=c.t("note.test_recall")),
                fact("test_support", c.t("f.test_support"), own_metrics.get("support"), c.num(own_metrics.get("support"), 0), test_prov)]
    else:
        rel.append(unavailable("test_precision", c.t("f.test_precision"), c.t("u.no_test_metrics"), "no_test_metrics"))
    if test.get("accuracy") is not None:
        rel.append(fact("test_accuracy", c.t("f.test_accuracy"), test["accuracy"], c.pct(test["accuracy"] * 100, 1), test_prov,
                        unit="%", note=c.t("note.test_accuracy", n=c.num(test.get("n_test"), 0)), refs=ref_field))
    sections.append(section("reliability", c.t("sec.reliability"), rel, chapter="evidence",
                            text=c.t("text.reliability"), text_provenance=provenance("reference", "literature"),
                            refs=ref_conf + ref_field))

    # detected findings (segmentation, measured)
    if seg_ok:
        regions = seg.get("regions") or []
        classes = {cl.get("name"): cl for cl in seg.get("classes") or []}
        plant_px = seg.get("plant_pixels") or 0
        rows = []
        for name, px in sorted((seg.get("class_pixels") or {}).items(), key=lambda kv: -kv[1]):
            kind = (classes.get(name) or {}).get("kind")
            if kind != "disease" or not px:
                continue
            reg = [r for r in regions if r.get("label") == name]
            mean_conf = (sum(r.get("mean_confidence") or 0 for r in reg) / len(reg)) if reg else None
            rows.append({"id": f"class-{name}", "cells": [
                fact("class", c.t("f.seg_class"), name, humanize(name), seg_prov),
                fact("regions", c.t("f.regions"), len(reg), c.num(len(reg), 0), seg_prov),
                fact("pixels", c.t("f.pixels"), px, c.num(px, 0), seg_prov, unit="px"),
                # Same validity rule as the measured area: no percentage without a usable denominator.
                (fact("share", c.t("f.share_of_plant"), round(px / plant_px * 100, 2), c.pct(px / plant_px * 100), seg_prov, unit="%")
                 if plant_px and seg.get("affected_pct") is not None
                 else unavailable("share", c.t("f.share_of_plant"), c.t(f"u.{_area_reason(seg)}"), _area_reason(seg))),
                (fact("mean_conf", c.t("f.seg_confidence"), round(mean_conf, 3), c.pct(mean_conf * 100, 0), seg_prov, unit="%")
                 if mean_conf is not None else unavailable("mean_conf", c.t("f.seg_confidence"), "—", "no_regions"))]})
        facts = [fact("regions", c.t("f.regions"), len(regions), c.num(len(regions), 0), seg_prov)]
        if regions:
            largest = max(regions, key=lambda r: r.get("pixels", 0))
            facts.append(fact("largest_region", c.t("f.largest_region"), largest.get("pixels"),
                              f"{humanize(largest.get('label'))} — {c.num(largest.get('pixels'), 0)} px", seg_prov))
        if seg.get("mean_confidence") is not None:
            facts.append(fact("seg_confidence", c.t("f.seg_confidence"), seg["mean_confidence"],
                              c.pct(seg["mean_confidence"] * 100, 0), seg_prov, unit="%"))
        if seg.get("mean_uncertainty") is not None:
            facts.append(fact("seg_uncertainty", c.t("f.seg_uncertainty"), seg["mean_uncertainty"],
                              c.pct(seg["mean_uncertainty"] * 100, 0), seg_prov, unit="%", note=c.t("note.uncertainty")))
        sections.append(section("findings", c.t("sec.findings"), facts, chapter="evidence", rows=rows or None,
                                note=c.t("note.findings")))
    else:
        code = _area_reason(seg) if seg else "no_segmentation_model"
        sections.append(section("findings", c.t("sec.findings"), [unavailable("regions", c.t("f.regions"), c.t(f"u.{code}"), code)],
                                chapter="evidence"))

    # alternatives the evidence does not rule out
    if top is None:
        sections.append(section("alternatives", c.t("sec.alternatives"),
                                [unavailable("alternatives", c.t("sec.alternatives"), c.t("u.no_alternatives"), "older_scan")],
                                chapter="evidence"))
    else:
        rows = []
        for i, p in enumerate(alts):
            key = f"{p.get('plant')}___{p.get('condition')}"
            m = (test.get("classes") or {}).get(key)
            alt_kb = (ev.get("alt_kb") or {}).get(key)
            rows.append({"id": f"alt-{i}", "cells": [
                fact("class", c.t("f.condition"), key, _label(p.get("plant"), p.get("condition"), c), clf_prov),
                fact("confidence", c.t("f.confidence"), p["confidence"], c.pct(p["confidence"]), clf_prov, unit="%"),
                (fact("test_recall", c.t("f.test_recall"), m.get("recall"), c.pct((m.get("recall") or 0) * 100, 0), test_prov, unit="%")
                 if m else unavailable("test_recall", c.t("f.test_recall"), "—", "no_test_metrics")),
                (fact("kb_symptoms", c.t("f.kb_symptoms"), alt_kb.get("symptoms"), "; ".join(alt_kb.get("symptoms") or []) or "—",
                      _kb_prov("diseases", alt_kb), lang=KB_LANG)
                 if alt_kb else unavailable("kb_symptoms", c.t("f.kb_symptoms"), c.t("u.no_kb_short"), "no_kb"))]})
        note = c.t("note.alternatives_uncertain") if (d["low_confidence"] or close_call) else c.t("note.alternatives")
        sections.append(section("alternatives", c.t("sec.alternatives"),
                                [] if rows else [unavailable("alternatives", c.t("sec.alternatives"), c.t("v.none"), "none")],
                                chapter="evidence", rows=rows or None, note=note))

    # verified knowledge for the predicted disease
    if kb:
        kp = _kb_prov("diseases", kb)
        kb_refs = cites.cite_kb(f"disease:{kb.get('plant')}/{kb['name']}")
        info = [fact("description", c.t("f.description"), kb.get("description"), kb.get("description") or "", kp, lang=KB_LANG, refs=kb_refs)]
        if kb.get("symptoms"):
            info.append(fact("symptoms", c.t("f.symptoms_to_check"), kb["symptoms"], "; ".join(kb["symptoms"]), kp, lang=KB_LANG,
                             note=c.t("note.symptoms_not_detected"), refs=kb_refs))
        if kb.get("causes"):
            info.append(fact("causes", c.t("f.causes"), kb["causes"], "; ".join(kb["causes"]), kp, lang=KB_LANG, refs=kb_refs))
        if kb.get("transmission"):
            info.append(fact("transmission", c.t("f.transmission"), kb["transmission"], kb["transmission"], kp, lang=KB_LANG, refs=kb_refs))
        if kb.get("recovery_probability") is not None:
            info.append(fact("recovery_probability", c.t("f.recovery_probability"), kb["recovery_probability"],
                             c.pct(kb["recovery_probability"]), kp, unit="%", refs=kb_refs))
        if kb.get("recovery_time"):
            info.append(fact("recovery_time", c.t("f.recovery_time"), kb["recovery_time"], kb["recovery_time"], kp, lang=KB_LANG, refs=kb_refs))
        info.append(unavailable("untreated", c.t("sec.untreated"), c.t("u.no_untreated_risk"), "not_in_kb"))
        if not kb_refs:
            info.append(unavailable("kb_references", c.t("f.kb_references"), c.t("u.no_kb_references"), "no_kb_references"))
        sections.append(section("knowledge", c.t("sec.knowledge"), info, chapter="evidence", note=c.t("chrome.kb_language")))
    elif disease:
        sections.append(section("knowledge", c.t("sec.knowledge"),
                                [unavailable("description", c.t("f.description"), c.t("u.no_kb"), "no_kb")], chapter="evidence"))

    # what would make the assessment more reliable
    improve = []
    for issue in q.get("issues") or []:
        improve.append({"text": c.t(f"imp.quality.{issue}"), "provenance": provenance("rule", "image_quality_checks")})
    if d["low_confidence"] or close_call:
        improve.append({"text": c.t("imp.more_views"), "provenance": provenance("reference", "diagnostic clinic guidance"),
                        "refs": cites.cite("guidance:sample_stages")})
    if disease and (d["low_confidence"] or close_call or not kb):
        improve.append({"text": c.t("imp.lab_sample"), "provenance": provenance("reference", "diagnostic clinic guidance"),
                        "refs": cites.cite("guidance:confirm_before_pesticide")})
    if disease:
        improve.append({"text": c.t("imp.context"), "provenance": provenance("reference", "diagnostic clinic guidance"),
                        "refs": cites.cite("guidance:context_info")})
    if not seg_ok:
        improve.append({"text": c.t("imp.segmentation"), "provenance": provenance("rule", "measurement_availability")})
    if not ev.get("tracked"):
        improve.append({"text": c.t("imp.track"), "provenance": provenance("rule", "recovery_monitoring")})
    if not d.get("location_shared"):
        improve.append({"text": c.t("imp.location"), "provenance": provenance("rule", "area_context")})
    sections.append(section("improve_confidence", c.t("sec.improve_confidence"), [], chapter="evidence", items=improve))

    # ------------------------------------------------------------------- 4. visual
    media.append({"id": "photo", "kind": "photo", "storage_key": d.get("original_ref"), "title": c.t("m.title.photo"),
                  "caption": c.day(d.get("diagnosed_at")), "explanation": c.t("m.explain.photo"),
                  "provenance": provenance("user_recorded", "scan photo", rec_id)})
    if d.get("heatmap_ref"):
        media.append({"id": "heatmap", "kind": "attention_heatmap", "storage_key": d["heatmap_ref"], "title": c.t("m.title.heatmap"),
                      "caption": c.t("v.severity_method.explainability_heatmap"), "explanation": c.t("m.explain.heatmap"),
                      "refs": ref_gradcam, "provenance": provenance("model_estimate", "grad-cam", rec_id)})
    if seg_ok and seg.get("artifact_dir"):
        for kind, file, over in (("segmentation_overlay", "overlay.png", "photo"), ("segmentation_contours", "contours.png", "photo"),
                                 ("segmentation_mask", "mask.png", None)):
            item = {"id": kind, "kind": kind, "storage_key": f"{seg['artifact_dir']}/{file}", "title": c.t(f"m.title.{kind}"),
                    "caption": f"{seg.get('model_name')}@{seg.get('model_version')}", "explanation": c.t(f"m.explain.{kind}"),
                    "provenance": seg_prov}
            if over:
                item["overlay_of"] = over
            media.append(item)
    visual_facts = []
    if not d.get("heatmap_ref"):
        visual_facts.append(unavailable("heatmap", c.t("m.title.heatmap"),
                                        c.t("u.heatmap_healthy" if d["is_healthy"] else "u.no_heatmap"),
                                        "healthy" if d["is_healthy"] else "no_heatmap"))
    if not seg_ok:
        code = _area_reason(seg) if seg else "no_segmentation_model"
        visual_facts.append(unavailable("segmentation_images", c.t("m.title.segmentation_overlay"), c.t(f"u.{code}"), code))
    sections.append(section("visual", c.t("sec.visual"), visual_facts, chapter="visual",
                            media_ids=[m["id"] for m in media], note=c.t("note.visual")))

    # photo quality, explained
    qprov = provenance("rule", "image_quality_checks", rec_id)
    if q:
        issues = [c.t(f"v.quality.{i}") for i in q.get("issues", [])]
        sections.append(section("quality", c.t("sec.quality"), [
            fact("resolution", c.t("f.resolution"), [q.get("width"), q.get("height")],
                 f"{c.num(q.get('width'), 0)} × {c.num(q.get('height'), 0)}", qprov, unit="px"),
            fact("brightness", c.t("f.brightness"), q.get("mean_luma"), f"{c.num(q.get('mean_luma'), 0)} / {c.num(255, 0)}", qprov),
            fact("sharpness", c.t("f.sharpness"), q.get("sharpness"), c.num(q.get("sharpness"), 0), qprov, note=c.t("note.sharpness")),
            fact("quality_issues", c.t("f.quality_issues"), q.get("issues", []), ", ".join(issues) or c.t("v.none"), qprov)],
            chapter="visual", warning=bool(issues),
            text=c.t("text.quality_issues") if issues else c.t("text.quality_ok")))
    else:
        sections.append(section("quality", c.t("sec.quality"),
                                [unavailable("quality_issues", c.t("f.quality_issues"), c.t("u.older_scan"), "older_scan")], chapter="visual"))

    # history of this plant (tracked plants only)
    tr = ev.get("tracked")
    if tr and tr.get("history"):
        hist_media, rows = [], []
        for i, h in enumerate(tr["history"]):
            mid = f"history_{i}"
            hist_media.append({"id": mid, "kind": "photo", "storage_key": h.get("original_ref"), "title": c.day(h["diagnosed_at"]),
                               "caption": _label(None, h.get("condition"), c) + (f" · {c.pct(h['area_pct'])}" if h.get("area_pct") is not None else ""),
                               "provenance": provenance("user_recorded", "scan photo", f"diagnoses/{h['id']}")})
            if h.get("overlay_key"):
                hist_media.append({"id": f"{mid}_overlay", "kind": "segmentation_overlay", "storage_key": h["overlay_key"], "overlay_of": mid,
                                   "title": c.t("m.title.segmentation_overlay"),
                                   "provenance": provenance("model_measurement", h.get("area_model"), f"diagnoses/{h['id']}")})
            hp = provenance("model", f"classifier@{h.get('classifier_version') or 'unknown'}", f"diagnoses/{h['id']}")
            rows.append({"id": h["id"], "cells": [
                fact("date", c.t("f.date"), h["diagnosed_at"], c.day(h["diagnosed_at"]), provenance("system", "diagnoses")),
                fact("condition", c.t("f.condition"), h.get("condition"), _label(None, h.get("condition"), c), hp),
                fact("confidence", c.t("f.confidence"), h.get("confidence"), c.pct(h.get("confidence")), hp, unit="%"),
                (fact("area", c.t("f.area_measured"), h["area_pct"], c.pct(h["area_pct"]),
                      provenance("model_measurement", h.get("area_model"), f"diagnoses/{h['id']}"), unit="%")
                 if h.get("area_pct") is not None else unavailable("area", c.t("f.area_measured"), "—", "area_generic"))]})
        media.extend(hist_media)
        prog = []
        a = tr.get("assessment") or {}
        if a.get("status"):
            prog.append(fact("recovery_status", c.t("f.recovery_status"), a["status"], c.t(f"v.status.{a['status']}"),
                             provenance("rule", a.get("method_version") or "recovery-rules")))
        series = a.get("area_series") or []
        if len(series) >= 2:
            change = round(series[-1]["area_pct"] - series[0]["area_pct"], 2)
            prog.append(fact("progression", c.t("f.progression"), change,
                             f"{_arrow(change)} {c.pp(change)} ({c.day(series[0]['taken_at'])} → {c.day(series[-1]['taken_at'])})",
                             provenance("model_measurement", series[-1].get("model")), unit="pp"))
        else:
            prog.append(unavailable("progression", c.t("f.progression"), c.t("u.no_area_series"), "no_area_series"))
        sections.append(section("history", c.t("sec.history_visual"), prog, chapter="visual", rows=rows,
                                media_ids=[m["id"] for m in hist_media], note=c.t("note.history")))

    # --------------------------------------------------------------- 5. interpretation
    sev = []
    if d.get("severity_level"):
        sev.append(fact("severity", c.t("f.severity"), d["severity_level"], c.t(f"v.severity.{d['severity_level']}"),
                        provenance("model_estimate", "grad-cam", rec_id), note=c.t("v.severity_method.explainability_heatmap"),
                        refs=ref_gradcam))
        limitations.append("lim.severity_is_estimate")
    elif disease:
        sev.append(unavailable("severity", c.t("f.severity"), c.t("u.no_severity"), "no_severity"))
    if seg_ok and seg.get("affected_pct") is not None:
        sev.append(fact("area_measured", c.t("f.area_measured"), seg["affected_pct"], c.pct(seg["affected_pct"]), seg_prov, unit="%",
                        note=c.t("note.area_measured", basis=c.t(f"v.area_basis.{seg.get('area_basis') or 'plant_pixels'}"))))
        limitations.append("lim.area_is_2d")
    else:
        code = _area_reason(seg)
        sev.append(unavailable("area_measured", c.t("f.area_measured"), c.t(f"u.{code}"), code))
    if d.get("gradcam_area_pct") is not None:
        sev.append(fact("area_estimate", c.t("f.area_estimate"), d["gradcam_area_pct"], c.pct(d["gradcam_area_pct"]),
                        provenance("model_estimate", "grad-cam", rec_id), unit="%", note=c.t("note.area_estimate"), refs=ref_gradcam))
    limitations.append("lim.no_critical_scale")
    sections.append(section("severity", c.t("sec.severity"), sev, chapter="interpretation",
                            text=c.t("text.severity_scale"), text_provenance=provenance("rule", "report-integrity")))

    # weather at scan time: what it means for spraying (weather_guidance.py, the same
    # assessment the diagnosis page and the scan PDF use), never for disease risk
    w = d.get("weather")
    wx = weather_guidance(w, rules, locale, cites, applicable=disease)
    env = []
    if w:
        wp = provenance("weather_provider", "open-meteo", f"weather_snapshots/{d['id']}")
        shown = {"temperature_c": ("temperature", "f.temperature", lambda v: f"{c.num(v)} °C", "°C"),
                 "humidity_pct": ("humidity", "f.humidity", lambda v: c.pct(v, 0), "%"),
                 "rain_probability_pct": ("rain_probability", "f.rain_probability", lambda v: c.pct(v, 0), "%"),
                 "wind_speed_kmh": ("wind", "f.wind", lambda v: f"{c.num(v)} km/h", "km/h")}
        for source_key, (key, label, show, unit) in shown.items():
            m = wx["measurements"][source_key]
            env.append(fact(key, c.t(label), m["value"], show(m["value"]), wp, unit=unit) if m["state"] == "ok"
                       else unavailable(key, c.t(label), c.t(f"u.weather_{m['state']}"), f"weather_{m['state']}"))
        env.append(fact("weather_time", c.t("f.weather_time"), w.get("retrieved_at"), c.day(w.get("retrieved_at")), wp)
                   if w.get("retrieved_at") else
                   unavailable("weather_time", c.t("f.weather_time"), c.t("u.weather_missing"), "weather_missing"))
    else:
        env.append(unavailable("weather", c.t("sec.environment"), c.t("u.no_weather"), "no_weather"))
    st = [statement(wx["summary"], "missing" if wx["verdict"] == "not_assessed" else "rule",
                    provenance("rule", f"{rules['rules_version']}:weather_guidance"))]
    for item in wx["items"]:
        st.append(statement(item["text"], {"reference": "reference", "missing_data": "missing"}.get(item["basis"], "rule"),
                            provenance("reference", "weather guidance") if item["basis"] == "reference" else provenance("system"),
                            refs=item["refs"], evidence={"wind": ["wind"], "rain": ["rain_probability"],
                                                         "label_limits": ["temperature", "humidity"]}.get(item["code"])))
    sections.append(section("environment", c.t("sec.environment"), env, chapter="interpretation", statements=st,
                            weather_verdict=wx["verdict"]))

    # local area (only when the owner shared the scan location)
    area = ev.get("area")
    if area:
        sections.append(section("outbreak_context", c.t("sec.outbreak_context"), _area_facts(c, area), chapter="interpretation",
                                note=c.t("note.area_privacy")))
    else:
        sections.append(section("outbreak_context", c.t("sec.outbreak_context"),
                                [unavailable("area", c.t("sec.outbreak_context"), c.t("u.no_location"), "no_location")],
                                chapter="interpretation"))

    # tracked plant context
    if tr:
        tp = provenance("user_recorded", "tracked_plants", f"tracked_plants/{tr['plant_id']}")
        rows = [fact("tracked_plant", c.t("f.tracked_plant"), tr["name"], tr["name"], tp),
                fact("scans", c.t("f.scans"), tr["scans"], c.num(tr["scans"], 0), provenance("historical", "tracked_plant_scans"))]
        if tr.get("latest_status"):
            rows.append(fact("recovery_status_ctx", c.t("f.recovery_status"), tr["latest_status"],
                             c.t(f"v.status.{tr['latest_status']}"), provenance("rule", tr.get("method_version") or "recovery-rules")))
        rows.append(fact("treatment_count", c.t("f.treatment_count"), tr["treatments"], c.num(tr["treatments"], 0), tp))
        for i, trt in enumerate((tr.get("recent_treatments") or [])[:3]):
            rows.append(fact(f"recent_treatment.{i}", c.t("f.recorded_treatment"), trt.get("name"),
                             f"{trt.get('name')} ({c.t('v.category.' + str(trt.get('category')))}) — {c.day(trt.get('applied_on'))}",
                             provenance("user_recorded", "treatment_records", f"treatment_records/{trt.get('id')}")))
        if tr.get("next_reminder"):
            rows.append(fact("next_reminder", c.t("f.next_reminder"), tr["next_reminder"], c.day(tr["next_reminder"]), tp))
        sections.append(section("plant_context", c.t("sec.plant_context"), rows, chapter="interpretation"))
    else:
        sections.append(section("plant_context", c.t("sec.plant_context"),
                                [unavailable("tracked_plant", c.t("f.tracked_plant"), c.t("u.not_tracked"), "not_tracked")],
                                chapter="interpretation"))

    # ------------------------------------------------------------------ 7. monitoring
    diagnosed = _d(d["diagnosed_at"]) if d.get("diagnosed_at") else None
    cadence = int(rules["rescan_days_disease"] if disease else rules["rescan_days_healthy"])
    plan = []
    if tr and tr.get("next_reminder"):
        plan.append({"text": c.t("mon.reminder", date=c.day(tr["next_reminder"])), "when": c.day(tr["next_reminder"]),
                     "provenance": provenance("user_recorded", "follow_up_reminders")})
    elif diagnosed:
        due = diagnosed + timedelta(days=cadence)
        plan.append({"text": c.t("mon.rescan_disease" if disease else "mon.rescan_healthy", days=c.num(cadence, 0)),
                     "when": c.day(due), "provenance": provenance("rule", f"{rules['rules_version']}:rescan"),
                     "refs": cites.cite("guidance:scouting") if disease else []})
    plan.append({"text": c.t("mon.same_photo"), "provenance": provenance("rule", "comparable_measurements")})
    if disease:
        plan.append({"text": c.t("mon.record_treatments"), "provenance": provenance("rule", "recovery_monitoring")})
        plan.append({"text": c.t("mon.watch_spread"), "provenance": provenance("reference", "scouting guidance"),
                     "refs": cites.cite("guidance:scouting")})
    sections.append(section("monitoring_plan", c.t("sec.monitoring_plan"), [], chapter="monitoring", items=plan))

    # -------------------------------------------------------------------- technical
    tech = [fact("meta.diagnosed_at", c.t("f.diagnosed_at"), d.get("diagnosed_at"), c.day(d.get("diagnosed_at")),
                 provenance("system", "diagnoses", rec_id)),
            fact("meta.scan_id", c.t("f.scan_id"), d["id"], d["id"], provenance("system", "diagnoses", rec_id))]
    sections.append(section("technical", c.t("sec.technical"), tech, chapter="references"))

    key_facts = [f_condition, f_conf]
    if own_metrics:
        key_facts.append(next(f for f in rel if f["key"] == "test_recall"))
    key_facts.append(next(f for f in sev if f["key"] == "area_measured"))
    if d.get("severity_level"):
        key_facts.append(next(f for f in sev if f["key"] == "severity"))
    if q:
        key_facts.append(next(s for s in sections if s["id"] == "quality")["facts"][-1])

    methods = [{"id": "classifier", "name": c.t("m.classifier"), "kind": "model", "version": clf.get("version"),
                "synthetic": bool(clf.get("synthetic"))}]
    if own_metrics or test.get("accuracy") is not None:
        methods.append({"id": "classifier_test", "name": c.t("m.classifier_test"), "kind": "model_evaluation", "version": clf.get("version")})
    if d.get("severity_level") or d.get("gradcam_area_pct") is not None:
        methods.append({"id": "gradcam", "name": c.t("m.gradcam"), "kind": "model_estimate", "version": clf.get("version"), "refs": ref_gradcam})
    if seg_ok:
        methods.append({"id": "segmentation", "name": c.t("m.segmentation"), "kind": "model_measurement",
                        "version": f"{seg.get('model_name')}@{seg.get('model_version')}", "synthetic": bool(seg.get("synthetic"))})
    if disease:
        methods.append({"id": "spray_conditions", "name": c.t("m.spray_conditions"), "kind": "rule", "version": rules["rules_version"]})

    status = "disease_predicted" if disease else "healthy_predicted"
    content = {
        "type": "diagnosis",
        "title": f"{c.t('type.diagnosis')} — {plant}: {condition}",
        "subject": {"diagnosis_id": d["id"], "plant": plant, "condition": condition, "diagnosed_at": d.get("diagnosed_at")},
        "status": {"code": status, "label": condition, "level": d.get("severity_level"), "provenance": clf_prov,
                   "qualifier": c.t("note.prediction"), "close_call": close_call},
        "crop": d.get("plant_name"), "disease": d["predicted_condition"] if disease else None,
        "key_facts": key_facts, "sections": sections, "media": media, "charts": charts,
        "limitations": [c.t(k) for k in dict.fromkeys(limitations)], "methods": methods,
    }
    return _finish(content, cites, c, ["summary", "condition", "evidence", "visual", "interpretation", "actions", "monitoring",
                                       "limitations", "references"])


def _arrow(change: float) -> str:
    return "↓" if change < 0 else ("↑" if change > 0 else "→")


def _area_reason(seg: Optional[dict]) -> str:
    if not seg:
        return "older_scan"
    if seg.get("status") in ("dataset_unavailable", "not_trained", "training_required", "not_configured", "unavailable"):
        return "no_segmentation_model"
    if seg.get("status") == "failed":
        return "segmentation_failed"
    if seg.get("reason") in ("model_does_not_segment_leaf_tissue", "too_little_plant_tissue_detected"):
        return seg["reason"]
    return "area_generic"


def _area_facts(c: Ctx, area: dict) -> List[dict]:
    obs = provenance("observation", "disease_observations", f"geo_areas/{area['area_id']}")
    facts = [fact("inspections", c.t("f.inspections"), area["inspections"], c.num(area["inspections"], 0), obs),
             fact("positives", c.t("f.positives"), area["positives"], c.num(area["positives"], 0), obs)]
    if area.get("positive_rate") is not None:
        facts.append(fact("positive_share", c.t("f.positive_share"), area["positive_rate"],
                          c.pct(area["positive_rate"] * 100, 0), obs, unit="%"))
    pred = area.get("prediction")
    if pred and pred.get("status") == "ok":
        facts.append(fact("risk_level", c.t("f.risk_level"), pred["risk_level"], c.t(f"v.risk.{pred['risk_level']}"),
                          provenance("model", f"{pred.get('model_name')}@{pred.get('model_version')}",
                                     f"outbreak_predictions/{pred['prediction_id']}"),
                          note=c.t("chrome.prediction_not_observation")))
    else:
        facts.append(unavailable("risk_level", c.t("f.risk_level"), c.t("u.no_prediction"), "no_prediction"))
    return facts


# =========================================================================== plant progress
def comparability(scans: List[dict], rules: dict) -> List[dict]:
    """For each scan: is its measurement usable for comparison, and if not, why. Mirrors
    ai/recovery/engine.py (same model version, valid denominator, no blocking quality issue)."""
    blocking = set(rules.get("blocking_quality_issues") or ["blurry", "too_dark", "overexposed"])
    usable = [s for s in scans if s.get("area_pct") is not None and s.get("area_model") and not (set(s.get("quality_issues") or []) & blocking)]
    reference_model = usable[-1]["area_model"] if usable else None
    out = []
    for s in scans:
        issues = set(s.get("quality_issues") or []) & blocking
        if s.get("area_pct") is None:
            reason = s.get("area_reason") or "area_generic"
        elif issues:
            reason = "quality:" + ",".join(sorted(issues))
        elif s.get("area_model") != reference_model:
            reason = "other_model"
        else:
            reason = None
        out.append({"id": s["id"], "comparable": reason is None, "reason": reason})
    return out


def build_plant_progress(ev: dict, locale: str, cites: Optional[Citations] = None) -> dict:
    c = Ctx(locale)
    cites = cites or Citations(locale)
    rules = ev["rules"]
    p, scans, a = ev["plant"], ev["scans"], ev["assessment"]
    pprov = provenance("user_recorded", "tracked_plants", f"tracked_plants/{p['id']}")
    rprov = provenance("rule", a.get("method_version") or "recovery-rules", f"recovery_assessments/{a.get('id')}")
    rec_rules = ev.get("recovery_rules") or {}
    sections: List[dict] = []
    media: List[dict] = []
    charts: List[dict] = []
    limitations = ["lim.prediction_not_diagnosis", "lim.camera_variation", "lim.correlation_not_causation"]
    status = a["status"]
    first, last = (scans[0], scans[-1]) if scans else (None, None)
    days = (_d(last["diagnosed_at"]) - _d(first["diagnosed_at"])).days if len(scans) >= 2 else 0
    series = a.get("area_series") or []
    comp = {x["id"]: x for x in comparability(scans, {**rules, **rec_rules})}
    indicators = {i.get("code"): i for i in a.get("indicators") or []}
    band = rec_rules.get("stable_band_pct")

    # ------------------------------------------------------------------ 2. condition
    key_facts = [fact("recovery_status", c.t("f.recovery_status"), status, c.t(f"v.status.{status}"), rprov),
                 fact("count.scans", c.t("f.scans"), len(scans), c.num(len(scans), 0),
                      provenance("historical", "tracked_plant_scans", f"tracked_plants/{p['id']}")),
                 fact("count.days", c.t("f.days_tracked"), days, c.num(days, 0),
                      provenance("historical", "diagnoses", f"tracked_plants/{p['id']}"))]
    if len(series) >= 2:
        f0, f1 = series[0], series[-1]
        change = round(f1["area_pct"] - f0["area_pct"], 2)
        key_facts.append(fact("area_change", c.t("f.area_change"), change,
                              f"{c.pct(f0['area_pct'])} → {c.pct(f1['area_pct'])} ({c.pp(change)})",
                              provenance("model_measurement", f1.get("model") or "", f"recovery_assessments/{a.get('id')}"), unit="pp"))
        limitations.append("lim.area_is_2d")
    else:
        key_facts.append(unavailable("area_change", c.t("f.area_change"), c.t("u.no_area_series"), "no_area_series"))
    key_facts.append(fact("count.treatments", c.t("f.treatment_count"), len(ev["treatments"]), c.num(len(ev["treatments"]), 0), pprov))

    why = []
    if status in ("improving", "worsening", "stable") and len(series) >= 2:
        f0, f1 = series[0], series[-1]
        change = round(f1["area_pct"] - f0["area_pct"], 2)
        why.append(statement(c.t(f"st.pp.{status}", first=c.pct(f0["area_pct"]), d0=c.day(f0["taken_at"]), last=c.pct(f1["area_pct"]),
                                 d1=c.day(f1["taken_at"]), change=c.pp(change), band=c.num(band) if band is not None else "?"),
                             "measured", provenance("model_measurement", f1.get("model")), evidence=["area_change"]))
        why.append(statement(c.t("st.pp.band_rule", band=c.num(band) if band is not None else "?"), "rule", rprov))
    elif status == "inconclusive":
        reasons = ", ".join(c.t(f"rl.{code}") for code in a.get("limitations") or []) or c.t("chrome.missing")
        why.append(statement(c.t("st.pp.inconclusive", reasons=reasons), "rule", rprov))
    else:
        why.append(statement(c.t("st.pp.insufficient"), "rule", rprov))
    changed = indicators.get("classification_changed")
    if changed:
        why.append(statement(c.t("st.pp.label_changed", frm=_label(None, changed.get("from"), c), to=_label(None, changed.get("to"), c)),
                             "rule", rprov))
    conf = indicators.get("classifier_confidence")
    if conf:
        why.append(statement(c.t("st.pp.confidence_not_health", frm=c.pct(conf.get("from")), to=c.pct(conf.get("to"))), "rule", rprov))
    sections.append(section("status", c.t("sec.recovery_status"), [key_facts[0]], chapter="condition", statements=why))

    # ------------------------------------------------------------------- 3. evidence
    rows = []
    for i, s in enumerate(scans):
        sp = provenance("model", f"classifier@{s.get('classifier_version') or 'unknown'}", f"diagnoses/{s['id']}")
        cm = comp.get(s["id"]) or {}
        rows.append({"id": s["id"], "cells": [
            fact("n", "#", i + 1, c.num(i + 1, 0), provenance("historical", "scan order")),
            fact("date", c.t("f.date"), s["diagnosed_at"], c.day(s["diagnosed_at"]), provenance("system", "diagnoses")),
            fact("day", c.t("f.day_offset"), (_d(s["diagnosed_at"]) - _d(first["diagnosed_at"])).days,
                 c.num((_d(s["diagnosed_at"]) - _d(first["diagnosed_at"])).days, 0), provenance("historical", "diagnoses")),
            fact("condition", c.t("f.condition"), s["condition"], _label(None, s["condition"], c), sp),
            fact("confidence", c.t("f.confidence"), s["confidence"], c.pct(s["confidence"]), sp, unit="%"),
            fact("severity", c.t("f.severity_estimate"), s.get("severity_level"),
                 c.t(f"v.severity.{s['severity_level']}") if s.get("severity_level") else "—",
                 provenance("model_estimate", "grad-cam", f"diagnoses/{s['id']}")),
            (fact("area", c.t("f.area_measured"), s["area_pct"], c.pct(s["area_pct"]),
                  provenance("model_measurement", s.get("area_model"), f"diagnoses/{s['id']}"), unit="%")
             if s.get("area_pct") is not None else unavailable("area", c.t("f.area_measured"), "—", s.get("area_reason") or "area_generic")),
            fact("quality", c.t("f.photo_quality"), s.get("quality_issues") or [],
                 ", ".join(c.t(f"v.quality.{q}") for q in s.get("quality_issues") or []) or c.t("v.ok"),
                 provenance("rule", "image_quality_checks", f"diagnoses/{s['id']}")),
            fact("comparable", c.t("f.comparable"), cm.get("comparable"),
                 c.t("v.yes") if cm.get("comparable") else _reason_text(c, cm.get("reason")), rprov),
            fact("stage", c.t("f.stage"), s["stage"], c.t(f"v.stage.{s['stage']}"), pprov),
        ]})
    sections.append(section("scan_table", c.t("sec.scan_table"), [], chapter="evidence", rows=rows, note=c.t("note.scan_table")))

    # measured changes between consecutive comparable measurements
    mrows, mfacts = [], []
    for prev, cur in zip(series, series[1:]):
        gap = (_d(cur["taken_at"]) - _d(prev["taken_at"])).days
        change = round(cur["area_pct"] - prev["area_pct"], 2)
        mp = provenance("model_measurement", cur.get("model"), f"diagnoses/{cur.get('diagnosis_id')}")
        mrows.append({"id": f"{prev.get('diagnosis_id')}-{cur.get('diagnosis_id')}", "cells": [
            fact("from", c.t("f.from"), prev["taken_at"], f"{c.day(prev['taken_at'])} · {c.pct(prev['area_pct'])}", mp),
            fact("to", c.t("f.to"), cur["taken_at"], f"{c.day(cur['taken_at'])} · {c.pct(cur['area_pct'])}", mp),
            fact("days", c.t("f.interval_days"), gap, c.num(gap, 0), provenance("historical", "diagnoses")),
            fact("change", c.t("f.change"), change, c.pp(change), mp, unit="pp"),
            (fact("rate", c.t("f.rate"), round(change / gap, 3), f"{c.pp(change / gap, 2)} / {c.t('unit.day')}", mp)
             if gap else unavailable("rate", c.t("f.rate"), "—", "same_day"))]})
    if len(series) >= 2:
        total = round(series[-1]["area_pct"] - series[0]["area_pct"], 2)
        mfacts.append(fact("total_change", c.t("f.total_change"), total, c.pp(total), provenance("model_measurement", series[-1].get("model")), unit="pp"))
        slope = indicators.get("affected_area_trend_pct_points_per_day")
        if slope:
            mfacts.append(fact("trend", c.t("f.trend_slope"), slope.get("value"), f"{c.pp(slope.get('value'), 3)} / {c.t('unit.day')}",
                               provenance("model_measurement", series[-1].get("model")), note=c.t("note.trend_slope")))
        sections.append(section("measured_changes", c.t("sec.measured_changes"), mfacts, chapter="evidence", rows=mrows,
                                note=c.t("note.measured_changes")))
    else:
        sections.append(section("measured_changes", c.t("sec.measured_changes"),
                                [unavailable("total_change", c.t("f.total_change"), c.t("u.no_area_series"), "no_area_series")],
                                chapter="evidence"))

    # ------------------------------------------------------------------- 4. visual
    if len(series) >= 2:
        x_dates = [_d(s["taken_at"]) for s in series]
        markers = _treatment_markers(c, ev["treatments"], x_dates)
        charts.append({"id": "area_trend", "kind": "line", "title": c.t("sec.area_trend"), "x": [c.day(s["taken_at"]) for s in series],
                       "series": [{"key": "area", "label": c.t("f.area_measured"), "values": [s["area_pct"] for s in series]}],
                       "unit": "%", "markers": markers, "provenance": provenance("model_measurement", series[-1].get("model"))})
    sev_scans = [s for s in scans if s.get("severity_level") in _SEVERITY_RANK]
    if len(sev_scans) >= 2:
        x_dates = [_d(s["diagnosed_at"]) for s in sev_scans]
        charts.append({"id": "severity_trend", "kind": "step", "title": c.t("sec.severity_trend"),
                       "x": [c.day(s["diagnosed_at"]) for s in sev_scans],
                       "series": [{"key": "severity", "label": c.t("f.severity_estimate"),
                                   "values": [_SEVERITY_RANK[s["severity_level"]] for s in sev_scans]}],
                       "y_labels": {"1": c.t("v.severity.mild"), "2": c.t("v.severity.moderate"), "3": c.t("v.severity.severe")},
                       "markers": _treatment_markers(c, ev["treatments"], x_dates),
                       "provenance": provenance("model_estimate", "grad-cam"), "note": c.t("note.severity_chart")})
    chart_facts = []
    if len(series) < 2:
        chart_facts.append(unavailable("area_trend", c.t("sec.area_trend"), c.t("u.no_area_series"), "no_area_series"))
    sections.append(section("trends", c.t("sec.trends"), chart_facts, chapter="visual",
                            chart_ids=[ch["id"] for ch in charts], note=c.t("note.trends")))
    gallery = scans if len(scans) <= 6 else [scans[0]] + scans[-5:]
    for s in gallery:
        mid = f"photo_{s['id'][:8]}"
        media.append({"id": mid, "kind": "photo", "storage_key": s.get("original_ref"), "title": c.day(s["diagnosed_at"]),
                      "caption": _label(None, s["condition"], c) + (f" · {c.pct(s['area_pct'])}" if s.get("area_pct") is not None else ""),
                      "provenance": provenance("user_recorded", "scan photo", f"diagnoses/{s['id']}")})
        if s.get("overlay_key"):
            media.append({"id": f"{mid}_overlay", "kind": "segmentation_overlay", "storage_key": s["overlay_key"], "overlay_of": mid,
                          "title": c.t("m.title.segmentation_overlay"),
                          "provenance": provenance("model_measurement", s.get("area_model"), f"diagnoses/{s['id']}")})
    if media:
        sections.append(section("comparison", c.t("sec.photo_series"), [], chapter="visual",
                                media_ids=[m["id"] for m in media], note=c.t("note.photo_series")))

    # --------------------------------------------------------------- 5. interpretation
    trows = []
    measured_points = [(_d(s["taken_at"]), s) for s in series]
    for tr in ev["treatments"]:
        tp = provenance("user_recorded", "treatment_records", f"treatment_records/{tr['id']}")
        when = _d(tr["applied_on"])
        before = next((s for dt, s in reversed(measured_points) if dt <= when), None)
        after = next((s for dt, s in measured_points if dt > when), None)
        trows.append({"id": tr["id"], "cells": [
            fact("applied_on", c.t("f.date"), tr["applied_on"], c.day(tr["applied_on"]), tp),
            fact("name", c.t("f.treatment_name"), tr["name"], tr["name"], tp),
            fact("category", c.t("f.category"), tr["category"], c.t(f"v.category.{tr['category']}"), tp),
            fact("dosage", c.t("f.dosage_recorded"), tr.get("dosage_text"), tr.get("dosage_text") or "—", tp),
            (fact("before", c.t("f.area_before"), before["area_pct"], f"{c.pct(before['area_pct'])} ({c.day(before['taken_at'])})",
                  provenance("model_measurement", before.get("model")), unit="%")
             if before else unavailable("before", c.t("f.area_before"), "—", "no_measurement_before")),
            (fact("after", c.t("f.area_after"), after["area_pct"], f"{c.pct(after['area_pct'])} ({c.day(after['taken_at'])})",
                  provenance("model_measurement", after.get("model")), unit="%")
             if after else unavailable("after", c.t("f.area_after"), "—", "no_measurement_after"))]})
    sections.append(section("treatments", c.t("sec.treatments_measurements"), [] if trows else
                            [unavailable("treatments", c.t("sec.treatments"), c.t("v.none_recorded"), "none")],
                            chapter="interpretation", rows=trows or None, note=c.t("note.treatments_measurements")))
    hypotheses = _hypotheses(c, status, series, ev["treatments"], scans)
    sections.append(section("hypotheses", c.t("sec.hypotheses"), [] if hypotheses else
                            [unavailable("hypotheses", c.t("sec.hypotheses"), c.t("u.no_hypotheses"), "none")],
                            chapter="interpretation", hypotheses=hypotheses or None, note=c.t("chrome.hypothesis")))
    events = [{"date": e["occurred_at"], "display_date": c.day(e["occurred_at"]), "event": e["event_type"],
               "label": c.t(f"ev.{e['event_type']}")} for e in ev["events"]]
    sections.append(section("timeline", c.t("sec.timeline"), [], chapter="interpretation", events=events))

    # ------------------------------------------------------------------ 7. monitoring
    gaps = follow_up_gaps(scans, ev["treatments"], ev.get("reminders") or [], rules, ev.get("today"))
    gap_items = []
    for g in gaps:
        gap_items.append({"text": c.t(f"gap.{g['code']}", **{k: (c.day(v) if k.endswith("date") else c.num(v, 0)) for k, v in g.items()
                                                             if k != "code"}),
                          "provenance": provenance("rule", f"{rules['rules_version']}:follow_up"), "kind": "gap"})
    for code in a.get("limitations") or []:
        if code in ("some_images_failed_quality_checks", "incompatible_segmentation_models", "area_comparison_unavailable"):
            gap_items.append({"text": c.t(f"rl.{code}"), "provenance": rprov, "kind": "gap"})
    latest_disease = bool(last and not last["is_healthy"])
    cadence = int(rules["rescan_days_disease"] if latest_disease else rules["rescan_days_healthy"])
    next_due = ev.get("next_reminder") or (_d(last["diagnosed_at"]) + timedelta(days=cadence) if last else None)
    plan = []
    if next_due:
        plan.append({"text": c.t("mon.next_scan", days=c.num(cadence, 0)), "when": c.day(next_due),
                     "provenance": provenance("user_recorded", "follow_up_reminders") if ev.get("next_reminder")
                     else provenance("rule", f"{rules['rules_version']}:rescan"),
                     "refs": cites.cite("guidance:scouting") if latest_disease else []})
    plan.append({"text": c.t("mon.same_photo"), "provenance": provenance("rule", "comparable_measurements")})
    plan.append({"text": c.t("mon.record_treatments"), "provenance": provenance("rule", "recovery_monitoring")})
    sections.append(section("follow_up", c.t("sec.follow_up_gaps"), [] if gap_items else
                            [unavailable("gaps", c.t("sec.follow_up_gaps"), c.t("u.no_gaps"), "none")],
                            chapter="monitoring", items=gap_items or None, warning=bool(gap_items)))
    sections.append(section("monitoring_plan", c.t("sec.monitoring_plan"), [], chapter="monitoring", items=plan))

    sections.append(section("technical", c.t("sec.technical"), [
        fact("meta.method", c.t("f.rules"), a.get("method_version"), a.get("method_version") or "—", rprov),
        fact("meta.band", c.t("f.stable_band"), band, f"±{c.num(band)} {c.t('unit.pp')}" if band is not None else "—", rprov),
        fact("meta.limitations", c.t("chrome.limitations"), a.get("limitations"),
             ", ".join(c.t(f"rl.{x}") for x in a.get("limitations") or []) or c.t("v.none"), rprov)], chapter="references"))

    methods = [{"id": "recovery_rules", "name": c.t("m.recovery_rules"), "kind": "rule", "version": a.get("method_version")},
               {"id": "classifier", "name": c.t("m.classifier"), "kind": "model", "version": None}]
    if series:
        methods.append({"id": "segmentation", "name": c.t("m.segmentation"), "kind": "model_measurement",
                        "version": series[-1].get("model"), "synthetic": bool(ev.get("segmentation_synthetic"))})
    content = {
        "type": "plant_progress",
        "title": f"{c.t('type.plant_progress')} — {p['name']}",
        "subject": {"tracked_plant_id": p["id"], "name": p["name"], "crop": p.get("crop"), "species": p.get("species"),
                    "since": p.get("created_at")},
        "status": {"code": status, "label": c.t(f"v.status.{status}"), "provenance": rprov,
                   "assessment_limitations": a.get("limitations") or []},
        "crop": p.get("crop"), "disease": (last or {}).get("condition") if last and not last["is_healthy"] else None,
        "key_facts": key_facts, "sections": sections, "media": media, "charts": charts,
        "limitations": [c.t(k) for k in dict.fromkeys(limitations)], "methods": methods,
    }
    return _finish(content, cites, c, ["summary", "condition", "evidence", "visual", "interpretation", "actions", "monitoring",
                                       "limitations", "references"])


def _reason_text(c: Ctx, reason: Optional[str]) -> str:
    if not reason:
        return "—"
    if reason.startswith("quality:"):
        return c.t("cmp.quality", issues=", ".join(c.t(f"v.quality.{q}") for q in reason.split(":", 1)[1].split(",")))
    return c.t(f"cmp.{reason}")


def _treatment_markers(c: Ctx, treatments: List[dict], x_dates: List[date]) -> List[dict]:
    """Treatment events placed on a chart's date axis (at the first point on or after them)."""
    out = []
    if not x_dates:
        return out
    for tr in sorted(treatments, key=lambda x: str(x["applied_on"])):
        when = _d(tr["applied_on"])
        if when < x_dates[0] or when > x_dates[-1]:
            continue
        index = next(i for i, dt in enumerate(x_dates) if dt >= when)
        out.append({"index": index, "label": f"{tr['name']} · {c.day(when)}", "kind": "treatment"})
    return out


def follow_up_gaps(scans: List[dict], treatments: List[dict], reminders: List[dict], rules: dict,
                   today: Optional[str] = None) -> List[dict]:
    """Missing follow-up data, from the stored dates only."""
    out = []
    if not scans:
        return out
    factor = float(rules.get("follow_up_gap_factor", 2))
    cadence = int(rules["rescan_days_disease"])
    dates = [_d(s["diagnosed_at"]) for s in scans]
    for a, b in zip(dates, dates[1:]):
        if (b - a).days > factor * cadence:
            out.append({"code": "long_gap", "from_date": a, "to_date": b, "days": (b - a).days})
    now = _d(today) if today else None
    last_disease = not scans[-1]["is_healthy"]
    if now and last_disease and (now - dates[-1]).days > cadence:
        out.append({"code": "follow_up_due", "last_date": dates[-1], "days": (now - dates[-1]).days})
    for tr in treatments:
        when = _d(tr["applied_on"])
        if not any(dt > when for dt in dates):
            out.append({"code": "no_scan_after_treatment", "treatment_date": when})
    overdue = [r for r in reminders if r.get("state") == "overdue"]
    if overdue:
        out.append({"code": "overdue_reminders", "n": len(overdue)})
    unmeasured = sum(1 for s in scans if s.get("area_pct") is None)
    if unmeasured:
        out.append({"code": "unmeasured_scans", "n": unmeasured})
    return out


def _hypotheses(c: Ctx, status: str, series: List[dict], treatments: List[dict], scans: List[dict]) -> List[dict]:
    out = []
    hp = provenance("rule", "hypothesis-rules-v1")
    if len(series) >= 2:
        start, end = _d(series[0]["taken_at"]), _d(series[-1]["taken_at"])
        between = sorted((tr for tr in treatments if start <= _d(tr["applied_on"]) <= end), key=lambda x: str(x["applied_on"]))
        if status == "improving" and between:
            out.append({"text": c.t("hyp.improved_after_treatment", date=c.day(between[0]["applied_on"])), "provenance": hp})
        elif status == "worsening" and between:
            out.append({"text": c.t("hyp.worsened_despite_treatment", date=c.day(between[0]["applied_on"])), "provenance": hp})
        elif status == "worsening":
            out.append({"text": c.t("hyp.worsened_untreated"), "provenance": hp})
        elif status == "stable" and between:
            out.append({"text": c.t("hyp.stable_after_treatment", date=c.day(between[0]["applied_on"])), "provenance": hp})
    elif len(scans) >= 2 and scans[0]["condition"] != scans[-1]["condition"]:
        out.append({"text": c.t("hyp.label_only"), "provenance": hp})
    if out:
        out.append({"text": c.t("hyp.other_factors"), "provenance": hp})
    return out


# ============================================================================ outbreak area
def build_outbreak_area(ev: dict, locale: str, cites: Optional[Citations] = None) -> dict:
    c = Ctx(locale)
    cites = cites or Citations(locale)
    area, region, summary = ev["area"], ev["region"], ev.get("summary")
    crop, disease = ev.get("crop"), ev.get("disease")
    obs = provenance("observation", "disease_observations", f"geo_areas/{area['id']}")
    sections: List[dict] = []
    charts: List[dict] = []
    media: List[dict] = []
    privacy = ev["privacy"]
    rules = ev["rules"]
    card = ev.get("model_card") or {}
    limitations = ["lim.risk_is_estimate", "lim.app_scans_biased", "lim.cell_not_farm"]
    period = f"{c.day(ev['date_from'])} – {c.day(ev['date_to'])}"
    b = area["bounds"]
    res = float(privacy["grid_resolution_deg"])
    km_ns = res * 111.32
    region_label = f"{c.num(b['south'], 2)}…{c.num(b['north'], 2)}° , {c.num(b['west'], 2)}…{c.num(b['east'], 2)}°"
    cells = region.get("cells", [])
    pred = ev.get("prediction")
    has_pred = bool(pred and pred.get("status") == "ok")

    # ------------------------------------------------------------------ 2. condition
    subject = [fact("region", c.t("f.region"), b, region_label, provenance("system", "geo_areas", f"geo_areas/{area['id']}"),
                    note=c.t("note.cell_size", deg=c.num(res, 2), km=c.num(km_ns, 0))),
               fact("period", c.t("f.period"), [ev["date_from"], ev["date_to"]], period, provenance("system", "report_request")),
               fact("crop", c.t("f.crop"), crop, humanize(crop) or c.t("chrome.missing"), provenance("system", "report_request")),
               fact("disease", c.t("f.disease"), disease, humanize(disease) or c.t("chrome.missing"), provenance("system", "report_request"))]
    if summary and summary.get("inspections"):
        negatives = summary["inspections"] - summary["positives"]
        observed = [fact("inspections", c.t("f.inspections"), summary["inspections"], c.num(summary["inspections"], 0), obs),
                    fact("positives", c.t("f.positives"), summary["positives"], c.num(summary["positives"], 0), obs),
                    fact("negatives", c.t("f.negatives"), negatives, c.num(negatives, 0), obs),
                    fact("positive_share", c.t("f.positive_share"), summary.get("positive_rate"),
                         c.pct((summary.get("positive_rate") or 0) * 100, 0), obs, unit="%"),
                    fact("latest_observation", c.t("f.latest_observation"), summary.get("latest_observation"),
                         c.day(summary.get("latest_observation")), obs)]
        if summary.get("app_counts_suppressed"):
            observed.append(fact("meta.suppressed", c.t("f.hidden_cells"), True, c.t("lim.privacy_threshold", k=privacy["min_contributors"]),
                                 provenance("rule", "privacy_threshold")))
    else:
        observed = [unavailable("inspections", c.t("f.inspections"), c.t("u.no_observations"), "no_observations")]
    reg_insp = sum(cell.get("inspections") or 0 for cell in cells)
    reg_pos = sum(cell.get("positives") or 0 for cell in cells)
    regional = [fact("region_inspections", c.t("f.region_inspections"), reg_insp, c.num(reg_insp, 0), provenance("observation", "disease_observations")),
                fact("region_positives", c.t("f.region_positives"), reg_pos, c.num(reg_pos, 0), provenance("observation", "disease_observations"))]
    if reg_insp:
        regional.append(fact("region_positive_share", c.t("f.region_positive_share"), round(reg_pos / reg_insp, 4),
                             c.pct(reg_pos / reg_insp * 100, 0), provenance("observation", "disease_observations"), unit="%"))
    sections.append(section("observed", c.t("sec.observed"), subject + observed, chapter="condition",
                            note=c.t("note.observations_confirmed")))
    sections.append(section("regional_condition", c.t("sec.regional_condition"), regional, chapter="condition",
                            note=c.t("note.region", n=c.num(len(cells), 0), radius=c.num(rules["region_radius_cells"], 0))))

    # ------------------------------------------------------------------- 3. evidence
    trend = ev.get("trend") or []
    if trend:
        charts.append({"id": "trend", "kind": "bar", "title": c.t("sec.trend"), "x": [c.day(w["week_start"]) for w in trend],
                       "series": [{"key": "inspections", "label": c.t("f.inspections"), "values": [w["inspections"] for w in trend]},
                                  {"key": "positives", "label": c.t("f.positives"), "values": [w["positives"] for w in trend]}],
                       "provenance": obs})
        sections.append(section("trend", c.t("sec.trend"), [], chapter="evidence", chart_ids=["trend"]))
    last_year = ev.get("last_year")
    if last_year is not None:
        hp = provenance("historical", "disease_observations", f"geo_areas/{area['id']}")
        sections.append(section("last_year", c.t("sec.last_year"), [
            fact("ly.inspections", c.t("f.inspections"), last_year.get("inspections", 0), c.num(last_year.get("inspections", 0), 0), hp),
            fact("ly.positives", c.t("f.positives"), last_year.get("positives", 0), c.num(last_year.get("positives", 0), 0), hp)],
            chapter="evidence"))
    rows = []
    for cell in cells:
        cb = cell["area"]["bounds"]
        cp = provenance("observation", "disease_observations", f"geo_areas/{cell['area']['id']}")
        pr = cell.get("prediction")
        rows.append({"id": cell["area"]["id"], "cells": [
            fact("cell", c.t("v.cell"), cell["area"]["grid_key"], f"{c.num(cb['south'], 2)}°, {c.num(cb['west'], 2)}°", cp),
            fact("inspections", c.t("f.inspections"), cell["inspections"], c.num(cell["inspections"], 0), cp),
            fact("positives", c.t("f.positives"), cell["positives"], c.num(cell["positives"], 0), cp),
            (fact("risk", c.t("f.risk_level"), pr["risk_level"], c.t(f"v.risk.{pr['risk_level']}"),
                  provenance("model", f"{pr.get('model_name')}@{pr.get('model_version')}", f"outbreak_predictions/{pr['prediction_id']}"))
             if pr else unavailable("risk", c.t("f.risk_level"), c.t("v.risk.none"), "no_prediction"))]})
    sections.append(section("region_cells", c.t("sec.region_cells"), [], chapter="evidence", rows=rows or None,
                            note=c.t("note.region_cells")))

    wdays = ev.get("weather") or []
    if wdays:
        wp = provenance("weather_provider", "open-meteo", f"geo_areas/{area['id']}")
        forecast_from = next((i for i, w in enumerate(wdays) if w.get("kind") == "forecast"), None)
        charts.append({"id": "weather", "kind": "line", "title": c.t("sec.weather"), "x": [c.day(w["day"]) for w in wdays],
                       "series": [{"key": "rh", "label": c.t("f.humidity"), "values": [w.get("relative_humidity_mean_pct") for w in wdays]},
                                  {"key": "temp", "label": c.t("f.temperature"), "values": [w.get("temperature_mean_c") for w in wdays]},
                                  {"key": "rain", "label": c.t("f.rain_mm"), "values": [w.get("precipitation_mm") for w in wdays]}],
                       "provenance": wp, "forecast_from": forecast_from})
        observed_days = [w for w in wdays if w.get("kind") != "forecast"][-14:]
        forecast_days = [w for w in wdays if w.get("kind") == "forecast"]
        wsum = weather_summary(observed_days)
        wfacts = [fact("w.days", c.t("f.weather_days"), wsum["days"], c.num(wsum["days"], 0), wp,
                       note=c.t("note.weather_window"))]
        if wsum["rh_mean"] is not None:
            wfacts.append(fact("w.rh_mean", c.t("f.rh_mean_14d"), wsum["rh_mean"], c.pct(wsum["rh_mean"], 0), wp, unit="%"))
        if wsum["rain_total"] is not None:
            wfacts.append(fact("w.rain_total", c.t("f.rain_total_14d"), wsum["rain_total"], f"{c.num(wsum['rain_total'])} mm", wp, unit="mm"))
        if wsum["rh90_days"] is not None:
            wfacts.append(fact("w.rh90_days", c.t("f.rh90_days"), wsum["rh90_days"], c.num(wsum["rh90_days"], 0), wp))
        if wsum["missing"]:
            wfacts.append(fact("w.missing", c.t("f.weather_missing_days"), wsum["missing"], c.num(wsum["missing"], 0), wp))
        if forecast_days:
            fsum = weather_summary(forecast_days)
            wfacts.append(fact("w.fc_days", c.t("f.forecast_days"), fsum["days"], c.num(fsum["days"], 0), wp))
            if fsum["rain_total"] is not None:
                wfacts.append(fact("w.fc_rain", c.t("f.forecast_rain"), fsum["rain_total"], f"{c.num(fsum['rain_total'])} mm", wp, unit="mm"))
        sections.append(section("weather", c.t("sec.weather"), wfacts, chapter="evidence", chart_ids=["weather"],
                                note=c.t("note.weather_forecast")))
    else:
        sections.append(section("weather", c.t("sec.weather"),
                                [unavailable("weather", c.t("sec.weather"), c.t("u.no_weather_area"), "no_weather_area")], chapter="evidence"))
    suit = ev.get("suitability") or []
    if suit:
        sfacts = []
        for s in suit:
            refs = cites.cite(f"rule:{s.get('rule')}") if s.get("reference_id") else []
            sfacts.append(fact(f"suit.{s['profile_id']}", s.get("description") or s["profile_id"], s["status"],
                               c.t(f"v.suitability.{s['status']}"), provenance("sourced_rule", s["profile_id"], citation=s.get("source")),
                               lang=KB_LANG, refs=refs,
                               note=c.t("note.suitability_periods", n=c.num(len(s.get("periods") or []), 0)) if s.get("periods") else None))
        sections.append(section("suitability", c.t("sec.suitability"), sfacts, chapter="evidence", note=c.t("note.suitability")))

    # --------------------------------------------------------------- 5. interpretation
    calc = []
    mp = provenance("model", f"{(pred or {}).get('model_name')}@{(pred or {}).get('model_version')}",
                    f"outbreak_predictions/{(pred or {}).get('prediction_id')}") if pred else provenance("system")
    details = card.get("details") or {}
    cut = details.get("risk_cutpoints") or [0.25, 0.5, 0.75]
    risk = []
    if has_pred:
        score = pred.get("score")
        risk = [fact("risk_level", c.t("f.risk_level"), pred["risk_level"], c.t(f"v.risk.{pred['risk_level']}"), mp,
                     note=c.t("chrome.prediction_not_observation")),
                fact("risk_score", c.t("f.risk_score"), score,
                     f"{c.num(score, 2)} ({c.t('v.score.' + (pred.get('score_kind') or 'risk_score'))})", mp),
                fact("risk_confidence", c.t("f.risk_confidence"), pred.get("confidence_level"),
                     c.t(f"v.confidence.{pred.get('confidence_level')}") if pred.get("confidence_level") else "—", mp),
                fact("completeness", c.t("f.completeness"), pred.get("data_completeness"),
                     c.pct((pred.get("data_completeness") or 0) * 100, 0), mp, unit="%"),
                fact("forecast_period", c.t("f.forecast_period"), [pred.get("forecast_start"), pred.get("forecast_end")],
                     f"{c.day(pred.get('forecast_start'))} – {c.day(pred.get('forecast_end'))}", mp)]
        calc.append(statement(c.t("st.oa.model", n=c.num(len(pred.get("features") or {}), 0)), "model", mp))
        lo, hi = _band(score, cut)
        calc.append(statement(c.t("st.oa.level", score=c.num(score, 2), lo=c.num(lo, 2) if lo is not None else "0",
                                  hi=c.num(hi, 2) if hi is not None else "1", level=c.t(f"v.risk.{pred['risk_level']}"),
                                  cuts=" / ".join(c.num(x, 2) for x in cut)), "rule", provenance("rule", "risk_cutpoints"),
                              evidence=["risk_score", "risk_level"]))
        calc.append(statement(c.t("st.oa.calibrated" if pred.get("score_kind") == "calibrated_probability" else "st.oa.uncalibrated"),
                              "model", mp))
        calc.append(statement(c.t(f"st.oa.confidence.{pred.get('confidence_level') or 'low'}",
                                  completeness=c.pct((pred.get("data_completeness") or 0) * 100, 0)), "rule",
                              provenance("rule", "estimate_confidence"), evidence=["risk_confidence", "completeness"]))
        test = (card.get("metrics") or {}).get("test") or {}
        if test.get("roc_auc") is not None:
            key = "st.oa.test_metrics" if test.get("brier") is not None else "st.oa.test_metrics_nobrier"
            calc.append(statement(c.t(key, auc=c.num(test.get("roc_auc"), 2), pr=c.num(test.get("pr_auc"), 2),
                                      brier=c.num(test.get("brier"), 3), base=c.pct((test.get("base_rate") or 0) * 100, 1),
                                      n=c.num(test.get("samples"), 0)),
                                  "evaluation", provenance("model_evaluation", f"{card.get('name')}@{card.get('version')}")))
        else:
            calc.append(statement(c.t("st.oa.no_test_metrics"), "missing", provenance("system")))
        if details.get("forecast_features_training_source"):
            calc.append(statement(c.t("st.oa.perfect_forecast"), "rule", provenance("rule", "model card")))
        if pred.get("score_kind") != "calibrated_probability":
            limitations.append("lim.score_not_calibrated")
        limitations.append("lim.weather_forecast")
    else:
        risk = [unavailable("risk_level", c.t("f.risk_level"), c.t("u.no_prediction"), "no_prediction")]
        calc.append(statement(c.t("st.oa.no_estimate"), "missing", provenance("system")))
    sections.append(section("risk", c.t("sec.risk"), risk, chapter="interpretation", statements=calc,
                            note=c.t("chrome.prediction_not_observation")))

    # factors: what pushes this estimate, relative to the training data
    if has_pred:
        frows = []
        for f in pred.get("factors") or []:
            rng = f.get("typical_range") or []
            frows.append({"id": f["feature"], "cells": [
                fact("feature", c.t("f.feature"), f["feature"], c.t(f"feat.{f['feature']}"), mp),
                fact("value", c.t("f.value_now"), f.get("value"), c.num(f.get("value"), 1) if f.get("value") is not None else "—", mp),
                fact("typical", c.t("f.typical_range"), rng,
                     f"{c.num(rng[0], 1)} – {c.num(rng[1], 1)}" if len(rng) == 2 and None not in rng else "—", mp),
                fact("relation", c.t("f.relation"), f.get("relation"), c.t(f"rel.{f.get('relation')}"), mp),
                fact("importance", c.t("f.importance"), f.get("importance"), c.num(f.get("importance"), 3), mp)]})
        sections.append(section("factors", c.t("sec.factors"), [] if frows else
                                [unavailable("factors", c.t("sec.factors"), c.t("u.no_factors"), "no_factors")],
                                chapter="interpretation", rows=frows or None, note=c.t("note.factors")))

    # why this cell's estimate is higher or lower than its neighbours'
    compare = []
    own = next((cell for cell in cells if cell["area"]["id"] == area["id"]), None)
    others = [cell for cell in cells if cell["area"]["id"] != area["id"]]
    if summary and summary.get("inspections") and reg_insp:
        own_rate = (summary.get("positive_rate") or 0) * 100
        reg_rate = reg_pos / reg_insp * 100
        compare.append(statement(c.t("st.oa.share_vs_region", own=c.pct(own_rate, 0), region=c.pct(reg_rate, 0),
                                     cmp=c.t("cmp.higher" if own_rate > reg_rate else "cmp.lower" if own_rate < reg_rate else "cmp.same")),
                                 "observation", obs, evidence=["positive_share", "region_positive_share"]))
    rank = {"low": 1, "moderate": 2, "high": 3, "critical": 4}
    other_levels = [(cell.get("prediction") or {}).get("risk_level") for cell in others]
    other_levels = [lv for lv in other_levels if lv in rank]
    if has_pred and other_levels:
        higher = sum(1 for lv in other_levels if rank[lv] > rank.get(pred["risk_level"], 0))
        lower = sum(1 for lv in other_levels if rank[lv] < rank.get(pred["risk_level"], 0))
        compare.append(statement(c.t("st.oa.level_vs_neighbours", n=c.num(len(other_levels), 0), higher=c.num(higher, 0),
                                     lower=c.num(lower, 0)), "model", provenance("model", "outbreak predictions")))
    if has_pred:
        above = [c.t(f"feat.{f['feature']}") for f in pred.get("factors") or [] if f.get("relation") == "above_typical"][:3]
        below = [c.t(f"feat.{f['feature']}") for f in pred.get("factors") or [] if f.get("relation") == "below_typical"][:3]
        if above:
            compare.append(statement(c.t("st.oa.factors_above", factors=", ".join(above)), "model", mp))
        if below:
            compare.append(statement(c.t("st.oa.factors_below", factors=", ".join(below)), "model", mp))
        compare.append(statement(c.t("st.oa.association"), "rule", provenance("rule", "report-integrity")))
    sections.append(section("why_level", c.t("sec.why_level"), [] if compare else
                            [unavailable("why_level", c.t("sec.why_level"), c.t("u.no_comparison"), "no_comparison")],
                            chapter="interpretation", statements=compare or None))

    # coverage and missing data
    no_insp = sum(1 for cell in cells if not cell.get("inspections"))
    no_est = sum(1 for cell in cells if not cell.get("prediction"))
    expected = (2 * int(rules["region_radius_cells"]) + 1) ** 2
    cov = [fact("count.cells", c.t("f.cells"), len(cells), c.num(len(cells), 0), provenance("observation", "geo_areas"),
                note=c.t("note.cells_expected", n=c.num(expected, 0))),
           fact("count.no_inspections", c.t("f.cells_no_inspections"), no_insp, c.num(no_insp, 0), provenance("observation", "geo_areas")),
           fact("count.no_estimate", c.t("f.cells_no_estimate"), no_est, c.num(no_est, 0), provenance("model", "outbreak predictions")),
           fact("count.hidden", c.t("f.hidden_cells"), region.get("hidden_for_privacy", 0), c.num(region.get("hidden_for_privacy", 0), 0),
                provenance("rule", "privacy_threshold"))]
    extent = details.get("training_extent")
    if extent and has_pred:
        inside = "outside_training_region" not in (pred.get("limitations") or [])
        cov.append(fact("training_region", c.t("f.training_region"), inside, c.t("v.inside" if inside else "v.outside"),
                        provenance("model", f"{card.get('name')}@{card.get('version')}")))
    for code in (pred or {}).get("limitations") or []:
        cov.append(fact(f"plim.{code}", c.t("f.estimate_limitation"), code, c.t(f"plim.{code}"), mp))
    sections.append(section("coverage", c.t("sec.coverage"), cov, chapter="interpretation", note=c.t("note.coverage")))

    # ------------------------------------------------------------------- 4. visual
    media.append({"id": "region_map", "kind": "region_map", "generated": True, "title": c.t("sec.map"), "caption": c.t("sec.map"),
                  "explanation": c.t("m.explain.region_map", deg=c.num(res, 2)), "provenance": provenance("observation", "disease_observations")})
    sections.append(section("distribution", c.t("sec.map"), [], chapter="visual", map=True, media_ids=["region_map"]))

    # ------------------------------------------------------------------- 6. actions
    pri = inspection_priorities(cells, rules, area["id"])
    prow = []
    for i, item in enumerate(pri):
        cell, reasons = item["cell"], item["reasons"]
        cb = cell["area"]["bounds"]
        prow.append({"id": cell["area"]["id"], "cells": [
            fact("rank", "#", i + 1, c.num(i + 1, 0), provenance("rule", "inspection-priority-v2")),
            fact("cell", c.t("v.cell"), cell["area"]["grid_key"],
                 f"{c.num(cb['south'], 2)}°, {c.num(cb['west'], 2)}°" + (f" ({c.t('v.selected')})" if cell["area"]["id"] == area["id"] else ""),
                 provenance("system", "geo_areas")),
            fact("reasons", c.t("f.reasons"), [r["code"] for r in reasons],
                 " · ".join(c.t(f"pri.{r['code']}", **{k: c.num(v, 0) if isinstance(v, (int, float)) else c.t(f"v.risk.{v}")
                                                     for k, v in r.items() if k != "code"}) for r in reasons),
                 provenance("rule", "inspection-priority-v2"))]})
    sections.append(section("inspection_priorities", c.t("sec.inspection_priorities"), [] if prow else
                            [unavailable("priorities", c.t("sec.inspection_priorities"), c.t("u.no_priorities"), "none")],
                            chapter="actions", rows=prow or None, note=c.t("note.priorities")))

    kb = ev.get("kb_disease")
    if kb and ev.get("kb_treatments"):
        limitations.append("lim.kb_not_region_specific")

    # ------------------------------------------------------------------ 7. monitoring
    plan = [{"text": c.t("mon.oa.weekly"), "provenance": provenance("reference", "scouting guidance"), "refs": cites.cite("guidance:scouting")},
            {"text": c.t("mon.oa.record_negatives"), "provenance": provenance("rule", "outbreak data")}]
    if has_pred and pred.get("forecast_end"):
        plan.append({"text": c.t("mon.oa.after_window"), "when": c.day(pred["forecast_end"]), "provenance": provenance("rule", "forecast window")})
    sections.append(section("monitoring_plan", c.t("sec.monitoring_plan"), [], chapter="monitoring", items=plan))

    limitation_texts = [c.t(k) for k in dict.fromkeys(limitations)] + [
        c.t("lim.grid_coarse", res=privacy["grid_resolution_deg"]), c.t("lim.privacy_threshold", k=privacy["min_contributors"])]
    key_facts = [observed[0]] + ([observed[1]] if len(observed) > 1 else []) + [risk[0]] + [cov[0]]
    methods = [{"id": "outbreak_model", "name": c.t("m.outbreak_model"), "kind": "model",
                "version": f"{pred.get('model_name')}@{pred.get('model_version')}" if pred else None,
                "synthetic": bool(ev.get("model_synthetic"))}]
    if suit:
        methods.append({"id": "suitability", "name": c.t("sec.suitability"), "kind": "sourced_rule", "version": "profiles"})
    methods.append({"id": "priorities", "name": c.t("m.priorities"), "kind": "rule", "version": "inspection-priority-v2"})
    status_code = f"risk_{pred['risk_level']}" if has_pred else "no_current_estimate"
    content = {
        "type": "outbreak_area",
        "title": f"{c.t('type.outbreak_area')} — {humanize(crop)} / {humanize(disease)}",
        "subject": {"area_id": area["id"], "grid_key": area["grid_key"], "bounds": b, "crop": crop, "disease": disease,
                    "date_from": ev["date_from"], "date_to": ev["date_to"], "region_cells": [cell["area"] for cell in cells]},
        "status": {"code": status_code,
                   "label": c.t(f"v.risk.{pred['risk_level']}") if has_pred else c.t("v.risk.none"),
                   "provenance": provenance("model", "outbreak") if pred else provenance("system"),
                   "qualifier": c.t("chrome.prediction_not_observation")},
        "crop": crop, "disease": disease, "period": [ev["date_from"], ev["date_to"]],
        # Aggregated cells only (privacy-filtered by OutbreakService.map_layer) for the map views.
        "map": {"selected": area["grid_key"], "cells": [
            {"area": cell["area"], "inspections": cell.get("inspections"), "positives": cell.get("positives"),
             "prediction": {"risk_level": cell["prediction"]["risk_level"]} if cell.get("prediction") else None}
            for cell in cells]},
        "key_facts": key_facts, "sections": sections, "media": media, "charts": charts,
        "limitations": limitation_texts, "methods": methods,
    }
    return _finish(content, cites, c, ["summary", "condition", "evidence", "visual", "interpretation", "actions", "monitoring",
                                       "limitations", "references"], {"condition": c.t("ch.condition_region")})


def _band(score: Optional[float], cuts: List[float]):
    if score is None:
        return None, None
    lo = None
    for cut in cuts:
        if score < cut:
            return lo, cut
        lo = cut
    return lo, None


def weather_summary(days: List[dict]) -> dict:
    """Aggregates over stored daily weather; missing values are counted, never filled."""
    rh = [w["relative_humidity_mean_pct"] for w in days if w.get("relative_humidity_mean_pct") is not None]
    rain = [w["precipitation_mm"] for w in days if w.get("precipitation_mm") is not None]
    rh90 = [w["rh_hours_ge_90"] for w in days if w.get("rh_hours_ge_90") is not None]
    missing = sum(1 for w in days if w.get("relative_humidity_mean_pct") is None or w.get("precipitation_mm") is None)
    return {"days": len(days), "rh_mean": round(sum(rh) / len(rh), 1) if rh else None,
            "rain_total": round(sum(rain), 1) if rain else None,
            "rh90_days": sum(1 for h in rh90 if h >= 6) if rh90 else None, "missing": missing}


def inspection_priorities(cells: List[dict], rules: dict, selected_id: str, limit: int = 8) -> List[dict]:
    """Cells to inspect first, by explicit rule: confirmed positives (weight 3 each, capped),
    a high estimated risk (2), and no inspections next to a cell with positives (1)."""
    high = set(rules["high_risk_levels"])
    by_key = {cell["area"]["grid_key"]: cell for cell in cells}
    out = []
    for cell in cells:
        reasons, score = [], 0.0
        if cell.get("positives"):
            reasons.append({"code": "positives", "n": cell["positives"]})
            score += 3 + min(cell["positives"], 10) * 0.1
        level = (cell.get("prediction") or {}).get("risk_level")
        if level in high:
            reasons.append({"code": "high_estimate", "level": level})
            score += 2
        if not cell.get("inspections"):
            lat, lon = _key_index(cell["area"]["grid_key"])
            if lat is not None:
                near = [by_key.get(_index_key(cell["area"]["grid_key"], lat + dy, lon + dx))
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]
                if any(n and n.get("positives") for n in near):
                    reasons.append({"code": "coverage_gap"})
                    score += 1
        if reasons:
            out.append({"cell": cell, "reasons": reasons, "score": score, "selected": cell["area"]["id"] == selected_id})
    out.sort(key=lambda x: (-x["score"], not x["selected"], x["cell"]["area"]["grid_key"]))
    return out[:limit]


def _key_index(key: str):
    """Grid keys look like '<res>:<lat_index>:<lon_index>' (ai/outbreak/grid.py)."""
    parts = str(key).split(":")
    try:
        return int(parts[-2]), int(parts[-1])
    except (ValueError, IndexError):
        return None, None


def _index_key(key: str, lat: int, lon: int) -> str:
    parts = str(key).split(":")
    return ":".join(parts[:-2] + [str(lat), str(lon)])
