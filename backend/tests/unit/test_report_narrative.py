"""The LLM may only word a report summary from the report's own facts. Every kind of
unsupported statement must be rejected (and the template summary used instead)."""
from __future__ import annotations

import json

import pytest

from app.application.reporting.content import fact, provenance, unavailable, validate_content
from app.application.reporting.narrative import build_narrative, facts_packet

CONTENT = {
    "type": "diagnosis",
    "status": {"code": "disease_predicted"},
    "key_facts": [
        fact("condition", "Predicted condition", "early_blight", "Early blight", provenance("model", "clf@1")),
        fact("confidence", "Model confidence", 91.5, "91.5%", provenance("model", "clf@1"), unit="%"),
        fact("plant", "Plant", "tomato", "Tomato", provenance("model", "clf@1")),
        unavailable("area_measured", "Affected area (measured)", "No segmentation model.", "no_segmentation_model"),
    ],
    "sections": [],
    "recommendations": [{"id": "rec-1", "title": "Scan again", "reason": "r", "evidence": [{"key": "condition"}]}],
}
KNOWN = ["early_blight", "late_blight", "Late blight", "powdery mildew"]


def _gen(summary, notes=None):
    payload = {"executive_summary": summary, "recommendation_notes": notes or []}

    def generate(prompt):
        assert "FACTS:" in prompt and "Early blight" in prompt  # the model only sees the report's facts
        return json.dumps(payload)
    generate.model_name = "fake-llm"
    return generate


def _ids():
    return {f["key"]: f["id"] for f in facts_packet(CONTENT)}


def test_valid_grounded_summary_is_used():
    ids = _ids()
    out = build_narrative(CONTENT, "en", KNOWN, _gen([
        {"text": "The model predicts Early blight with 91.5% confidence; this is not confirmed.",
         "fact_ids": [ids["condition"], ids["confidence"]]},
        {"text": "The affected area could not be measured.", "fact_ids": [ids["area_measured"]]}]))
    assert out["source"] == "llm" and out["model"] == "fake-llm" and out["validation"]["passed"]


@pytest.mark.parametrize("text,why", [
    ("The model predicts Early blight with 97% confidence.", "number"),
    ("Spray 2 ml per litre of water.", "dose"),
    ("Early blight is confirmed on this plant.", "certain"),
    ("See https://example.org for details.", "reference"),
    ("Early blight (Smith et al., 2019) spreads fast.", "reference"),
    ("It may also be late blight.", "disease"),
])
def test_unsupported_statements_fall_back_to_template(text, why):
    ids = _ids()
    out = build_narrative(CONTENT, "en", KNOWN, _gen([{"text": text, "fact_ids": [ids["condition"], ids["confidence"]]}]))
    assert out["source"] == "template" and not out["validation"]["passed"]
    assert out["validation"]["errors"] and out["executive_summary"]  # the template summary is still there


def test_uncited_or_unknown_ids_and_bad_json_are_rejected():
    for summary in ([{"text": "Early blight predicted.", "fact_ids": []}],
                    [{"text": "Early blight predicted.", "fact_ids": ["F99"]}]):
        assert build_narrative(CONTENT, "en", KNOWN, _gen(summary))["source"] == "template"

    def broken(prompt):
        return "not json"
    assert build_narrative(CONTENT, "en", KNOWN, broken)["validation"]["errors"][0].startswith("invalid LLM output")

    def offline(prompt):
        raise ConnectionError("no network")
    assert build_narrative(CONTENT, "en", KNOWN, offline)["validation"]["errors"][0].startswith("LLM unavailable")


def test_arabic_numbers_are_checked_too():
    ids = _ids()
    good = build_narrative(CONTENT, "ar", KNOWN, _gen([{"text": "ثقة النموذج ٩١٫٥٪.", "fact_ids": [ids["confidence"]]}]))
    bad = build_narrative(CONTENT, "ar", KNOWN, _gen([{"text": "ثقة النموذج ٩٩٪.", "fact_ids": [ids["confidence"]]}]))
    assert good["source"] == "llm" and bad["source"] == "template"


def test_negated_certainty_words_are_allowed():
    from app.application.reporting.narrative import _asserts_certainty

    for ok in ("This is not confirmed.", "an unconfirmed prediction", "It is never certain.", "هذا غير مؤكد."):
        assert not _asserts_certainty(ok), ok
    for bad in ("This is confirmed.", "It is definitely early blight.", "المرض مؤكد."):
        assert _asserts_certainty(bad), bad


def test_template_without_llm_cites_facts():
    out = build_narrative(CONTENT, "en", KNOWN, None)
    assert out["source"] == "template" and all(s["fact_ids"] for s in out["executive_summary"])


def test_content_validation_rejects_unsourced_values():
    content = {"key_facts": [{"key": "x", "label": "x", "value": 3.0, "display": "3", "available": True, "provenance": {}}],
               "sections": [], "charts": [{"id": "c", "x": [1, 2], "series": [{"values": [1]}], "provenance": {"kind": "model"}}],
               "recommendations": [{"id": "r", "provenance": {"kind": "rule"}, "reason": ""}]}
    problems = validate_content(content)
    assert any("no valid provenance" in p for p in problems)
    assert any("different lengths" in p for p in problems)
    assert any("no reason" in p for p in problems)
