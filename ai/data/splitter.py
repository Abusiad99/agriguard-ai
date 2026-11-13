"""
DatasetSplitter — stratified Train/Validation/Test split (FR-DATA-4).

Uses scikit-learn's `train_test_split` twice (unified index -> train vs. temp, then
temp -> val vs. test) with `stratify=` on the canonical label so every class is
proportionally represented in all three partitions.

Small classes are handled separately, because sklearn refuses to stratify when a class
has a single member left for the val/test half (it raised ValueError for classes of
about 3-6 images):
- fewer than 3 images: all go to TRAIN (a warning is logged; the class is never tested);
- 3 up to the smallest size sklearn can always stratify: one image to VAL, one to TEST,
  the rest to TRAIN, chosen with the same seed.
An image is always in exactly one split.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import pandas as pd
from sklearn.model_selection import train_test_split

from ai.config import CONFIG

logger = logging.getLogger("agriguard.data.splitter")


@dataclass
class DatasetSplits:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


class DatasetSplitter:
    def __init__(self, train_ratio: float | None = None, val_ratio: float | None = None,
                 test_ratio: float | None = None, seed: int | None = None):
        self.train_ratio = train_ratio if train_ratio is not None else CONFIG.data.train_ratio
        self.val_ratio = val_ratio if val_ratio is not None else CONFIG.data.val_ratio
        self.test_ratio = test_ratio if test_ratio is not None else CONFIG.data.test_ratio
        self.seed = seed if seed is not None else CONFIG.data.random_seed

    def _min_class_size_for_sklearn(self) -> int:
        """Smallest class size for which both stratified sklearn splits always work: the
        val/test half must keep at least 2 images of the class (sklearn may put up to
        floor(n * train_ratio) + 1 of them into TRAIN)."""
        n = 3
        while n - (math.floor(n * self.train_ratio) + 1) < 2:
            n += 1
        return n

    def split(self, df: pd.DataFrame, label_col: str = "canonical_label") -> DatasetSplits:
        class_counts = df[label_col].value_counts()
        safe_min = self._min_class_size_for_sklearn()
        tiny_classes = class_counts[class_counts < 3].index
        small_classes = class_counts[(class_counts >= 3) & (class_counts < safe_min)].index

        too_small = df[df[label_col].isin(tiny_classes)]
        if not too_small.empty:
            logger.warning(
                "Classes with < 3 samples cannot be safely stratified into 3 splits; "
                "these %d sample(s) are assigned entirely to the training split: %s",
                len(too_small), sorted(too_small[label_col].unique().tolist()),
            )

        # Small classes: exactly one image each to VAL and TEST, the rest to TRAIN.
        small_train, small_val, small_test = [], [], []
        for label in sorted(small_classes):
            rows = df[df[label_col] == label].sample(frac=1.0, random_state=self.seed)
            small_val.append(rows.iloc[[0]])
            small_test.append(rows.iloc[[1]])
            small_train.append(rows.iloc[2:])
        if len(small_classes):
            logger.info("%d small class(es) (3-%d images) split as 1 val / 1 test / rest train: %s",
                        len(small_classes), safe_min - 1, sorted(small_classes))

        stratifiable_df = df[~df[label_col].isin(tiny_classes) & ~df[label_col].isin(small_classes)].reset_index(drop=True)

        if stratifiable_df.empty:
            train_df = val_df = test_df = stratifiable_df
        else:
            train_df, temp_df = train_test_split(
                stratifiable_df,
                train_size=self.train_ratio,
                stratify=stratifiable_df[label_col],
                random_state=self.seed,
            )

            relative_val_ratio = self.val_ratio / (self.val_ratio + self.test_ratio)
            val_df, test_df = train_test_split(
                temp_df,
                train_size=relative_val_ratio,
                stratify=temp_df[label_col],
                random_state=self.seed,
            )

        train_df = pd.concat([train_df, too_small, *small_train], ignore_index=True)
        val_df = pd.concat([val_df, *small_val], ignore_index=True)
        test_df = pd.concat([test_df, *small_test], ignore_index=True)

        logger.info(
            "Split sizes -> train: %d, val: %d, test: %d (classes: %d)",
            len(train_df), len(val_df), len(test_df), df[label_col].nunique(),
        )
        return DatasetSplits(
            train=train_df.reset_index(drop=True),
            val=val_df.reset_index(drop=True),
            test=test_df.reset_index(drop=True),
        )
