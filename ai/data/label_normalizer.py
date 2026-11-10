"""
LabelNormalizer — maps arbitrary raw dataset labels onto AgriGuard AI's canonical
schema: "{plant}___{condition}" (FR-DATA-2).

Different datasets format labels differently:
  - PlantWild v2 (bundled):    "apple black rot", "bell pepper bacterial spot"
  - PlantVillage:              "Tomato___Early_blight", "Tomato___healthy"
  - PlantDoc:                  "Tomato leaf", "Apple Scab Leaf", "Corn Gray leaf spot"
  - New Plant Diseases (Kaggle): same convention as PlantVillage (it is derived from it)
  - IP102 (pest names):         "rice_leaf_roller", "red palm weevil"
  - Date Palm datasets:         "Bayoud", "black_scorch", "healthy_palm"

The normalizer therefore does NOT assume a single delimiter convention. It:
  1. Lowercases the raw label and splits it into word tokens. A parenthetical part
     ("Esca_(Black_Measles)", "bacterial leaf streak (black chaff)") is treated as an
     alias: it can select a known condition but never becomes part of the class name.
  2. If the "___" canonical delimiter is already present, splits on it directly
     (dropping a repeated plant name from the condition, as in
     "Tomato___Tomato_mosaic_virus").
  3. Otherwise, finds the earliest known plant name/synonym in the label, matching
     whole words only ("bean" never matches inside "soybean").
  4. Takes the remaining words as the condition and maps it to a canonical spelling
     only by EXACT lookup in CONDITION_SYNONYMS — first as written, then without
     generic filler words ("leaf", "disease"), then via the parenthetical alias.
  5. If no synonym matches, keeps the condition words as written (minus filler at
     the edges, e.g. PlantDoc's trailing "Leaf"). Distinct diseases therefore always
     stay distinct classes: "wheat stem rust" and "wheat stripe rust" are never
     merged into a generic "rust", and "leaf" inside a name ("gray leaf spot") is kept.
  6. If no known plant is found, the plant is recorded as "unknown" and the full raw
     label (normalized) becomes the condition — these are surfaced in the audit report
     for manual review rather than silently mis-merged into an unrelated class.

Classes from different datasets merge only through an explicit CONDITION_SYNONYMS
entry. The output is deterministic and logged, so a label that should merge with
another can be fixed by extending PLANT_SYNONYMS / CONDITION_SYNONYMS rather than by
editing pipeline logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Canonical plant name -> list of synonyms (one or more words) that may appear in raw labels.
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
    "grape": ["grape", "grapevine"],
    "apple": ["apple"],
    "olive": ["olive"],
    "orange": ["orange"],
    "lemon": ["lemon"],
    "date_palm": ["date_palm", "date palm", "palm", "phoenix_dactylifera"],
    "banana": ["banana"],
    "basil": ["basil"],
    "bean": ["bean"],
    "blueberry": ["blueberry"],
    "broccoli": ["broccoli"],
    "cabbage": ["cabbage"],
    "carrot": ["carrot"],
    "cauliflower": ["cauliflower"],
    "celery": ["celery"],
    "cherry": ["cherry"],
    "citrus": ["citrus"],
    "coffee": ["coffee"],
    "eggplant": ["eggplant", "aubergine", "brinjal"],
    "garlic": ["garlic"],
    "ginger": ["ginger"],
    "maple": ["maple"],
    "peach": ["peach"],
    "plum": ["plum"],
    "raspberry": ["raspberry"],
    "soybean": ["soybean", "soyabean"],
    "squash": ["squash"],
    "strawberry": ["strawberry"],
    "tobacco": ["tobacco"],
    "zucchini": ["zucchini", "courgette"],
}

# Canonical condition for a plant with no disease. Inference and the backend
# (app/domain/entities/diagnosis.py) both key on this exact string.
HEALTHY_CONDITION = "healthy"

# Raw condition phrase -> canonical condition spelling. Matched exactly (whole
# phrase), never as a substring, so a generic entry like "rust" can't absorb
# "stem_rust" or "stripe_rust".
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
    "leaf_rust": "leaf_rust",
    "anthracnose": "anthracnose",
    "leaf_curl": "leaf_curl",
    "leafcurl": "leaf_curl",
    "curl_virus": "leaf_curl",
    "leaf_spot": "leaf_spot",
    "leafspot": "leaf_spot",
    "gray_leaf_spot": "gray_leaf_spot",
    "cercospora_leaf_spot_gray_leaf_spot": "gray_leaf_spot",  # PlantVillage corn folder
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
    "greening": "citrus_greening",
    "greening_disease": "citrus_greening",
    "esca": "esca_black_measles",
    "black_measles": "esca_black_measles",
    "spider_mites": "spider_mites",
    "two_spotted_spider_mite": "spider_mites",
    "spider_mites_two_spotted_spider_mite": "spider_mites",  # PlantVillage tomato folder
}

# Generic words that may be dropped when looking a condition up in CONDITION_SYNONYMS.
_NOISE_WORDS = {"leaf", "leaves", "disease", "plant", "the", "a", "an", "of", "on"}
# Filler trimmed from the start/end of an unmatched condition (PlantDoc's
# "Apple Scab Leaf"); kept in the middle, where it is part of the name.
_EDGE_FILLER = {"leaf", "leaves", "plant", "the", "a", "an", "of", "on"}

_PARENTHETICAL = re.compile(r"\(([^)]*)\)")


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


def _split_alias(text: str) -> Tuple[List[str], List[str]]:
    """Return (main tokens, alias tokens) where the alias is any parenthetical text."""
    alias = " ".join(_PARENTHETICAL.findall(text))
    return _tokenize(_PARENTHETICAL.sub(" ", text)), _tokenize(alias)


# (plant, synonym tokens), longest synonyms first so "date palm" beats "palm".
_PLANT_PATTERNS: List[Tuple[str, List[str]]] = sorted(
    ((plant, _tokenize(syn)) for plant, synonyms in PLANT_SYNONYMS.items() for syn in synonyms),
    key=lambda item: -len(item[1]),
)


def _find_plant(tokens: List[str]) -> Optional[Tuple[str, int, int]]:
    """Earliest whole-word occurrence of any plant synonym: (plant, start, end)."""
    best = None
    for plant, pattern in _PLANT_PATTERNS:
        n = len(pattern)
        for start in range(len(tokens) - n + 1):
            if tokens[start:start + n] == pattern:
                if best is None or start < best[1]:
                    best = (plant, start, start + n)
                break
    return best


class LabelNormalizer:
    def __init__(self):
        self._unmatched_plants: List[str] = []

    def normalize(self, raw_label: str) -> CanonicalLabel:
        raw = raw_label.strip()

        # Case 1: already in canonical "plant___condition" form (PlantVillage-derived sets).
        if "___" in raw:
            plant_part, condition_part = raw.split("___", 1)
            found = _find_plant(_tokenize(plant_part))
            plant = found[0] if found else self._slugify(plant_part)
            tokens, alias = _split_alias(condition_part)
            leading = _find_plant(tokens)
            if leading and leading[0] == plant and leading[1] == 0:
                tokens = tokens[leading[2]:]  # "Tomato___Tomato_mosaic_virus"
            return CanonicalLabel(plant=plant, condition=self._resolve_condition(tokens, alias))

        tokens, alias = _split_alias(raw)
        found = _find_plant(tokens)
        if found is None:
            self._unmatched_plants.append(raw_label)
            return CanonicalLabel(plant="unknown", condition=self._slugify(raw))

        plant, start, end = found
        remainder = tokens[:start] + tokens[end:]
        return CanonicalLabel(plant=plant, condition=self._resolve_condition(remainder, alias))

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_condition(tokens: List[str], alias: List[str]) -> str:
        significant = [t for t in tokens if t not in _NOISE_WORDS]
        if not significant:
            return "unspecified"

        for candidate in (tokens, significant, alias, [t for t in alias if t not in _NOISE_WORDS]):
            key = "_".join(candidate)
            if key in CONDITION_SYNONYMS:
                return CONDITION_SYNONYMS[key]

        start, end = 0, len(tokens)
        while tokens[start] in _EDGE_FILLER:
            start += 1
        while tokens[end - 1] in _EDGE_FILLER:
            end -= 1
        return "_".join(tokens[start:end])

    def _slugify(self, text: str) -> str:
        return "_".join(_tokenize(text)) or "unspecified"

    @property
    def unmatched_plant_labels(self) -> List[str]:
        """Raw labels that could not be matched to a known plant — surfaced for the
        pre-flight audit report so a human can extend PLANT_SYNONYMS if needed."""
        return list(self._unmatched_plants)
