"""
LabelNormalizer — maps arbitrary raw dataset labels onto AgriGuard AI's canonical
schema: "{plant}___{condition}" (FR-DATA-2).

Different datasets format labels differently:
  - PlantVillage:              "Tomato___Early_blight", "Tomato___healthy"
  - PlantDoc:                  "Tomato leaf", "Apple Scab Leaf", "Corn Gray leaf spot"
  - New Plant Diseases (Kaggle): same convention as PlantVillage (it is derived from it)
  - IP102 (pest names):         "rice_leaf_roller", "red palm weevil"
  - Date Palm datasets:         "Bayoud", "black_scorch", "healthy_palm"

The normalizer therefore does NOT assume a single delimiter convention. It:
  1. Lowercases and strips the raw label.
  2. If the "___" canonical delimiter is already present, splits on it directly.
  3. Otherwise, scans the label for a known plant name/synonym anywhere in the string.
  4. Removes the matched plant tokens and generic noise words ("leaf", "disease") from
     the remainder to derive the condition.
  5. Normalizes the condition string (spaces -> underscores, known condition synonyms
     collapsed to one canonical spelling, e.g. "early_blight" for "earlyblight").
  6. If no known plant is found, the plant is recorded as "unknown" and the full raw
     label (normalized) becomes the condition — these are surfaced in the audit report
     for manual review rather than silently mis-merged into an unrelated class.

This is a best-effort heuristic layer, not a guarantee of perfect taxonomy alignment;
its output is deterministic and logged so misclassified labels can be corrected by
extending PLANT_SYNONYMS / CONDITION_SYNONYMS rather than by editing pipeline logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

# Canonical plant name -> list of synonym tokens that may appear in raw labels.
PLANT_SYNONYMS: Dict[str, List[str]] = {
    "tomato": ["tomato"],
    "potato": ["potato"],
    "corn": ["corn", "maize"],
    "wheat": ["wheat"],
    "rice": ["rice"],
    "cucumber": ["cucumber"],
    "pepper": ["pepper", "bell_pepper", "bell pepper", "capsicum"],
    "lettuce": ["lettuce"],
    "mint": ["mint"],
    "parsley": ["parsley"],
    "coriander": ["coriander", "cilantro"],
    "grape": ["grape"],
    "apple": ["apple"],
    "olive": ["olive"],
    "orange": ["orange"],
    "lemon": ["lemon"],
    "date_palm": ["date_palm", "date palm", "palm", "phoenix_dactylifera"],
}

# Raw condition token/phrase -> canonical condition spelling.
CONDITION_SYNONYMS: Dict[str, str] = {
    "healthy": "healthy",
    "health": "healthy",
    "early_blight": "early_blight",
    "earlyblight": "early_blight",
    "late_blight": "late_blight",
    "lateblight": "late_blight",
    "leaf_mold": "leaf_mold",
    "leafmold": "leaf_mold",
    "powdery_mildew": "powdery_mildew",
    "powderymildew": "powdery_mildew",
    "downy_mildew": "downy_mildew",
    "downymildew": "downy_mildew",
    "rust": "rust",
    "anthracnose": "anthracnose",
    "leaf_curl": "leaf_curl",
    "leafcurl": "leaf_curl",
    "curl_virus": "leaf_curl",
    "leaf_spot": "leaf_spot",
    "leafspot": "leaf_spot",
    "gray_leaf_spot": "gray_leaf_spot",
    "graphiola_leaf_spot": "graphiola_leaf_spot",
    "bacterial_spot": "bacterial_spot",
    "bacterialspot": "bacterial_spot",
    "fusarium_wilt": "fusarium_wilt",
    "fusariumwilt": "fusarium_wilt",
    "root_rot": "root_rot",
    "rootrot": "root_rot",
    "scab": "scab",
    "black_scorch": "black_scorch",
    "blackscorch": "black_scorch",
    "bayoud": "bayoud_disease",
    "bayoud_disease": "bayoud_disease",
    "leaf_blight": "leaf_blight",
    "leafblight": "leaf_blight",
    "red_palm_weevil": "red_palm_weevil",
    "redpalmweevil": "red_palm_weevil",
    "weevil": "red_palm_weevil",
    "mosaic_virus": "mosaic_virus",
    "yellow_leaf_curl_virus": "yellow_leaf_curl_virus",
    "septoria_leaf_spot": "septoria_leaf_spot",
    "target_spot": "target_spot",
    "black_rot": "black_rot",
    "cedar_apple_rust": "cedar_apple_rust",
    "haunglongbing": "citrus_greening",
    "citrus_greening": "citrus_greening",
    "esca": "esca_black_measles",
    "black_measles": "esca_black_measles",
    "spider_mites": "spider_mites",
    "two_spotted_spider_mite": "spider_mites",
}

_NOISE_WORDS = {"leaf", "leaves", "disease", "plant", "the", "a", "an", "of", "on"}


@dataclass(frozen=True)
class CanonicalLabel:
    plant: str
    condition: str

    @property
    def canonical(self) -> str:
        return f"{self.plant}___{self.condition}"


def _tokenize(text: str) -> List[str]:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return [t for t in text.split("_") if t]


class LabelNormalizer:
    def __init__(self):
        self._unmatched_plants: List[str] = []

    def normalize(self, raw_label: str) -> CanonicalLabel:
        raw = raw_label.strip()

        # Case 1: already in canonical "plant___condition" form (PlantVillage-derived sets).
        if "___" in raw:
            plant_part, condition_part = raw.split("___", 1)
            plant = self._match_plant(plant_part) or self._slugify(plant_part)
            condition = self._match_condition(condition_part) or self._slugify(condition_part)
            return CanonicalLabel(plant=plant, condition=condition)

        tokens = _tokenize(raw)
        joined = "_".join(tokens)

        plant = self._match_plant(joined)
        if plant is None:
            self._unmatched_plants.append(raw_label)
            return CanonicalLabel(plant="unknown", condition=self._slugify(raw))

        # Remove plant tokens + noise words from the token stream to isolate condition.
        plant_tokens = set()
        for syn in PLANT_SYNONYMS[plant]:
            plant_tokens.update(_tokenize(syn))
        remainder_tokens = [t for t in tokens if t not in plant_tokens and t not in _NOISE_WORDS]

        if not remainder_tokens:
            condition = "healthy" if "healthy" in tokens or "health" in tokens else "unspecified"
        else:
            condition = self._match_condition("_".join(remainder_tokens)) or "_".join(remainder_tokens)

        return CanonicalLabel(plant=plant, condition=condition)

    # ------------------------------------------------------------------
    def _match_plant(self, text: str) -> str | None:
        norm = "_".join(_tokenize(text))
        for plant, synonyms in PLANT_SYNONYMS.items():
            for syn in synonyms:
                syn_norm = "_".join(_tokenize(syn))
                if syn_norm and syn_norm in norm:
                    return plant
        return None

    def _match_condition(self, text: str) -> str | None:
        norm = "_".join(_tokenize(text))
        if norm in CONDITION_SYNONYMS:
            return CONDITION_SYNONYMS[norm]
        for key, canonical in CONDITION_SYNONYMS.items():
            if key in norm:
                return canonical
        return None

    def _slugify(self, text: str) -> str:
        return "_".join(_tokenize(text)) or "unspecified"

    @property
    def unmatched_plant_labels(self) -> List[str]:
        """Raw labels that could not be matched to a known plant — surfaced for the
        pre-flight audit report so a human can extend PLANT_SYNONYMS if needed."""
        return list(self._unmatched_plants)
