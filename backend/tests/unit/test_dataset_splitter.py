"""DatasetSplitter (classifier train/val/test split): no image in two splits, small classes
handled without crashing, and every class with at least 3 images is tested.

The splitter used to raise ValueError for classes of about 3-6 images (sklearn cannot
stratify a class with one member left) - e.g. after duplicates are removed from the
smallest classes of a real dataset. Rows here are SYNTHETIC file names; no images are read."""
from __future__ import annotations

import pandas as pd
import pytest

from app.infrastructure.external import ai_pipeline_client  # noqa: F401  (puts the repo-root `ai` package on sys.path)

from ai.data.splitter import DatasetSplitter


def _index(sizes):
    return pd.DataFrame([{"image_path": f"class{c}/img{i}.jpg", "canonical_label": f"class{c}"}
                         for c, n in enumerate(sizes) for i in range(n)])


def _per_class(frame):
    return frame["canonical_label"].value_counts().to_dict()


@pytest.mark.parametrize("sizes", [
    [5, 5, 5, 300], [3, 300], [4, 300], [6, 250, 40], [7, 8, 13, 16, 19, 390],  # the last mirrors the smallest real classes
    [3, 4, 5, 6],                                                              # only small classes
    [1, 2, 300],                                                               # classes too small to test at all
])
def test_small_classes_do_not_crash_and_nothing_overlaps(sizes):
    df = _index(sizes)
    splits = DatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42).split(df)
    train, val, test = set(splits.train.image_path), set(splits.val.image_path), set(splits.test.image_path)
    assert not (train & val) and not (train & test) and not (val & test)       # no leakage between splits
    assert train | val | test == set(df.image_path)                            # nothing lost
    assert len(splits.train) + len(splits.val) + len(splits.test) == len(df)   # nothing duplicated
    for c, n in enumerate(sizes):
        label = f"class{c}"
        if n >= 3:   # tested and validated on at least one image each, and still trained on
            assert _per_class(splits.val).get(label, 0) >= 1, (label, n)
            assert _per_class(splits.test).get(label, 0) >= 1, (label, n)
            assert _per_class(splits.train).get(label, 0) >= 1, (label, n)
        else:        # too small to hold anything back
            assert _per_class(splits.train).get(label, 0) == n


def test_split_is_reproducible_for_a_seed_and_roughly_70_15_15():
    df = _index([200, 120, 60, 5])
    a = DatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=7).split(df)
    b = DatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=7).split(df)
    assert list(a.train.image_path) == list(b.train.image_path) and list(a.test.image_path) == list(b.test.image_path)
    assert abs(len(a.train) / len(df) - 0.70) < 0.02 and abs(len(a.val) / len(df) - 0.15) < 0.02
