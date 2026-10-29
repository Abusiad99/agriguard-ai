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
from pathlib import Path

import timm
import torch
import torch.nn as nn

from ai.config import CONFIG

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
    local_weights = CONFIG.train.pretrained_weights_path if pretrained else ""
    logger.info("Building classifier: architecture=%s (timm=%s), num_classes=%d, pretrained=%s%s",
                architecture, timm_name, num_classes, pretrained,
                f" (local weights: {local_weights})" if local_weights else "")
    if local_weights:
        model = timm.create_model(timm_name, pretrained=False, num_classes=num_classes)
        load_backbone_weights(model, Path(local_weights))
        return model
    model = timm.create_model(timm_name, pretrained=pretrained, num_classes=num_classes)
    return model


def load_backbone_weights(model: nn.Module, weights_path: Path) -> None:
    """Load an ImageNet checkpoint into `model`, skipping any tensor whose shape does
    not match (i.e. the 1000-class ImageNet head, replaced by our own head).

    Fails loudly if the file is missing or if almost nothing matched, because a
    silent fallback to random weights would invalidate every downstream metric.
    """
    if not weights_path.is_file():
        raise FileNotFoundError(f"AGRIGUARD_PRETRAINED_WEIGHTS points to a missing file: {weights_path}")
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "state_dict" in state and isinstance(state["state_dict"], dict):
        state = state["state_dict"]
    own = model.state_dict()
    compatible = {k: v for k, v in state.items() if k in own and own[k].shape == v.shape}
    skipped = sorted(k for k in state if k not in compatible)
    missing = sorted(k for k in own if k not in compatible)
    model.load_state_dict(compatible, strict=False)
    coverage = len(compatible) / max(1, len(own))
    logger.info("Loaded %d/%d backbone tensors from %s (skipped from checkpoint: %s; left at init: %s)",
                len(compatible), len(own), weights_path, skipped[:6], missing[:6])
    if coverage < 0.9:
        raise ValueError(
            f"Only {coverage:.0%} of the model's tensors matched {weights_path.name}; "
            "the checkpoint does not belong to this architecture."
        )


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
