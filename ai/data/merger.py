"""
DatasetMerger — orchestrates the full ingestion chain (FR-DATA-1..3):

  scan datasets/ -> per-dataset adapter selection -> raw (image, raw_label) pairs
  -> label normalization -> corrupted-image filtering -> cross-dataset deduplication
  -> a single unified, canonical-labeled image index.

The unified index is a pandas DataFrame with columns:
  image_path, plant, condition, canonical_label, source_dataset

and is persisted to `artifacts/unified_dataset_index.csv` for auditability — anyone
can inspect exactly what the pipeline trained on and trace every row back to its
source dataset folder and original raw label.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from ai.config import CONFIG
from ai.data.dataset_scanner import DatasetAudit, DatasetScanner
from ai.data.dedup import DuplicateDetector
from ai.data.label_normalizer import LabelNormalizer
from ai.data.validator import ImageValidator

logger = logging.getLogger("agriguard.data.merger")

UNIFIED_INDEX_COLUMNS = ["image_path", "plant", "condition", "canonical_label", "source_dataset", "raw_label"]


@dataclass
class MergeResult:
    dataframe: pd.DataFrame
    audit: DatasetAudit
    unmatched_plant_labels: List[str]
    rejected_corrupt_count: int
    duplicate_count: int


class DatasetMerger:
    def __init__(
        self,
        scanner: DatasetScanner | None = None,
        normalizer: LabelNormalizer | None = None,
        validator: ImageValidator | None = None,
        dedup: DuplicateDetector | None = None,
    ):
        self.scanner = scanner or DatasetScanner()
        self.normalizer = normalizer or LabelNormalizer()
        self.validator = validator or ImageValidator()
        self.dedup = dedup or DuplicateDetector()

    def build_unified_dataset(self, persist: bool = True) -> MergeResult:
        audit = self.scanner.preflight_check()

        rows = []
        for sample in self.scanner.iter_all_samples():
            canonical = self.normalizer.normalize(sample.raw_label)
            rows.append({
                "image_path": str(sample.image_path),
                "plant": canonical.plant,
                "condition": canonical.condition,
                "canonical_label": canonical.canonical,
                "source_dataset": sample.source_dataset,
                "raw_label": sample.raw_label,
            })

        df = pd.DataFrame(rows, columns=UNIFIED_INDEX_COLUMNS)
        logger.info("Raw merged samples (pre-validation): %d", len(df))

        # --- Corrupted image filtering ---
        valid_paths = set(self.validator.filter_valid(Path(p) for p in df["image_path"]))
        rejected_count = len(df) - sum(df["image_path"].apply(lambda p: Path(p) in valid_paths))
        df = df[df["image_path"].apply(lambda p: Path(p) in valid_paths)].reset_index(drop=True)
        logger.info("After corrupted-image filtering: %d valid (%d rejected)", len(df), rejected_count)

        # --- Cross-dataset deduplication ---
        kept_paths, dup_map = self.dedup.deduplicate([Path(p) for p in df["image_path"]])
        kept_set = set(str(p) for p in kept_paths)
        df = df[df["image_path"].isin(kept_set)].reset_index(drop=True)
        logger.info("After deduplication: %d unique images", len(df))

        # --- Enforce minimum images-per-class (drop classes too sparse to train/eval) ---
        class_counts = df["canonical_label"].value_counts()
        sparse_classes = class_counts[class_counts < CONFIG.data.min_images_per_class].index.tolist()
        if sparse_classes:
            logger.warning(
                "Dropping %d class(es) with fewer than %d images: %s",
                len(sparse_classes), CONFIG.data.min_images_per_class, sparse_classes,
            )
            df = df[~df["canonical_label"].isin(sparse_classes)].reset_index(drop=True)

        if df.empty:
            raise RuntimeError(
                "After validation, deduplication, and minimum-class-size filtering, "
                "no usable samples remain. Check that datasets/ contains enough "
                "correctly-labeled images per class (minimum "
                f"{CONFIG.data.min_images_per_class})."
            )

        if persist:
            out_path = CONFIG.paths.artifacts_dir / "unified_dataset_index.csv"
            df.to_csv(out_path, index=False)
            logger.info("Unified dataset index written to %s", out_path)

        return MergeResult(
            dataframe=df,
            audit=audit,
            unmatched_plant_labels=sorted(set(self.normalizer.unmatched_plant_labels)),
            rejected_corrupt_count=rejected_count,
            duplicate_count=len(dup_map),
        )
