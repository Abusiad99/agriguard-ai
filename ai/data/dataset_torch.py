"""
PlantDiseaseDataset — a torch.utils.data.Dataset over a split DataFrame produced by
DatasetSplitter, resolving canonical labels to integer indices via a LabelEncoder and
applying the provided transform (train transform with augmentation, or eval transform
without) at `__getitem__` time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset

from ai.data.label_encoder import LabelEncoder


class PlantDiseaseDataset(Dataset):
    def __init__(self, dataframe: pd.DataFrame, label_encoder: LabelEncoder,
                 transform: Optional[Callable] = None, label_col: str = "canonical_label"):
        self.df = dataframe.reset_index(drop=True)
        self.label_encoder = label_encoder
        self.transform = transform
        self.label_col = label_col

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int):
        row = self.df.iloc[idx]
        image_path = Path(row["image_path"])
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            if self.transform is not None:
                tensor = self.transform(img)
            else:
                tensor = img

        label_idx = self.label_encoder.encode(row[self.label_col])
        return tensor, torch.tensor(label_idx, dtype=torch.long)

    def class_sample_counts(self):
        """Per-class sample counts in this split, used to build class weights /
        the weighted sampler (FR-DATA-6)."""
        counts = self.df[self.label_col].value_counts()
        return {self.label_encoder.encode(k): int(v) for k, v in counts.items()}
