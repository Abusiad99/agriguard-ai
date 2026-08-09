"""
DataPipeline — the single orchestration point that `train.py` and `evaluate.py` call
into. Ties together: DatasetMerger (scan+normalize+validate+dedup) -> DatasetSplitter
(stratified train/val/test) -> LabelEncoder -> PlantDiseaseDataset (train transform vs.
eval transform). This is the one place that sequences FR-DATA-1..6 end to end.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ai.data.dataset_torch import PlantDiseaseDataset
from ai.data.label_encoder import LabelEncoder
from ai.data.merger import DatasetMerger, MergeResult
from ai.data.preprocessing import PreprocessingConfig, build_eval_transform, build_train_transform
from ai.data.splitter import DatasetSplitter, DatasetSplits

logger = logging.getLogger("agriguard.pipeline")


@dataclass
class PreparedData:
    train_dataset: PlantDiseaseDataset
    val_dataset: PlantDiseaseDataset
    test_dataset: PlantDiseaseDataset
    label_encoder: LabelEncoder
    preprocessing_config: PreprocessingConfig
    merge_result: MergeResult
    splits: DatasetSplits


def prepare_data() -> PreparedData:
    logger.info("=== Stage 1/4: Dataset discovery, normalization, validation, dedup ===")
    merger = DatasetMerger()
    merge_result = merger.build_unified_dataset()

    if merge_result.unmatched_plant_labels:
        logger.warning(
            "%d raw label(s) could not be matched to a known plant and were bucketed "
            "under plant='unknown'. Consider extending PLANT_SYNONYMS in "
            "ai/data/label_normalizer.py. Examples: %s",
            len(merge_result.unmatched_plant_labels),
            merge_result.unmatched_plant_labels[:10],
        )

    logger.info("=== Stage 2/4: Stratified train/val/test split ===")
    splitter = DatasetSplitter()
    splits = splitter.split(merge_result.dataframe)

    logger.info("=== Stage 3/4: Label encoding ===")
    label_encoder = LabelEncoder.fit(merge_result.dataframe["canonical_label"])
    logger.info("Discovered %d canonical classes.", label_encoder.num_classes)

    logger.info("=== Stage 4/4: Building datasets (augmentation on TRAIN only) ===")
    preprocessing_config = PreprocessingConfig.from_global_config()
    train_transform = build_train_transform(preprocessing_config)
    eval_transform = build_eval_transform(preprocessing_config)

    train_dataset = PlantDiseaseDataset(splits.train, label_encoder, transform=train_transform)
    val_dataset = PlantDiseaseDataset(splits.val, label_encoder, transform=eval_transform)
    test_dataset = PlantDiseaseDataset(splits.test, label_encoder, transform=eval_transform)

    return PreparedData(
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        test_dataset=test_dataset,
        label_encoder=label_encoder,
        preprocessing_config=preprocessing_config,
        merge_result=merge_result,
        splits=splits,
    )
