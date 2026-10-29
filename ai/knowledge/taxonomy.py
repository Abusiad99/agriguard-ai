"""
Curated metadata for the classes the disease classifier can output.

For every class label produced by the label normalizer on PlantWild v2
("plant___condition") this records:
  cause_type  — fungal | oomycete | bacterial | viral | physiological
  parts       — plant parts on which symptoms typically show in photos
  patterns    — coarse symptom-pattern tags used to suggest look-alike causes
  regulated   — True when the pathogen is subject to quarantine / mandatory
                reporting in many jurisdictions (local rules differ)

PROVENANCE AND LIMITS: these are general plant-pathology classifications compiled
for this project (AgriGuard curated taxonomy, version below). They have NOT been
reviewed by an external plant pathologist. They are used only to (a) group model
candidates by cause type and (b) suggest which non-disease look-alikes and follow-up
questions are relevant — never to change model probabilities or to assert a cause.
Classes not listed here get cause_type "unknown" and no pattern-based suggestions.
"""
from __future__ import annotations

from typing import Dict, List

TAXONOMY_VERSION = "1.0.0-unreviewed"

# Pattern tags
SPOT, BLIGHT, MILDEW, RUST, MOSAIC, WILT, ROT, CURL, SCORCH, SMUT, CANKER, STREAK, MOLD = (
    "leaf_spots", "blight", "powdery_or_downy_coating", "rust_pustules", "mosaic_mottle_yellowing",
    "wilting", "rot", "curling_distortion", "scorch_marginal_browning", "smut_galls", "canker_lesions",
    "streaks", "mold_growth",
)

_T: Dict[str, dict] = {}


def _add(labels: List[str], cause: str, parts: List[str], patterns: List[str], regulated: bool = False) -> None:
    for lbl in labels:
        _T[lbl] = {"cause_type": cause, "parts": parts, "patterns": patterns, "regulated": regulated}


# --- Fungal ---------------------------------------------------------------
_add(["apple___black_rot", "grape___black_rot", "coffee___black_rot"], "fungal", ["leaf", "fruit"], [SPOT, ROT])
_add(["apple___rust", "bean___rust", "corn___rust", "garlic___rust", "peach___rust", "plum___rust",
      "soybean___rust", "blueberry___rust", "coffee___leaf_rust", "raspberry___yellow_rust",
      "wheat___leaf_rust", "wheat___stem_rust", "wheat___stripe_rust"], "fungal", ["leaf"], [RUST])
_add(["apple___scab", "peach___scab"], "fungal", ["leaf", "fruit"], [SPOT])
_add(["banana___anthracnose", "blueberry___anthracnose", "celery___anthracnose", "peach___anthracnose",
      "strawberry___anthracnose"], "fungal", ["leaf", "fruit"], [SPOT, ROT])
_add(["banana___black_leaf_streak"], "fungal", ["leaf"], [STREAK, SPOT])
_add(["banana___cigar_end_rot"], "fungal", ["fruit"], [ROT])
_add(["banana___cordana_leaf_spot", "cherry___leaf_spot", "ginger___leaf_spot", "grape___leaf_spot",
      "raspberry___leaf_spot", "soybean___brown_spot", "tobacco___brown_spot", "tobacco___frogeye_leaf_spot",
      "soybean___frog_eye_leaf_spot", "pepper___frogeye_leaf_spot", "eggplant___cercospora_leaf_spot",
      "broccoli___alternaria_leaf_spot", "cabbage___alternaria_leaf_spot", "cauliflower___alternaria_leaf_spot",
      "broccoli___ring_spot", "corn___gray_leaf_spot", "tomato___septoria_leaf_spot", "coffee___brown_eye_spot",
      "maple___tar_spot"], "fungal", ["leaf"], [SPOT])
_add(["banana___panama"], "fungal", ["leaf", "stem", "whole_plant"], [WILT, MOSAIC], regulated=True)
_add(["blueberry___botrytis_blight", "raspberry___gray_mold"], "fungal", ["fruit", "leaf", "stem"], [BLIGHT, MOLD, ROT])
_add(["blueberry___mummy_berry"], "fungal", ["fruit", "leaf"], [ROT, BLIGHT])
_add(["blueberry___scorch"], "viral", ["leaf", "stem"], [SCORCH, BLIGHT])
_add(["carrot___alternaria_leaf_blight", "carrot___cercospora_leaf_blight", "celery___early_blight",
      "corn___northern_leaf_blight", "garlic___leaf_blight", "potato___early_blight", "tomato___early_blight",
      "rice___blast"], "fungal", ["leaf"], [SPOT, BLIGHT])
_add(["rice___sheath_blight", "ginger___sheath_blight"], "fungal", ["stem", "leaf"], [BLIGHT, SPOT])
_add(["cherry___powdery_mildew", "cucumber___powdery_mildew", "pepper___powdery_mildew",
      "squash___powdery_mildew", "wheat___powdery_mildew", "zucchini___powdery_mildew"],
     "fungal", ["leaf"], [MILDEW])
_add(["coffee___berry_blotch"], "fungal", ["fruit"], [SPOT, ROT])
_add(["corn___smut", "wheat___loose_smut"], "fungal", ["fruit", "head", "stem"], [SMUT])
_add(["eggplant___phomopsis_fruit_rot"], "fungal", ["fruit", "leaf"], [ROT, SPOT])
_add(["peach___brown_rot", "plum___brown_rot"], "fungal", ["fruit", "stem"], [ROT, MOLD])
_add(["peach___leaf_curl", "plum___pocket"], "fungal", ["leaf", "fruit"], [CURL])
_add(["strawberry___leaf_scorch"], "fungal", ["leaf"], [SPOT, SCORCH])
_add(["tomato___leaf_mold"], "fungal", ["leaf"], [MOLD, MOSAIC])
_add(["wheat___head_scab"], "fungal", ["head"], [BLIGHT])
_add(["wheat___septoria_blotch"], "fungal", ["leaf"], [SPOT, BLIGHT])
_add(["carrot___cavity_spot"], "oomycete", ["root"], [SPOT, ROT])

# --- Oomycetes (water moulds) -----------------------------------------------
_add(["basil___downy_mildew", "broccoli___downy_mildew", "cabbage___downy_mildew", "grape___downy_mildew",
      "lettuce___downy_mildew", "soybean___downy_mildew", "zucchini___downy_mildew"],
     "oomycete", ["leaf"], [MILDEW, MOSAIC])
_add(["potato___late_blight", "tomato___late_blight", "eggplant___phytophthora_blight"],
     "oomycete", ["leaf", "stem", "fruit"], [BLIGHT, ROT])
_add(["tobacco___blue_mold"], "oomycete", ["leaf"], [MILDEW, SPOT])

# --- Bacterial ---------------------------------------------------------------
_add(["pepper___bacterial_spot", "tomato___bacterial_spot", "plum___bacterial_spot", "bean___halo_blight",
      "soybean___bacterial_blight", "cucumber___angular_leaf_spot"], "bacterial", ["leaf", "fruit"], [SPOT, BLIGHT])
_add(["cabbage___black_rot"], "bacterial", ["leaf"], [SCORCH, BLIGHT])
_add(["cauliflower___bacterial_soft_rot"], "bacterial", ["head", "stem"], [ROT])
_add(["cucumber___bacterial_wilt", "zucchini___bacterial_wilt"], "bacterial", ["whole_plant", "leaf"], [WILT])
_add(["raspberry___fire_blight"], "bacterial", ["stem", "leaf", "fruit"], [BLIGHT])
_add(["wheat___bacterial_leaf_streak_black_chaff"], "bacterial", ["leaf", "head"], [STREAK])
_add(["citrus___canker"], "bacterial", ["leaf", "fruit", "stem"], [CANKER, SPOT], regulated=True)
_add(["citrus___citrus_greening"], "bacterial", ["leaf", "fruit", "whole_plant"], [MOSAIC], regulated=True)

# --- Viral -------------------------------------------------------------------
_add(["apple___mosaic_virus", "bean___mosaic_virus", "lettuce___mosaic_virus", "soybean___mosaic",
      "tobacco___mosaic_virus", "tomato___mosaic_virus", "zucchini___yellow_mosaic_virus"],
     "viral", ["leaf"], [MOSAIC, CURL])
_add(["tomato___yellow_leaf_curl_virus"], "viral", ["leaf", "whole_plant"], [CURL, MOSAIC])
_add(["grape___leafroll"], "viral", ["leaf"], [CURL, MOSAIC])
_add(["plum___pox_virus"], "viral", ["leaf", "fruit"], [MOSAIC, SPOT], regulated=True)
_add(["banana___bunchy_top"], "viral", ["leaf", "whole_plant"], [MOSAIC, CURL, STREAK], regulated=True)

# --- Physiological (non-infectious) ------------------------------------------
_add(["pepper___blossom_end_rot"], "physiological", ["fruit"], [ROT])

TAXONOMY: Dict[str, dict] = dict(_T)

# Look-alike causes the image classifier CANNOT recognize (no training data), keyed by
# symptom pattern. Shown as "also consider", never as predictions.
LOOKALIKES: Dict[str, List[str]] = {
    SPOT: ["insect_or_mite_damage", "spray_or_chemical_injury", "sunscald_or_heat_injury"],
    BLIGHT: ["water_stress", "heat_or_cold_injury", "spray_or_chemical_injury"],
    MILDEW: ["dust_or_spray_residue", "honeydew_and_sooty_mould"],
    RUST: ["insect_or_mite_damage", "nutrient_deficiency"],
    MOSAIC: ["nutrient_deficiency", "herbicide_injury", "insect_or_mite_damage"],
    WILT: ["water_stress", "root_damage", "heat_or_cold_injury"],
    ROT: ["physical_damage", "sunscald_or_heat_injury", "nutrient_disorder"],
    CURL: ["insect_or_mite_damage", "herbicide_injury", "heat_or_cold_injury"],
    SCORCH: ["water_stress", "salt_or_fertilizer_burn", "heat_or_cold_injury"],
    SMUT: [],
    CANKER: ["physical_damage", "insect_or_mite_damage"],
    STREAK: ["nutrient_deficiency", "herbicide_injury"],
    MOLD: ["honeydew_and_sooty_mould"],
}

ALL_NON_MODEL_CATEGORIES = [
    "insect_or_mite_damage", "nutrient_deficiency", "nutrient_disorder", "water_stress",
    "heat_or_cold_injury", "herbicide_injury", "spray_or_chemical_injury", "sunscald_or_heat_injury",
    "salt_or_fertilizer_burn", "root_damage", "physical_damage", "dust_or_spray_residue",
    "honeydew_and_sooty_mould", "healthy_or_normal_variation",
]


def describe(label: str) -> dict:
    entry = TAXONOMY.get(label)
    if entry is None:
        return {"cause_type": "unknown", "parts": [], "patterns": [], "regulated": False, "in_taxonomy": False}
    return {**entry, "in_taxonomy": True}
