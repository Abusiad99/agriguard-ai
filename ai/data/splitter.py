"""
DatasetSplitter — stratified Train/Validation/Test split (FR-DATA-4).

Uses scikit-learn's `train_test_split` twice (unified index -> train vs. temp, then
temp -> val vs. test) with `stratify=` on the canonical label so every class is
proportionally represented in all three partitions. Classes with too few samples to
stratify safely (fewer than 2 per target split) are still included but a warning is
logged, since sklearn requires at least 1 member per class per split.
"""
from __future__ import annotations

import logging
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

    def split(self, df: pd.DataFrame, label_col: str = "canonical_label") -> DatasetSplits:
        class_counts = df[label_col].value_counts()
        stratifiable = df[label_col].isin(class_counts[class_counts >= 3].index)
        too_small = df[~stratifiable]
        if not too_small.empty:
            logger.warning(
                "Classes with < 3 samples cannot be safely stratified into 3 splits; "
                "these %d sample(s) are assigned entirely to the training split: %s",
                len(too_small), sorted(too_small[label_col].unique().tolist()),
            )

        stratifiable_df = df[stratifiable].reset_index(drop=True)

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

        train_df = pd.concat([train_df, too_small], ignore_index=True)

        logger.info(
            "Split sizes -> train: %d, val: %d, test: %d (classes: %d)",
            len(train_df), len(val_df), len(test_df), df[label_col].nunique(),
        )
        return DatasetSplits(
            train=train_df.reset_index(drop=True),
            val=val_df.reset_index(drop=True),
            test=test_df.reset_index(drop=True),
        )
