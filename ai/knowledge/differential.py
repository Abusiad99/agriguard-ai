"""
Differential diagnosis: turn the classifier's calibrated top-k into a cautious,
explained shortlist, and add the causes the model CANNOT recognize.

What is automated vs. not
-------------------------
* Model candidates — only classes the classifier was trained on (PlantWild v2 disease
  classes). Probabilities are the calibrated model outputs, unchanged.
* "Also consider" categories — pests, nutrient problems, water/heat stress, chemical
  injury, healthy variation. The model has NO training data for these, so they are
  never given a probability or ranked against model classes; they are suggested from
  the leading candidates' symptom patterns (ai/knowledge/taxonomy.py).
* Follow-up questions — short, structured questions whose answers produce
  rule-of-thumb hints ("consistent with…", "also check…"). Answers are user-provided
  context; they never modify model probabilities and are never treated as proof.

Expert review is recommended whenever the decision is not "confident", when the
leading candidates point to different cause types, or when a candidate is a
pathogen that is regulated in many regions.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ai.knowledge.taxonomy import (
    ALL_NON_MODEL_CATEGORIES,
    BLIGHT,
    CURL,
    LOOKALIKES,
    MILDEW,
    MOSAIC,
    ROT,
    SCORCH,
    SPOT,
    TAXONOMY_VERSION,
    WILT,
    describe,
)

DIFFERENTIAL_VERSION = "1.1.0"

# Only candidates with at least this calibrated probability (percent) count when
# deciding whether to recommend expert review. A 3 % runner-up of another cause type
# should not turn a 94 % result into a "candidates disagree" warning. Regulated
# pathogens use a lower floor because missing one is costly.
PLAUSIBLE_CANDIDATE_MIN_PCT = 10.0
REGULATED_CANDIDATE_MIN_PCT = 5.0

FOLLOW_UP_QUESTIONS: List[dict] = [
    {"id": "affected_parts", "type": "multi",
     "options": ["leaves", "stems", "fruit", "roots_or_base", "whole_plant"]},
    {"id": "distribution", "type": "single",
     "options": ["few_scattered_spots", "older_lower_leaves_first", "new_growth_first", "whole_plant_evenly",
                 "one_side_or_patch"]},
    {"id": "duration", "type": "single", "options": ["under_3_days", "one_to_two_weeks", "over_two_weeks"]},
    {"id": "pests_seen", "type": "single", "options": ["yes", "no", "not_checked"]},
    {"id": "recent_watering", "type": "single",
     "options": ["normal", "soil_very_dry", "soil_waterlogged", "recently_changed"]},
    {"id": "recent_weather", "type": "single",
     "options": ["normal", "wet_or_humid", "very_hot", "frost_or_cold"]},
    {"id": "spreading_to_neighbors", "type": "single", "options": ["yes", "no", "unknown"]},
    {"id": "recent_chemicals", "type": "single", "options": ["yes", "no", "unknown"]},
]
_QUESTION_INDEX = {q["id"]: q for q in FOLLOW_UP_QUESTIONS}


def validate_answers(answers: Dict[str, object]) -> Dict[str, object]:
    """Keep only known question ids and allowed option values (drops anything else)."""
    clean: Dict[str, object] = {}
    for qid, value in (answers or {}).items():
        q = _QUESTION_INDEX.get(qid)
        if q is None:
            continue
        if q["type"] == "multi":
            vals = value if isinstance(value, list) else [value]
            vals = [v for v in vals if isinstance(v, str) and v in q["options"]]
            if vals:
                clean[qid] = sorted(set(vals))
        elif isinstance(value, str) and value in q["options"]:
            clean[qid] = value
    return clean


def _relevant_questions(patterns: set) -> List[str]:
    ids = ["affected_parts", "distribution", "pests_seen", "spreading_to_neighbors"]
    if patterns & {WILT, SCORCH, BLIGHT}:
        ids += ["recent_watering", "recent_weather"]
    if patterns & {MOSAIC, CURL, SPOT, SCORCH}:
        ids.append("recent_chemicals")
    ids.append("duration")
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def build_differential(candidates: List[dict], decision_status: Optional[str],
                       answers: Optional[Dict[str, object]] = None) -> dict:
    """`candidates`: calibrated top-k from InferenceService
    ([{"canonical", "plant", "condition", "confidence"}, ...])."""
    answers = validate_answers(answers or {})
    model_candidates = []
    patterns: set = set()
    cause_types = set()
    plausible_cause_types: set = set()
    regulated = []
    for c in candidates:
        meta = describe(c.get("canonical", ""))
        model_candidates.append({
            "label": c.get("canonical"),
            "plant": c.get("plant"),
            "condition": c.get("condition"),
            "probability_pct": c.get("confidence"),
            "cause_type": meta["cause_type"],
            "typical_parts": meta["parts"],
            "symptom_patterns": meta["patterns"],
            "regulated_in_many_regions": meta["regulated"],
        })
        patterns.update(meta["patterns"])
        cause_types.add(meta["cause_type"])
        prob = float(c.get("confidence") or 0.0)
        if prob >= PLAUSIBLE_CANDIDATE_MIN_PCT:
            plausible_cause_types.add(meta["cause_type"])
        if meta["regulated"] and prob >= REGULATED_CANDIDATE_MIN_PCT:
            regulated.append(c.get("canonical"))

    if decision_status == "inconclusive":
        # The candidates are withheld for an inconclusive result, so nothing derived
        # from them (look-alikes, question selection, cause-based hints) is shown
        # either: that would reveal the hidden guess indirectly.
        patterns, cause_types = set(), set()
        model_candidates_for_ui: List[dict] = []
        questions = [q["id"] for q in FOLLOW_UP_QUESTIONS]
    else:
        model_candidates_for_ui = model_candidates
        questions = _relevant_questions(patterns)

    leading_patterns = set(model_candidates_for_ui[0]["symptom_patterns"]) if model_candidates_for_ui else set()
    also_consider: List[str] = []
    for p in sorted(leading_patterns or patterns):
        for cat in LOOKALIKES.get(p, []):
            if cat not in also_consider:
                also_consider.append(cat)

    reasons = []
    if decision_status != "confident":
        reasons.append("model_not_confident")
    if len(plausible_cause_types - {"unknown"}) > 1:
        reasons.append("candidates_differ_in_cause_type")
    if regulated:
        reasons.append("possible_regulated_pathogen")

    return {
        "version": DIFFERENTIAL_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "decision_status": decision_status,
        "model_candidates": model_candidates_for_ui,
        "also_consider": also_consider,
        "not_assessable_by_model": ALL_NON_MODEL_CATEGORIES,
        "follow_up_questions": questions,
        "answers": answers,
        "hints": derive_hints(answers, patterns, cause_types),
        "expert_review_recommended": bool(reasons),
        "expert_review_reasons": reasons,
        "regulated_candidates": regulated,
    }


def derive_hints(answers: Dict[str, object], patterns: set, cause_types: set) -> List[dict]:
    """Rule-of-thumb hints from user answers. Each hint has a stable `code` the UI
    localizes. These are prompts for what to check — not conclusions."""
    hints: List[dict] = []

    def add(code: str, kind: str):
        hints.append({"code": code, "kind": kind})

    if answers.get("pests_seen") == "yes":
        add("pests_seen_check_pest_damage", "also_check")
    if answers.get("recent_watering") in ("soil_very_dry", "soil_waterlogged") and patterns & {WILT, SCORCH, BLIGHT}:
        add("watering_problem_can_mimic_symptoms", "also_check")
    if answers.get("recent_chemicals") == "yes" and patterns & {SPOT, MOSAIC, CURL, SCORCH}:
        add("chemical_injury_possible", "also_check")
    if answers.get("distribution") == "new_growth_first" and MOSAIC in patterns:
        add("new_growth_yellowing_consider_micronutrients", "also_check")
    if answers.get("distribution") == "older_lower_leaves_first" and MOSAIC in patterns:
        add("older_leaf_yellowing_consider_mobile_nutrients", "also_check")
    if answers.get("distribution") == "whole_plant_evenly" and answers.get("duration") == "under_3_days":
        add("sudden_uniform_symptoms_suggest_environmental_or_chemical_cause", "also_check")
    if answers.get("recent_weather") == "wet_or_humid" and cause_types & {"fungal", "oomycete", "bacterial"}:
        add("wet_weather_consistent_with_foliar_disease", "consistent")
    if answers.get("recent_weather") in ("very_hot", "frost_or_cold") and patterns & {SCORCH, BLIGHT, WILT, CURL}:
        add("temperature_extreme_can_mimic_symptoms", "also_check")
    if answers.get("spreading_to_neighbors") == "yes":
        add("spread_between_plants_more_typical_of_infectious_cause", "consistent")
    elif answers.get("spreading_to_neighbors") == "no" and answers.get("duration") == "over_two_weeks":
        add("no_spread_over_time_consider_non_infectious_cause", "also_check")
    parts = answers.get("affected_parts") or []
    if "roots_or_base" in parts or "whole_plant" in parts:
        add("whole_plant_or_root_symptoms_need_field_inspection", "also_check")
    if "fruit" in parts and ROT in patterns:
        add("fruit_rot_check_physical_damage_and_calcium_disorder", "also_check")
    if MILDEW in patterns and answers.get("pests_seen") == "yes":
        add("coating_may_be_honeydew_or_sooty_mould", "also_check")
    return hints
