"""
AdapterRegistry — the piece that makes dataset ingestion truly automatic (FR-DATA-1/2).

For each top-level folder discovered under `datasets/`, the registry asks every
registered adapter whether it recognizes the structure (`matches`) and, among matches,
picks the one with highest `confidence`. This means a user can drop PlantVillage,
PlantDoc, the Kaggle New Plant Diseases Dataset, IP102, a Date Palm dataset, and a Red
Palm Weevil dataset into `datasets/` in whatever internal shape they were downloaded
in, and the correct adapter is chosen per-dataset without any dataset-name mapping
table anywhere in the code (C1).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, List, Optional

from ai.data.adapters.base_adapter import DatasetAdapter, RawSample
from ai.data.adapters.csv_annotation_adapter import CsvAnnotationAdapter
from ai.data.adapters.imagefolder_adapter import ImageFolderAdapter
from ai.data.adapters.json_annotation_adapter import JsonAnnotationAdapter
from ai.data.adapters.xml_annotation_adapter import XmlAnnotationAdapter

logger = logging.getLogger("agriguard.data.adapters")


class AdapterRegistry:
    def __init__(self, adapters: Optional[List[DatasetAdapter]] = None):
        # Order matters only as a tiebreaker when confidences are exactly equal;
        # ImageFolder is checked last among ties because annotation-file adapters
        # are more specific signals when both patterns coexist in a messy folder.
        self.adapters: List[DatasetAdapter] = adapters or [
            XmlAnnotationAdapter(),
            JsonAnnotationAdapter(),
            CsvAnnotationAdapter(),
            ImageFolderAdapter(),
        ]

    def select_adapter(self, dataset_root: Path) -> Optional[DatasetAdapter]:
        best_adapter: Optional[DatasetAdapter] = None
        best_confidence = 0.0
        for adapter in self.adapters:
            try:
                if not adapter.matches(dataset_root):
                    continue
                conf = adapter.confidence(dataset_root)
            except Exception as exc:  # noqa: BLE001 — a misbehaving adapter must not crash discovery
                logger.warning("Adapter %s raised while probing %s: %s", adapter.name, dataset_root, exc)
                continue
            if conf > best_confidence:
                best_confidence = conf
                best_adapter = adapter
        if best_adapter is not None:
            logger.info(
                "Dataset '%s' matched adapter '%s' (confidence=%.2f)",
                dataset_root.name, best_adapter.name, best_confidence,
            )
        return best_adapter

    def iter_samples_for_dataset(self, dataset_root: Path) -> Iterator[RawSample]:
        adapter = self.select_adapter(dataset_root)
        if adapter is None:
            logger.warning("No adapter matched dataset folder '%s' — skipping.", dataset_root)
            return
        yield from adapter.iter_samples(dataset_root)
