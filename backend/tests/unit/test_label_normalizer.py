"""
Unit tests for ai/data/label_normalizer.py — the raw dataset label -> canonical
"{plant}___{condition}" mapping that becomes the model's class list (FR-DATA-2).

The bundled dataset (datasets/plantwild_v2) is checked class by class: every folder
must map to its real plant and to its own class, so no two diseases are merged and
no plant is lost to "unknown". Only the folder names are read; no image is opened,
so this runs even when the Git LFS images haven't been downloaded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.data.label_normalizer import LabelNormalizer  # noqa: E402

PLANTWILD_DIR = REPO_ROOT / "datasets" / "plantwild_v2"

# Leading word(s) of each PlantWild class folder -> the plant it must map to.
EXPECTED_PLANT_BY_PREFIX = {
    "apple": "apple", "banana": "banana", "basil": "basil", "bean": "bean",
    "bell pepper": "pepper", "blueberry": "blueberry", "broccoli": "broccoli",
    "cabbage": "cabbage", "carrot": "carrot", "cauliflower": "cauliflower",
    "celery": "celery", "cherry": "cherry", "citrus": "citrus", "coffee": "coffee",
    "corn": "corn", "cucumber": "cucumber", "eggplant": "eggplant", "garlic": "garlic",
    "ginger": "ginger", "grape": "grape", "grapevine": "grape", "lettuce": "lettuce",
    "maple": "maple", "peach": "peach", "plum": "plum", "potato": "potato",
    "raspberry": "raspberry", "rice": "rice", "soybean": "soybean", "squash": "squash",
    "strawberry": "strawberry", "tobacco": "tobacco", "tomato": "tomato", "wheat": "wheat",
    "zucchini": "zucchini",
}


def _plantwild_classes() -> list:
    if not PLANTWILD_DIR.is_dir():
        pytest.skip("datasets/plantwild_v2 is not present in this checkout")
    return sorted(p.name for p in PLANTWILD_DIR.iterdir() if p.is_dir())


def _expected_plant(raw_label: str) -> str:
    prefixes = [p for p in EXPECTED_PLANT_BY_PREFIX if raw_label == p or raw_label.startswith(p + " ")]
    assert prefixes, f"test table has no plant for {raw_label!r}"
    return EXPECTED_PLANT_BY_PREFIX[max(prefixes, key=len)]


class TestPlantWildDataset:
    def test_every_class_maps_to_its_plant(self):
        normalizer = LabelNormalizer()
        wrong = {
            raw: normalizer.normalize(raw).plant
            for raw in _plantwild_classes()
            if normalizer.normalize(raw).plant != _expected_plant(raw)
        }
        assert wrong == {}
        assert normalizer.unmatched_plant_labels == []

    def test_every_class_stays_a_distinct_label(self):
        normalizer = LabelNormalizer()
        classes = _plantwild_classes()
        by_canonical: dict = {}
        for raw in classes:
            by_canonical.setdefault(normalizer.normalize(raw).canonical, []).append(raw)
        merged = {canonical: raws for canonical, raws in by_canonical.items() if len(raws) > 1}
        assert merged == {}
        assert len(by_canonical) == len(classes)

    def test_no_class_loses_its_condition(self):
        normalizer = LabelNormalizer()
        lost = [raw for raw in _plantwild_classes()
                if normalizer.normalize(raw).condition in ("unspecified", "healthy", "")]
        assert lost == []

    @pytest.mark.parametrize("raw, canonical", [
        # Previously all three collapsed into wheat___rust via substring matching.
        ("wheat leaf rust", "wheat___leaf_rust"),
        ("wheat stem rust", "wheat___stem_rust"),
        ("wheat stripe rust", "wheat___stripe_rust"),
        # "leaf" inside a disease name is part of the name, not filler.
        ("corn gray leaf spot", "corn___gray_leaf_spot"),
        ("corn northern leaf blight", "corn___northern_leaf_blight"),
        ("tomato leaf mold", "tomato___leaf_mold"),
        ("tomato yellow leaf curl virus", "tomato___yellow_leaf_curl_virus"),
        ("tomato septoria leaf spot", "tomato___septoria_leaf_spot"),
        # Multi-word plants and plant-name variants.
        ("bell pepper bacterial spot", "pepper___bacterial_spot"),
        ("grapevine leafroll disease", "grape___leafroll_disease"),
        ("maple tar spot", "maple___tar_spot"),
        # Previously "plant='unknown'" because these plants weren't in PLANT_SYNONYMS.
        ("banana panama disease", "banana___panama_disease"),
        ("soybean frog eye leaf spot", "soybean___frog_eye_leaf_spot"),
        # A parenthetical alias doesn't leak into the class name.
        ("wheat bacterial leaf streak (black chaff)", "wheat___bacterial_leaf_streak"),
        ("citrus greening disease", "citrus___citrus_greening"),
    ])
    def test_specific_plantwild_labels(self, raw, canonical):
        assert LabelNormalizer().normalize(raw).canonical == canonical


class TestOtherDatasetConventions:
    """The conventions the module docstring promises to handle besides PlantWild."""

    @pytest.mark.parametrize("raw, canonical", [
        # PlantVillage "Plant___Condition" folders.
        ("Tomato___healthy", "tomato___healthy"),
        ("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "tomato___yellow_leaf_curl_virus"),
        ("Apple___Cedar_apple_rust", "apple___cedar_apple_rust"),
        ("Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", "grape___leaf_blight"),
        ("Grape___Esca_(Black_Measles)", "grape___esca_black_measles"),
        ("Orange___Haunglongbing_(Citrus_greening)", "orange___citrus_greening"),
        ("Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "corn___gray_leaf_spot"),
        ("Pepper,_bell___Bacterial_spot", "pepper___bacterial_spot"),
        # PlantDoc "Plant [leaf] condition [leaf]" folders.
        ("Apple Scab Leaf", "apple___scab"),
        ("Tomato leaf late blight", "tomato___late_blight"),
        # Date palm folders.
        ("healthy_palm", "date_palm___healthy"),
    ])
    def test_known_conventions(self, raw, canonical):
        assert LabelNormalizer().normalize(raw).canonical == canonical

    def test_label_without_a_known_plant_is_kept_verbatim_under_unknown(self):
        normalizer = LabelNormalizer()
        assert normalizer.normalize("black_scorch").canonical == "unknown___black_scorch"
        assert normalizer.unmatched_plant_labels == ["black_scorch"]

    def test_plant_names_match_whole_words_only(self):
        # "bean" must not match inside "soybean", nor "grape" inside "grapefruit".
        normalizer = LabelNormalizer()
        assert normalizer.normalize("soybean rust").plant == "soybean"
        assert normalizer.normalize("grapefruit scab").plant == "unknown"
