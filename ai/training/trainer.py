"""
Trainer — the core training loop: class-weighted loss / weighted sampling
(FR-DATA-6), backbone-freeze warmup, mixed precision, early stopping, and per-epoch
history logging (feeds "Save training history" / "Save training graphs").
"""
from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler

from ai.config import CONFIG
from ai.data.dataset_torch import PlantDiseaseDataset
from ai.models.architectures import freeze_backbone, unfreeze_all

logger = logging.getLogger("agriguard.training.trainer")


def _build_class_weights(class_counts: Dict[int, int], num_classes: int) -> torch.Tensor:
    counts = np.array([class_counts.get(i, 0) for i in range(num_classes)], dtype=np.float64)
    counts = np.where(counts == 0, 1, counts)  # avoid div-by-zero for absent classes
    weights = counts.sum() / (num_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


def _build_weighted_sampler(dataset: PlantDiseaseDataset) -> WeightedRandomSampler:
    class_counts = dataset.class_sample_counts()
    sample_weights = []
    for i in range(len(dataset)):
        label_idx = dataset.label_encoder.encode(dataset.df.iloc[i][dataset.label_col])
        sample_weights.append(1.0 / class_counts[label_idx])
    return WeightedRandomSampler(weights=sample_weights, num_samples=len(sample_weights), replacement=True)


class Trainer:
    def __init__(self, model: nn.Module, device: torch.device,
                 train_dataset: PlantDiseaseDataset, val_dataset: PlantDiseaseDataset,
                 num_classes: int):
        self.model = model.to(device)
        self.device = device
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.num_classes = num_classes
        self.cfg = CONFIG.train

        self.history: Dict[str, List[float]] = {
            "train_loss": [], "train_accuracy": [], "val_loss": [], "val_accuracy": [],
        }

    def _build_loaders(self):
        sampler = None
        shuffle = True
        if self.cfg.use_weighted_sampler:
            sampler = _build_weighted_sampler(self.train_dataset)
            shuffle = False

        train_loader = DataLoader(
            self.train_dataset, batch_size=self.cfg.batch_size, sampler=sampler,
            shuffle=shuffle, num_workers=self.cfg.num_workers, pin_memory=(self.device.type == "cuda"),
        )
        val_loader = DataLoader(
            self.val_dataset, batch_size=self.cfg.batch_size, shuffle=False,
            num_workers=self.cfg.num_workers, pin_memory=(self.device.type == "cuda"),
        )
        return train_loader, val_loader

    def _build_criterion(self) -> nn.Module:
        if self.cfg.use_class_weighting:
            class_counts = self.train_dataset.class_sample_counts()
            weights = _build_class_weights(class_counts, self.num_classes).to(self.device)
            return nn.CrossEntropyLoss(weight=weights)
        return nn.CrossEntropyLoss()

    def fit(self) -> Dict[str, List[float]]:
        train_loader, val_loader = self._build_loaders()
        criterion = self._build_criterion()
        optimizer = torch.optim.AdamW(
            self.model.parameters(), lr=self.cfg.learning_rate, weight_decay=self.cfg.weight_decay
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=2)
        scaler = torch.cuda.amp.GradScaler(enabled=(self.cfg.mixed_precision and self.device.type == "cuda"))

        if self.cfg.freeze_backbone_epochs > 0:
            freeze_backbone(self.model)
            logger.info("Backbone frozen for the first %d epoch(s) (transfer-learning warmup).",
                        self.cfg.freeze_backbone_epochs)

        best_val_loss = float("inf")
        best_state_dict = None
        epochs_without_improvement = 0

        for epoch in range(1, self.cfg.num_epochs + 1):
            if epoch == self.cfg.freeze_backbone_epochs + 1:
                unfreeze_all(self.model)
                logger.info("Backbone unfrozen at epoch %d; fine-tuning all layers.", epoch)

            train_loss, train_acc = self._run_epoch(train_loader, criterion, optimizer, scaler, is_train=True)
            val_loss, val_acc = self._run_epoch(val_loader, criterion, optimizer, scaler, is_train=False)

            self.history["train_loss"].append(train_loss)
            self.history["train_accuracy"].append(train_acc)
            self.history["val_loss"].append(val_loss)
            self.history["val_accuracy"].append(val_acc)

            scheduler.step(val_loss)
            logger.info(
                "Epoch %d/%d — train_loss=%.4f train_acc=%.4f val_loss=%.4f val_acc=%.4f",
                epoch, self.cfg.num_epochs, train_loss, train_acc, val_loss, val_acc,
            )

            if val_loss < best_val_loss - 1e-4:
                best_val_loss = val_loss
                best_state_dict = {k: v.clone() for k, v in self.model.state_dict().items()}
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= self.cfg.early_stopping_patience:
                    logger.info("Early stopping triggered at epoch %d (patience=%d).",
                                epoch, self.cfg.early_stopping_patience)
                    break

        if best_state_dict is not None:
            self.model.load_state_dict(best_state_dict)
            logger.info("Restored best model weights (val_loss=%.4f).", best_val_loss)

        return self.history

    def _run_epoch(self, loader: DataLoader, criterion: nn.Module,
                    optimizer: torch.optim.Optimizer, scaler: torch.cuda.amp.GradScaler,
                    is_train: bool):
        self.model.train(mode=is_train)
        total_loss, correct, total = 0.0, 0, 0

        context = torch.enable_grad() if is_train else torch.no_grad()
        with context:
            for images, labels in loader:
                images, labels = images.to(self.device), labels.to(self.device)

                if is_train:
                    optimizer.zero_grad()

                with torch.autocast(device_type=self.device.type if self.device.type in ("cuda", "cpu") else "cpu",
                                     enabled=(self.cfg.mixed_precision and self.device.type == "cuda")):
                    outputs = self.model(images)
                    loss = criterion(outputs, labels)

                if is_train:
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()

                total_loss += loss.item() * images.size(0)
                preds = outputs.argmax(dim=1)
                correct += (preds == labels).sum().item()
                total += images.size(0)

        avg_loss = total_loss / max(1, total)
        accuracy = correct / max(1, total)
        return avg_loss, accuracy
