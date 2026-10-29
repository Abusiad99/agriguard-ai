"""
LabelNormalizer — maps arbitrary raw dataset labels onto AgriGuard AI's canonical
schema: "{plant}___{condition}" (FR-DATA-2).

Different datasets format labels differently:
  - PlantVillage:              "Tomato___Early_blight", "Tomato___healthy"
  - PlantDoc:                  "Tomato leaf", "Apple Scab Leaf", "Corn Gray leaf spot"
  - New Plant Diseases (Kaggle): same convention as PlantVillage (it is derived from it)
  - PlantWild:                 "wheat stripe rust", "banana panama disease"
  - IP102 (pest names):         "rice_leaf_roller", "red palm weevil"
  - Date Palm datasets:         "Bayoud", "black_scorch", "healthy_palm"

The normalizer therefore does NOT assume a single delimiter convention. It:
  1. Lowercases the raw label and tokenizes it on non-alphanumeric characters.
  2. If the "___" canonical delimiter is already present, splits on it directly.
  3. Otherwise, finds a known plant synonym as a *whole-token* sequence (longest
     synonym wins, so "bell pepper" beats "pepper" and "soybean" is never read as
     "bean").
  4. Removes the matched plant tokens from the remainder to derive the condition.
  5. Maps the condition through CONDITION_SYNONYMS by *exact* match only; if that
     fails, generic noise words at the start/end ("leaf", "disease", ...) are
     stripped and the exact match is retried; otherwise the slug is kept verbatim.
  6. If no known plant is found, the plant is recorded as "unknown" and the full raw
     label (normalized) becomes the condition — these are surfaced in the audit report
     for manual review rather than silently mis-merged into an unrelated class.

Why exact matching only (changed from an earlier substring-based version): substring
matching silently merged genuinely different diseases — e.g. "wheat leaf rust",
"wheat stem rust" and "wheat stripe rust" all collapsed into "wheat___rust", and 75 of
PlantWild's 115 classes were bucketed under plant="unknown", which also broke the
per-plant probability mass used at inference time. A label that is not recognized
now keeps its own distinct slug instead of being merged into a different class.

This is a deterministic heuristic layer, not a guarantee of perfect taxonomy
alignment; misclassified labels should be corrected by extending PLANT_SYNONYMS /
CONDITION_SYNONYMS rather than by editing pipeline logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Canonical plant name -> list of synonym phrases that may appear in raw labels.
PLANT_SYNONYMS: Dict[str, List[str]] = {
    "tomato": ["tomato"],
    "potato": ["potato"],
    "corn": ["corn", "maize"],
    "wheat": ["wheat"],
    "rice": ["rice"],
    "cucumber": ["cucumber"],
    "pepper": ["pepper", "bell pepper", "capsicum"],
    "lettuce": ["lettuce"],
    "mint": ["mint"],
    "parsley": ["parsley"],
    "coriander": ["coriander", "cilantro"],
    "grape": ["grape", "grapevine"],
    "apple": ["apple"],
    "olive": ["olive"],
    "orange": ["orange"],
    "lemon": ["lemon"],
    "citrus": ["citrus"],
    "date_palm": ["date palm", "palm", "phoenix dactylifera"],
    "banana": ["banana"],
    "basil": ["basil"],
    "bean": ["bean"],
    "soybean": ["soybean", "soy bean", "soya"],
    "blueberry": ["blueberry"],
    "raspberry": ["raspberry"],
    "strawberry": ["strawberry"],
    "broccoli": ["broccoli"],
    "cabbage": ["cabbage"],
    "cauliflower": ["cauliflower"],
    "carrot": ["carrot"],
    "celery": ["celery"],
    "cherry": ["cherry"],
    "coffee": ["coffee"],
    "eggplant": ["eggplant", "aubergine", "brinjal"],
    "garlic": ["garlic"],
    "ginger": ["ginger"],
    "maple": ["maple"],
    "peach": ["peach"],
    "plum": ["plum"],
    "squash": ["squash"],
    "zucchini": ["zucchini", "courgette"],
    "tobacco": ["tobacco"],
}

# Raw condition phrase (already tokenized/underscore-joined) -> canonical condition
# spelling. Matched EXACTLY against the whole condition phrase.
CONDITION_SYNONYMS: Dict[str, str] = {
    "healthy": "healthy",
    "health": "healthy",
    "earlyblight": "early_blight",
    "lateblight": "late_blight",
    "leafmold": "leaf_mold",
    "powderymildew": "powdery_mildew",
    "downymildew": "downy_mildew",
    "leafcurl": "leaf_curl",
    "curl_virus": "leaf_curl",
    "leafspot": "leaf_spot",
    "bacterialspot": "bacterial_spot",
    "fusariumwilt": "fusarium_wilt",
    "rootrot": "root_rot",
    "blackscorch": "black_scorch",
    "bayoud": "bayoud_disease",
    "leafblight": "leaf_blight",
    "redpalmweevil": "red_palm_weevil",
    "weevil": "red_palm_weevil",
    "red_weevil": "red_palm_weevil",
    "haunglongbing": "citrus_greening",
    "haunglongbing_citrus_greening": "citrus_greening",
    "huanglongbing": "citrus_greening",
    "greening": "citrus_greening",
    "esca": "esca_black_measles",
    "black_measles": "esca_black_measles",
    "two_spotted_spider_mite": "spider_mites",
    "spider_mites_two_spotted_spider_mite": "spider_mites",
    "cercospora_leaf_spot_gray_leaf_spot": "gray_leaf_spot",
    "leaf_blight_isariopsis_leaf_spot": "leaf_blight",
    "common_rust": "rust",
    "bacterial_leaf_spot": "bacterial_spot",
}

_NOISE_WORDS = {"leaf", "leaves", "disease", "plant", "the", "a", "an", "of", "on"}
_LEADING_NOISE = {"the", "a", "an", "of", "on"}


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


def _synonym_index() -> List[Tuple[Tuple[str, ...], str]]:
    """(synonym token tuple, canonical plant), longest synonyms first so a more
    specific phrase always wins over a shorter one it contains."""
    entries = []
    for plant, synonyms in PLANT_SYNONYMS.items():
        for syn in synonyms:
            toks = tuple(_tokenize(syn))
            if toks:
                entries.append((toks, plant))
    entries.sort(key=lambda e: len(e[0]), reverse=True)
    return entries


_SYNONYM_INDEX = _synonym_index()


def _find_plant(tokens: List[str]) -> Optional[Tuple[str, int, int]]:
    """Return (plant, start, end) of the earliest, longest whole-token synonym
    match in `tokens`, or None."""
    best: Optional[Tuple[str, int, int]] = None
    for syn_tokens, plant in _SYNONYM_INDEX:
        n = len(syn_tokens)
        for start in range(0, len(tokens) - n + 1):
            if tuple(tokens[start:start + n]) == syn_tokens:
                if best is None or start < best[1] or (start == best[1] and n > best[2] - best[1]):
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
            plant = self._match_plant(plant_part) or self._slugify(plant_part)
            cond_tokens = _tokenize(condition_part)
            # PlantVillage repeats the plant at the start of some conditions
            # ("Tomato___Tomato_mosaic_virus"); drop only a *leading* repeat so that
            # e.g. "Apple___Cedar_apple_rust" keeps its full name.
            match = _find_plant(cond_tokens)
            if match is not None and match[1] == 0 and match[0] == plant and match[2] < len(cond_tokens):
                cond_tokens = cond_tokens[match[2]:]
            return CanonicalLabel(plant=plant, condition=self._normalize_condition(cond_tokens))

        tokens = _tokenize(raw)
        match = _find_plant(tokens)
        if match is None:
            self._unmatched_plants.append(raw_label)
            return CanonicalLabel(plant="unknown", condition=self._slugify(raw))

        plant, start, end = match
        remainder = tokens[:start] + tokens[end:]
        meaningful = [t for t in remainder if t not in _NOISE_WORDS]
        if not meaningful:
            # e.g. PlantDoc "Tomato leaf" — a plant-only label means a healthy sample.
            return CanonicalLabel(plant=plant, condition="healthy")
        return CanonicalLabel(plant=plant, condition=self._normalize_condition(remainder))

    # ------------------------------------------------------------------
    def _match_plant(self, text: str) -> Optional[str]:
        match = _find_plant(_tokenize(text))
        return match[0] if match else None

    def _normalize_condition(self, tokens: List[str]) -> str:
        if not tokens:
            return "unspecified"
        joined = "_".join(tokens)
        if joined in CONDITION_SYNONYMS:
            return CONDITION_SYNONYMS[joined]
        # Only articles are stripped from the start ("leaf mold" must stay "leaf_mold");
        # generic words are stripped from the end ("Apple Scab Leaf" -> "scab").
        stripped = list(tokens)
        while stripped and stripped[0] in _LEADING_NOISE:
            stripped.pop(0)
        while stripped and stripped[-1] in _NOISE_WORDS:
            stripped.pop()
        if not stripped:
            return joined
        joined_stripped = "_".join(stripped)
        return CONDITION_SYNONYMS.get(joined_stripped, joined_stripped)

    def _match_condition(self, text: str) -> Optional[str]:
        """Exact synonym lookup only (kept for callers/tests that use it directly)."""
        norm = "_".join(_tokenize(text))
        return CONDITION_SYNONYMS.get(norm)

    def _slugify(self, text: str) -> str:
        return "_".join(_tokenize(text)) or "unspecified"

    @property
    def unmatched_plant_labels(self) -> List[str]:
        """Raw labels that could not be matched to a known plant — surfaced for the
        pre-flight audit report so a human can extend PLANT_SYNONYMS if needed."""
        return list(self._unmatched_plants)
