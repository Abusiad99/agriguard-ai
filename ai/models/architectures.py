"""
Model architecture factory (see ai/MODEL_ARCHITECTURE_DECISIONS.md for the full
comparison and justification).

`build_classifier` is backbone-agnostic: it wraps any `timm` model with a
classification head sized to the dataset's actual class count (from LabelEncoder),
so the same code path serves EfficientNet, ConvNeXt, ViT, and MobileNetV4 without
per-architecture branching.

`build_yolo_detector` is the designated upgrade path for bbox-annotated pest data
(e.g. IP102-style XML annotations, already parsed by XmlAnnotationAdapter) — it is a
thin, optional wrapper around Ultralytics YOLOv11 and is only invoked if the caller
explicitly opts into detection training with bbox data present.
"""
from __future__ import annotations

import logging

import timm
import torch
import torch.nn as nn

logger = logging.getLogger("agriguard.models.architectures")

SUPPORTED_ARCHITECTURES = {
    "efficientnet_b0": "efficientnet_b0",
    "efficientnet_b3": "efficientnet_b3",
    "convnext_tiny": "convnext_tiny",
    "vit_base": "vit_base_patch16_224",
    "mobilenetv4": "mobilenetv4_conv_small",
}


def resolve_device(preference: str = "auto") -> torch.device:
    if preference != "auto":
        return torch.device(preference)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def build_classifier(architecture: str, num_classes: int, pretrained: bool = True) -> nn.Module:
    """Build a timm classification model with `num_classes` outputs.

    Raises a clear error for unsupported architecture names rather than silently
    falling back, since a typo in AGRIGUARD_ARCHITECTURE should fail fast.
    """
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise ValueError(
            f"Unsupported architecture '{architecture}'. Supported: "
            f"{sorted(SUPPORTED_ARCHITECTURES.keys())}"
        )
    timm_name = SUPPORTED_ARCHITECTURES[architecture]
    logger.info("Building classifier: architecture=%s (timm=%s), num_classes=%d, pretrained=%s",
                architecture, timm_name, num_classes, pretrained)
    model = timm.create_model(timm_name, pretrained=pretrained, num_classes=num_classes)
    return model


def freeze_backbone(model: nn.Module) -> None:
    """Freeze all parameters except the final classification head, used for the
    initial `freeze_backbone_epochs` warmup (transfer-learning best practice)."""
    head_param_names = set()
    for name, _ in model.named_parameters():
        if any(k in name for k in ("head", "classifier", "fc")):
            head_param_names.add(name)
    for name, param in model.named_parameters():
        param.requires_grad = name in head_param_names
    logger.info("Backbone frozen; trainable head params: %d", len(head_param_names))


def unfreeze_all(model: nn.Module) -> None:
    for param in model.parameters():
        param.requires_grad = True


def build_yolo_detector(num_classes: int, pretrained_weights: str = "yolo11n.pt"):
    """Optional upgrade path for bbox-annotated pest detection data.

    Only imported/invoked when the caller explicitly requests detection training
    over bbox data (e.g. from XML-annotated IP102-style samples). Not part of the
    default classification-based pipeline (see MODEL_ARCHITECTURE_DECISIONS.md §3).
    """
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "Training a YOLOv11 detector requires the 'ultralytics' package "
            "(`pip install ultralytics`). This is an optional dependency, not "
            "required for the default classification-based pipeline."
        ) from exc
    model = YOLO(pretrained_weights)
    logger.info("Loaded YOLOv11 base weights '%s' for detector fine-tuning (%d classes)",
                pretrained_weights, num_classes)
    return model
