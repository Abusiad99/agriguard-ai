"""Report content v2 (evidence, visual analysis, recommendations, recovery, regional
risk, references) built from SYNTHETIC evidence. Builders are pure functions, so these
tests check exact numbers against the inputs. Nothing here is a real result."""
from __future__ import annotations

import copy
import io
import json
import re

import pytest

from app.application.reporting import builders
from app.application.reporting.content import SCHEMA_VERSION, validate_content
from app.application.reporting.i18n import T
from app.application.reporting.i18n_extra import EXTRA
from app.application.reporting.recommendations import (diagnosis_recommendations, load_rules, outbreak_recommendations,
                                                       plant_progress_recommendations)
from app.application.reporting.references import Citations, load_catalog, validate_catalog

RULES = load_rules()
SEG_MODEL = "disease-segmentation@v-test"


def generate(build, recommend, ev, locale="en"):
    """What ReportService.generate does, minus the database and the narrative."""
    cites = Citations(locale, ev.get("kb_references"))
    content = build(ev, locale, cites)
    content["recommendations"] = recommend(ev, content, locale, cites)
    content["references"] = cites.to_list()
    content["schema"] = SCHEMA_VERSION
    return content


def facts(content):
    out = {}
    for f in content["key_facts"]:
        out.setdefault(f["key"], f)
    for sec in content["sections"]:
        for f in sec["facts"]:
            out.setdefault(f["key"], f)
    return out


def sections(content):
    return {s["id"]: s for s in content["sections"]}


def recs(content):
    return {r["rule"]: r for r in content["recommendations"]}


# ------------------------------------------------------------------------- fixtures
def diagnosis_ev():
    """SYNTHETIC: a close call between late and early blight, with segmentation, test metrics,
    a tracked history, a recent treatment and windy, rainy weather."""
    return {
        "diagnosis": {
            "id": "11111111-1111-1111-1111-111111111111", "diagnosed_at": "2026-11-01T10:00:00+00:00", "plant_name": "tomato",
            "predicted_condition": "late_blight", "is_healthy": False, "confidence": 61.0, "low_confidence": False,
            "severity_level": "moderate", "gradcam_area_pct": 22.0,
            "quality": {"width": 1024, "height": 768, "mean_luma": 120.0, "sharpness": 300.0, "issues": [], "acceptable": True},
            "top_predictions": [{"plant": "tomato", "condition": "late_blight", "confidence": 61.0},
                                {"plant": "tomato", "condition": "early_blight", "confidence": 52.0},
                                {"plant": "tomato", "condition": "healthy", "confidence": 3.0}],
            "original_ref": "scans/a.jpg", "heatmap_ref": "heatmaps/a.png", "location_shared": False,
            "weather": {"temperature_c": 24.0, "humidity_pct": 88.0, "wind_speed_kmh": 18.0, "rain_probability_pct": 70.0,
                        "retrieved_at": "2026-11-01T10:00:00+00:00"},
        },
        "classifier": {"name": "plant-disease-classifier", "version": "run-test", "num_classes": 38, "synthetic": True,
                       "test": {"accuracy": 0.9, "n_test": 1000, "record": "model_runs/run-test/metrics.json",
                                "classes": {"tomato___late_blight": {"precision": 0.72, "recall": 0.81, "f1": 0.76, "support": 120},
                                            "tomato___early_blight": {"precision": 0.9, "recall": 0.88, "f1": 0.89, "support": 130}}}},
        "segmentation": {"id": "seg1", "status": "ok", "model_name": "disease-segmentation", "model_version": "v-test",
                         "affected_pct": 12.5, "plant_pixels": 8000, "affected_pixels": 1000, "reason": None,
                         "regions": [{"label": "lesion", "class_id": 2, "pixels": 600, "mean_confidence": 0.8},
                                     {"label": "lesion", "class_id": 2, "pixels": 400, "mean_confidence": 0.6}],
                         "class_pixels": {"background": 2000, "leaf": 7000, "lesion": 1000},
                         "classes": [{"id": 0, "name": "background", "kind": "background"}, {"id": 1, "name": "leaf", "kind": "leaf"},
                                     {"id": 2, "name": "lesion", "kind": "disease"}],
                         "area_basis": "plant_pixels", "mean_uncertainty": 0.2, "mean_confidence": 0.75,
                         "artifact_dir": "segmentations/x", "synthetic": True},
        "kb_disease": {"id": "kb1", "name": "late_blight", "plant": "tomato", "description": "Synthetic description.",
                       "symptoms": ["water-soaked lesions (synthetic)"], "causes": [], "transmission": None,
                       "recovery_probability": None, "recovery_time": None, "version": 1},
        "kb_treatments": [{"id": "t1", "category": "organic", "instructions": "Remove affected leaves (synthetic).",
                           "safety_notes": None, "citation": "Synthetic citation text", "referral_only": False,
                           "displayable": True, "version": 1}],
        "kb_references": [{"id": "0000aaaa-0000-0000-0000-000000000001", "title": "Synthetic KB source", "authors": None,
                           "organization": "Test Extension", "url": "https://example.test/lb", "doi": None,
                           "publication_date": "2020", "source_type": "university_extension", "language": "en",
                           "verified_on": "2026-11-01",
                           "claims": [{"subject": "disease:tomato/late_blight", "claim": "Synthetic claim about symptoms"},
                                      {"subject": "treatment:t1", "claim": "Synthetic claim about the treatment"}]}],
        "alt_kb": {"tomato___early_blight": {"id": "kb2", "name": "early_blight", "version": 1,
                                             "symptoms": ["target-like rings (synthetic)"]}},
        "tracked": {"plant_id": "p1", "name": "Row 1", "scans": 3, "latest_status": "inconclusive", "method_version": "rules-v1",
                    "assessment": {"status": "inconclusive", "method_version": "rules-v1", "area_series": []},
                    "history": [{"id": "h1", "diagnosed_at": "2026-10-20T10:00:00+00:00", "condition": "early_blight",
                                 "confidence": 70.0, "area_pct": 8.0, "area_model": SEG_MODEL, "original_ref": "scans/h1.jpg",
                                 "overlay_key": "segmentations/h1/overlay.png"}],
                    "treatments": 1,
                    "recent_treatments": [{"id": "tr1", "name": "Copper spray (synthetic)", "category": "organic",
                                           "applied_on": "2026-10-25"}],
                    "next_reminder": None, "overdue": 0},
        "area": None, "rules": RULES,
    }


def plant_ev():
    """SYNTHETIC: four scans; one measured by another model version, one blurry."""
    def scan(i, day, area, model=SEG_MODEL, issues=(), severity="moderate"):
        return {"id": f"d{i}", "diagnosed_at": f"2026-{day}T09:00:00+00:00", "condition": "late_blight", "is_healthy": False,
                "confidence": 80.0, "low_confidence": False, "severity_level": severity, "area_pct": area, "area_model": model,
                "quality_issues": list(issues), "area_reason": None, "stage": "during_treatment",
                "original_ref": f"scans/d{i}.jpg", "overlay_key": f"segmentations/d{i}/overlay.png", "disease_id": None}
    scans = [scan(1, "09-01", 20.0), scan(2, "09-08", 15.0, model="disease-segmentation@v-old"),
             scan(3, "09-10", 30.0, issues=["blurry"], severity="severe"), scan(4, "10-01", 9.0, severity="mild")]
    return {
        "plant": {"id": "p1", "name": "Row 1 (synthetic)", "crop": "tomato", "species": None, "created_at": "2026-09-01T09:00:00+00:00"},
        "scans": scans,
        "assessment": {"id": "a1", "status": "improving", "method_version": "rules-v1",
                       "limitations": ["incompatible_segmentation_models", "some_images_failed_quality_checks"],
                       "area_series": [{"diagnosis_id": "d1", "taken_at": "2026-09-01T09:00:00+00:00", "area_pct": 20.0, "model": SEG_MODEL},
                                       {"diagnosis_id": "d4", "taken_at": "2026-10-01T09:00:00+00:00", "area_pct": 9.0, "model": SEG_MODEL}],
                       "indicators": [{"code": "classifier_confidence", "from": 80.0, "to": 80.0}]},
        "treatments": [{"id": "tr1", "name": "Copper spray (synthetic)", "category": "organic", "applied_on": "2026-09-05", "dosage_text": None},
                       {"id": "tr2", "name": "Removed leaves (synthetic)", "category": "cultural", "applied_on": "2026-10-05",
                        "dosage_text": None}],
        "events": [{"occurred_at": "2026-09-01T09:00:00+00:00", "event_type": "plant_created"},
                   {"occurred_at": "2026-09-05T09:00:00+00:00", "event_type": "treatment_recorded"}],
        "reminders": [{"due_on": "2026-10-10", "state": "overdue"}], "next_reminder": None, "overdue_reminders": 1,
        "recovery_rules": {"stable_band_pct": 5.0, "min_days_between": 1.0, "blocking_quality_issues": ["blurry", "too_dark", "overexposed"]},
        "today": "2026-10-20", "kb_disease": None, "kb_treatments": [], "kb_references": [], "rules": RULES,
        "segmentation_synthetic": True,
    }


def _cell(key, insp, pos, level=None):
    lat, lon = (int(x) for x in key.split(":")[1:])
    area = {"id": f"area-{lat}-{lon}", "grid_key": key, "resolution_deg": 0.25,
            "bounds": {"south": lat * 0.25, "west": lon * 0.25, "north": (lat + 1) * 0.25, "east": (lon + 1) * 0.25}}
    pred = {"risk_level": level, "prediction_id": f"pred-{lat}-{lon}", "model_name": "outbreak-risk", "model_version": "run1"} if level else None
    return {"area": area, "inspections": insp, "positives": pos, "prediction": pred}


def outbreak_ev():
    """SYNTHETIC: a high estimate in a cell with confirmed cases, an uninspected neighbour."""
    cells = [_cell("0.25:40:80", 20, 6, "high"), _cell("0.25:40:81", 10, 0, "low"), _cell("0.25:41:80", 0, 0),
             _cell("0.25:39:79", 5, 2, "moderate")]
    weather = [{"day": f"2026-10-{d:02d}", "kind": "observed", "temperature_mean_c": 14.0, "relative_humidity_mean_pct": 85.0,
                "rh_hours_ge_90": 7.0 if d % 2 else 3.0, "precipitation_mm": 2.0} for d in range(15, 29)]
    weather += [{"day": f"2026-10-{d}", "kind": "forecast", "temperature_mean_c": 13.0, "relative_humidity_mean_pct": 90.0,
                 "rh_hours_ge_90": 8.0, "precipitation_mm": 4.0} for d in (29, 30, 31)]
    return {
        "area": {"id": "area-40-80", "grid_key": "0.25:40:80", "bounds": cells[0]["area"]["bounds"]},
        "crop": "potato", "disease": "late_blight", "date_from": "2026-08-01", "date_to": "2026-10-28",
        "summary": {"inspections": 20, "positives": 6, "positive_rate": 0.3, "latest_observation": "2026-10-27"},
        "trend": [{"week_start": "2026-10-19", "inspections": 8, "positives": 3}, {"week_start": "2026-10-26", "inspections": 12, "positives": 3}],
        "last_year": {"inspections": 9, "positives": 1}, "weather": weather,
        "suitability": [{"profile_id": "hutton_criteria_potato_late_blight", "rule": "hutton_criteria", "reference_id": "ref-hutton",
                         "status": "met", "periods": [{"start": "2026-10-15", "end": "2026-10-16"}],
                         "source": "Hutton Criteria (AHDB)", "description": "Two consecutive days ..."}],
        "region": {"cells": cells, "hidden_for_privacy": 1},
        "prediction": {"prediction_id": "pred-40-80", "status": "ok", "risk_level": "high", "score": 0.62,
                       "score_kind": "calibrated_probability", "confidence_level": "medium", "data_completeness": 0.8,
                       "model_name": "outbreak-risk", "model_version": "run1", "forecast_start": "2026-10-29",
                       "forecast_end": "2026-11-04", "features": {f"f{i}": i for i in range(22)}, "limitations": [],
                       "factors": [{"feature": "rh90_hours_7d", "value": 30.0, "importance": 0.12, "relation": "above_typical",
                                    "typical_range": [5.0, 15.0]},
                                   {"feature": "temp_mean_7d", "value": 8.0, "importance": 0.05, "relation": "below_typical",
                                    "typical_range": [12.0, 20.0]}]},
        "model_card": {"name": "outbreak-risk", "version": "run1",
                       "details": {"risk_cutpoints": [0.25, 0.5, 0.75], "training_extent": {"lat_index": [38, 42], "lon_index": [78, 82]},
                                   "forecast_features_training_source": "observed_weather_perfect_forecast_assumption"},
                       "metrics": {"test": {"samples": 400, "positives": 60, "base_rate": 0.15, "roc_auc": 0.81, "pr_auc": 0.44,
                                            "brier": 0.11}}},
        "kb_disease": None, "kb_treatments": [], "data_gap": False,
        "privacy": {"grid_resolution_deg": 0.25, "min_contributors": 3}, "rules": RULES, "model_synthetic": True,
    }


# ------------------------------------------------------------------------ catalog
class TestReferenceCatalog:
    def test_catalog_is_valid_and_bilingual(self):
        data = load_catalog()
        assert validate_catalog(data) == []
        assert {r["id"] for r in data["references"]} >= {"ref-gradcam", "ref-calibration", "ref-field-gap", "ref-hutton",
                                                          "ref-umn-prevention", "ref-spray-wind", "ref-rainfast",
                                                          "ref-cornell-sampling"}
        for r in data["references"]:
            assert r["url"].startswith("https://") and r["verified_on"] and r["organization"]

    def test_catalog_problems_are_reported(self):
        bad = {"references": [{"id": "x", "title": "t", "url": "http://insecure", "organization": "o", "source_type": "blog",
                               "verified_on": "2026-01-01", "claims": [{"subject": "nonsense", "en": "a"}]}]}
        problems = " ".join(validate_catalog(bad))
        assert "https" in problems and "source_type" in problems and "subject" in problems and "Arabic" in problems

    def test_citations_number_in_order_of_first_use(self):
        cites = Citations("en")
        assert cites.cite("guidance:scouting") == ["ref-umn-prevention"]
        assert cites.cite("method:gradcam") == ["ref-gradcam"]
        cites.cite("guidance:rotation")  # same reference again: same number, second claim added
        refs = cites.to_list()
        assert [(r["id"], r["n"]) for r in refs] == [("ref-umn-prevention", 1), ("ref-gradcam", 2)]
        assert len(refs[0]["claims"]) == 2 and cites.cite("guidance:no_such_thing") == []

    def test_strings_have_the_same_placeholders_in_both_languages(self):
        assert set(EXTRA["en"]) == set(EXTRA["ar"])
        for key, en in EXTRA["en"].items():
            assert set(re.findall(r"{(\w+)}", en)) == set(re.findall(r"{(\w+)}", EXTRA["ar"][key])), key
        assert set(T["en"]) == set(T["ar"])


# ---------------------------------------------------------------------- diagnosis
class TestDiagnosisReport:
    def test_evidence_numbers_are_computed_from_the_inputs(self):
        c = generate(builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev())
        assert validate_content(c) == []
        f, sec = facts(c), sections(c)
        assert f["margin"]["value"] == 9.0 and f["margin"]["note"]                       # 61 - 52, below the 15 pp threshold
        assert f["test_recall"]["display"] == "81%" and f["test_precision"]["value"] == 0.72
        assert f["test_recall"]["provenance"]["kind"] == "model_evaluation"
        assert f["area_measured"]["value"] == 12.5 and f["area_measured"]["provenance"]["kind"] == "model_measurement"
        assert f["area_estimate"]["provenance"]["kind"] == "model_estimate" and f["area_estimate"]["refs"] == ["ref-gradcam"]
        lesion = sec["findings"]["rows"][0]["cells"]
        assert [x["value"] for x in lesion][:4] == ["lesion", 2, 1000, 12.5]             # 1000 / 8000 plant pixels
        assert lesion[4]["value"] == 0.7                                                 # mean of 0.8 and 0.6
        kinds = [s["kind"] for s in sec["reasoning"]["statements"]]
        assert kinds[:3] == ["model", "model", "rule"] and {"evaluation", "estimate", "measured", "knowledge", "reference"} <= set(kinds)
        measured = next(s for s in sec["reasoning"]["statements"] if s["kind"] == "measured")
        assert "12.5%" in measured["text"] and "1,000 of 8,000" in measured["text"]
        # alternatives show the knowledge-base symptoms that tell them apart
        alt = sec["alternatives"]["rows"][0]["cells"]
        assert alt[1]["value"] == 52.0 and alt[2]["value"] == 0.88 and "target-like rings" in alt[3]["display"]
        assert sec["alternatives"]["note"].startswith("The evidence does not clearly separate")

    def test_no_share_of_tissue_without_a_valid_denominator(self):
        ev = diagnosis_ev()
        ev["segmentation"].update(affected_pct=None, plant_pixels=9, affected_pixels=9, reason="too_little_plant_tissue_detected",
                                  regions=[], class_pixels={"background": 50000, "leaf": 0, "lesion": 9})
        c = generate(builders.build_diagnosis, diagnosis_recommendations, ev)
        share = {x["key"]: x for x in sections(c)["findings"]["rows"][0]["cells"]}["share"]
        assert share["available"] is False and share["reason_code"] == "too_little_plant_tissue_detected"
        assert facts(c)["area_measured"]["reason_code"] == "too_little_plant_tissue_detected"

    def test_visual_panels_and_history(self):
        c = generate(builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev())
        media = {m["id"]: m for m in c["media"]}
        assert media["segmentation_overlay"]["overlay_of"] == "photo" and media["segmentation_contours"]["overlay_of"] == "photo"
        assert "overlay_of" not in media["segmentation_mask"]
        assert media["attention_heatmap" if "attention_heatmap" in media else "heatmap"]["provenance"]["kind"] == "model_estimate"
        assert all(media[k]["explanation"] for k in ("photo", "heatmap", "segmentation_overlay", "segmentation_mask"))
        hist = sections(c)["history"]
        assert media["history_0"]["storage_key"] == "scans/h1.jpg" and media["history_0_overlay"]["overlay_of"] == "history_0"
        assert hist["rows"][0]["cells"][3]["value"] == 8.0
        assert hist["facts"][1]["reason_code"] == "no_area_series"                       # no comparable series yet: said, not drawn

    def test_recommendations_use_context_and_cite_sources(self):
        c = generate(builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev())
        r = recs(c)
        confirm = r["R-DX-CONFIRM"]
        assert confirm["horizon"] == "immediate" and confirm["basis"] == "reference" and "ref-cornell-sampling" in confirm["refs"]
        assert "gap to the next class is small" in confirm["reason"] and "test precision" in confirm["reason"]
        spray = r["R-DX-SPRAY-CONDITIONS"]
        assert spray["priority"] == "medium" and set(spray["refs"]) == {"ref-spray-wind", "ref-rainfast"}
        assert "18.0 km/h" in spray["reason"] and "70%" in spray["reason"]
        assert "R-DX-LABEL-CHANGED" in r and "Early blight" in r["R-DX-LABEL-CHANGED"]["reason"]
        assert "R-DX-RECENT-TREATMENT" in r
        kb = r["R-KB-TREATMENT"]
        assert kb["basis"] == "knowledge_base" and kb["refs"] == ["kb-0000aaaa-0000-0000-0000-000000000001"]
        assert any("You recorded a treatment of this type" in w for w in kb["warnings"])
        assert kb["timing"] == "After the diagnosis is confirmed"                       # uncertain prediction
        ref_ids = {x["id"] for x in c["references"]}
        assert "kb-0000aaaa-0000-0000-0000-000000000001" in ref_ids
        kb_ref = next(x for x in c["references"] if x["origin"] == "knowledge_base")
        assert set(kb_ref["claims"]) == {"Synthetic claim about symptoms", "Synthetic claim about the treatment"}
        for rec in c["recommendations"]:
            assert rec["basis"] in ("reference", "knowledge_base", "agriguard_rule", "general_guidance")
            assert set(rec["refs"]) <= ref_ids
        assert not re.search(r"\d+\s*(ml|g|l)\b", json.dumps([x["reason"] for x in c["recommendations"]]))

    def test_spray_conditions_within_limits_are_said_with_the_source(self):
        ev = diagnosis_ev()
        ev["diagnosis"]["weather"].update(wind_speed_kmh=8.0, rain_probability_pct=10.0)
        spray = recs(generate(builders.build_diagnosis, diagnosis_recommendations, ev))["R-DX-SPRAY-CONDITIONS"]
        assert spray["priority"] == "low" and spray["title"].startswith("Spraying conditions at scan time were within")

    def test_healthy_prediction_has_no_disease_actions(self):
        ev = diagnosis_ev()
        ev["diagnosis"].update(predicted_condition="healthy", is_healthy=True, severity_level=None, gradcam_area_pct=None,
                               heatmap_ref=None, top_predictions=None)
        ev.update(kb_disease=None, kb_treatments=[], kb_references=[], tracked=None, segmentation=None)
        c = generate(builders.build_diagnosis, diagnosis_recommendations, ev)
        assert validate_content(c) == []
        r = recs(c)
        assert not {"R-KB-TREATMENT", "R-PREVENT-SPREAD", "R-DX-SPRAY-CONDITIONS", "R-DX-CONFIRM"} & set(r)
        assert r["R-RESCAN"]["basis"] == "agriguard_rule"
        missing = {m["key"]: m["reason_code"] for m in c["missing"]}
        assert missing["heatmap"] == "healthy" and missing["margin"] == "older_scan"

    def test_arabic_report_is_complete(self):
        c = generate(builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev(), "ar")
        assert validate_content(c) == []
        text = json.dumps(c, ensure_ascii=False)
        assert "٪" in text and "٩٫٠" in text                                        # Arabic digits and decimal mark
        # no untranslated i18n key leaks into the report
        leaked = re.findall(r'"(?:st|rec|imp|mon|note|sec|f|u|m\.title|m\.explain|ch|stk)\.[a-z_]+(?:\.[a-z_]+)*"', text)
        assert leaked == []
        assert c["chapters"][0]["title"] == "الملخص التنفيذي"
        ref = next(x for x in c["references"] if x["id"] == "ref-gradcam")
        assert ref["claims"][0].startswith("تُنتج طريقة Grad-CAM")


# ------------------------------------------------------------------ plant progress
class TestRecoveryReport:
    def test_comparability_and_measured_changes(self):
        c = generate(builders.build_plant_progress, plant_progress_recommendations, plant_ev())
        assert validate_content(c) == []
        sec = sections(c)
        comparable = [{x["key"]: x for x in row["cells"]}["comparable"] for row in sec["scan_table"]["rows"]]
        assert [x["value"] for x in comparable] == [True, False, False, True]
        assert comparable[1]["display"] == "Measured by a different model version"
        assert comparable[2]["display"] == "Photo quality: blurry"
        change = sec["measured_changes"]["rows"][0]["cells"]
        assert [x["value"] for x in change[2:4]] == [30, -11.0] and change[4]["value"] == round(-11.0 / 30, 3)
        assert sec["measured_changes"]["facts"][0]["value"] == -11.0
        why = sec["status"]["statements"]
        assert why[0]["kind"] == "measured" and "20.0%" in why[0]["text"] and "9.0%" in why[0]["text"] and "±5.0" in why[0]["text"]
        assert any("Confidence measures certainty" in s["text"] for s in why)

    def test_treatments_are_lined_up_with_measurements_not_credited(self):
        c = generate(builders.build_plant_progress, plant_progress_recommendations, plant_ev())
        chart = next(ch for ch in c["charts"] if ch["id"] == "area_trend")
        assert chart["series"][0]["values"] == [20.0, 9.0]
        assert [m["index"] for m in chart["markers"]] == [1]                             # 5 Sep lies between the two points
        sev = next(ch for ch in c["charts"] if ch["id"] == "severity_trend")
        assert sev["series"][0]["values"] == [2, 2, 3, 1] and sev["provenance"]["kind"] == "model_estimate"
        rows = {r["id"]: {x["key"]: x for x in r["cells"]} for r in sections(c)["treatments"]["rows"]}
        assert rows["tr1"]["before"]["value"] == 20.0 and rows["tr1"]["after"]["value"] == 9.0
        assert rows["tr2"]["after"]["available"] is False
        hyp = sections(c)["hypotheses"]["hypotheses"]
        assert "5 Sep 2026" in hyp[0]["text"] and "not proof that the treatment caused it" in hyp[0]["text"]
        assert hyp[-1]["text"].startswith("Weather, plant age")

    def test_missing_follow_up_data_is_identified(self):
        c = generate(builders.build_plant_progress, plant_progress_recommendations, plant_ev())
        gaps = [i["text"] for i in sections(c)["follow_up"]["items"]]
        assert any("21 days passed between scans" in g for g in gaps)
        assert any("19 days ago" in g for g in gaps)
        assert any("No scan is dated after the treatment recorded on 5 Oct 2026" in g for g in gaps)
        assert any("1 follow-up reminder" in g for g in gaps)
        r = recs(c)
        assert {"R-PP-OVERDUE", "R-PP-FOLLOWUP-DUE", "R-PP-AFTER-TREATMENT"} <= set(r) and "R-RESCAN" not in r
        assert r["R-PP-FOLLOWUP-DUE"]["refs"] == ["ref-umn-prevention"]

    def test_follow_up_gaps_function(self):
        ev = plant_ev()
        codes = [g["code"] for g in builders.follow_up_gaps(ev["scans"], ev["treatments"], ev["reminders"], RULES, "2026-10-02")]
        assert codes == ["long_gap", "no_scan_after_treatment", "overdue_reminders"]     # last scan 1 day ago: not due


# ------------------------------------------------------------------- regional risk
class TestRegionalReport:
    def test_risk_calculation_is_explained(self):
        c = generate(builders.build_outbreak_area, outbreak_recommendations, outbreak_ev())
        assert validate_content(c) == []
        st = [s["text"] for s in sections(c)["risk"]["statements"]]
        assert any("0.62 falls between 0.50 and 0.75, so the level is High" in s for s in st)
        assert any("calibrated" in s for s in st) and any("ROC-AUC 0.81" in s and "400 rows" in s for s in st)
        assert any("observed weather in place of forecasts" in s for s in st)
        factors = sections(c)["factors"]["rows"]
        assert factors[0]["cells"][0]["display"] == "Hours ≥90% humidity, last 7 days"
        assert factors[0]["cells"][2]["display"] == "5.0 – 15.0"

    def test_observations_and_estimates_stay_apart(self):
        c = generate(builders.build_outbreak_area, outbreak_recommendations, outbreak_ev())
        f = facts(c)
        assert f["positives"]["provenance"]["kind"] == "observation" and f["risk_level"]["provenance"]["kind"] == "model"
        assert f["region_inspections"]["value"] == 35 and f["region_positives"]["value"] == 8
        why = [s["text"] for s in sections(c)["why_level"]["statements"]]
        assert any("(30%) is higher than the region's (23%)" in s for s in why)
        assert any("Of 2 neighbouring cells with estimates, 0 have a higher level and 2 a lower one" in s for s in why)
        assert any("not causes" in s for s in why)
        assert any("not any single farm" in lim for lim in c["limitations"])
        weather = sections(c)["weather"]["facts"]
        w = {x["key"]: x["value"] for x in weather}
        assert w["w.days"] == 14 and w["w.rh_mean"] == 85.0 and w["w.rain_total"] == 28.0 and w["w.rh90_days"] == 7
        assert w["w.fc_days"] == 3 and w["w.fc_rain"] == 12.0

    def test_inspection_priorities_and_coverage(self):
        c = generate(builders.build_outbreak_area, outbreak_recommendations, outbreak_ev())
        rows = sections(c)["inspection_priorities"]["rows"]
        order = [{x["key"]: x for x in r["cells"]}["cell"]["value"] for r in rows]
        assert order == ["0.25:40:80", "0.25:39:79", "0.25:41:80"]                       # cases+high, cases, uninspected neighbour
        assert "no inspections, next to a cell with cases" in rows[2]["cells"][2]["display"]
        cov = {f["key"]: f["value"] for f in sections(c)["coverage"]["facts"]}
        assert cov["count.cells"] == 4 and cov["count.no_inspections"] == 1 and cov["count.no_estimate"] == 1
        assert cov["count.hidden"] == 1 and cov["training_region"] is True
        r = recs(c)
        assert r["R-OA-INSPECT"]["priority"] == "high" and r["R-OA-INSPECT"]["horizon"] == "immediate"
        assert r["R-OA-SUITABILITY"]["refs"] == ["ref-hutton"] and r["R-OA-SCOUTING"]["refs"] == ["ref-umn-prevention"]
        assert "R-OA-COVERAGE" in r
        suit = facts(c)["suit.hutton_criteria_potato_late_blight"]
        assert suit["refs"] == ["ref-hutton"] and suit["provenance"]["kind"] == "sourced_rule"

    def test_no_estimate_means_no_level(self):
        ev = outbreak_ev()
        ev["prediction"] = None
        ev["region"]["cells"] = [{**cell, "prediction": None} for cell in ev["region"]["cells"]]
        c = generate(builders.build_outbreak_area, outbreak_recommendations, ev)
        assert validate_content(c) == [] and c["status"]["code"] == "no_current_estimate"
        assert sections(c)["risk"]["statements"][0]["kind"] == "missing"
        assert "R-OA-NO-ESTIMATE" in recs(c)


# ------------------------------------------------------------------ validation rules
class TestValidation:
    def test_unsourced_or_unlabelled_content_is_rejected(self):
        c = generate(builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev())
        bad = copy.deepcopy(c)
        bad["recommendations"][0]["basis"] = "reference"
        bad["recommendations"][0]["refs"] = []
        bad["sections"][0]["statements"] = [{"text": "x", "kind": "reference", "provenance": {"kind": "reference"}}]
        bad["sections"][1]["facts"].append({"key": "z", "label": "z", "value": 1, "display": "1", "available": True,
                                            "provenance": {"kind": "model"}, "refs": ["ref-made-up"]})
        bad["sections"][2].pop("chapter")
        bad["charts"] = [{"id": "c", "x": ["a"], "series": [{"values": [1]}], "markers": [{"index": 3}],
                          "provenance": {"kind": "model"}}]
        problems = " ".join(validate_content(bad))
        for expected in ("claims a reference but cites none", "says it is sourced but cites nothing", "unknown reference ref-made-up",
                         "has no chapter", "marker outside its axis"):
            assert expected in problems


# ---------------------------------------------------------------------------- PDF
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_v2_pdfs_render_every_chapter(locale):
    from pypdf import PdfReader

    from app.infrastructure.reporting.report_pdf import render_report_pdf

    for build, recommend, ev in ((builders.build_diagnosis, diagnosis_recommendations, diagnosis_ev()),
                                 (builders.build_plant_progress, plant_progress_recommendations, plant_ev()),
                                 (builders.build_outbreak_area, outbreak_recommendations, outbreak_ev())):
        content = generate(build, recommend, ev, locale)
        content["narrative"] = {"source": "template", "executive_summary": [{"text": "Synthetic summary.", "fact_ids": ["F1"]}]}
        report = {"content": content, "locale": locale, "reference": "AGR-TEST-v1", "version": 1, "generated_display": "1 Nov 2026",
                  "synthetic": True, "sources": [{"kind": "test", "table": "synthetic", "id": "1"}], "data_hash": "0" * 64,
                  "generator_version": "reports-v2", "schema_version": SCHEMA_VERSION}
        data = render_report_pdf(report, lambda key: None)
        assert data.startswith(b"%PDF")
        pages = PdfReader(io.BytesIO(data)).pages
        text = "".join(p.extract_text() or "" for p in pages)
        if locale == "en":
            for ch in content["chapters"]:
                assert ch["title"] in text, ch["title"]
            assert "Cited for" in text and content["references"][0]["url"][:30] in text
        else:
            assert len(pages) >= 2 and "https://" in text
