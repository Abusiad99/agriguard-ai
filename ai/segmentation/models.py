"""
Segmentation model registry. Both architectures sit on a timm encoder
(`features_only=True`), the same backbone family the classifier uses, so no new
dependency is needed and any timm encoder can be swapped in by name.

  unet           U-Net decoder with skip connections at every encoder stage. Default:
                 keeps fine lesion boundaries (small spots matter for area
                 measurement) and trains well on hundreds of annotated images.
  deeplabv3plus  ASPP context module + one low-level skip. Better when lesions vary
                 a lot in scale and there is more data / compute.

Add an architecture by writing an nn.Module with forward(x) -> logits [B, C, H, W] and
registering a builder in ARCHITECTURES.
"""
from __future__ import annotations

from typing import Callable, Dict

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F


def _conv_bn_relu(cin: int, cout: int, k: int = 3, dilation: int = 1) -> nn.Sequential:
    pad = dilation * (k // 2)
    return nn.Sequential(nn.Conv2d(cin, cout, k, padding=pad, dilation=dilation, bias=False),
                         nn.BatchNorm2d(cout), nn.ReLU(inplace=True))


class UNet(nn.Module):
    def __init__(self, encoder: str, num_classes: int, pretrained: bool, decoder_channels=(256, 128, 64, 32, 16)):
        super().__init__()
        self.encoder = timm.create_model(encoder, features_only=True, pretrained=pretrained)
        channels = self.encoder.feature_info.channels()
        deep, skips = channels[-1], list(reversed(channels[:-1]))
        blocks, cin = [], deep
        for i, skip in enumerate(skips):
            cout = decoder_channels[min(i, len(decoder_channels) - 1)]
            blocks.append(nn.Sequential(_conv_bn_relu(cin + skip, cout), _conv_bn_relu(cout, cout)))
            cin = cout
        self.blocks = nn.ModuleList(blocks)
        self.head = nn.Sequential(_conv_bn_relu(cin, decoder_channels[-1]), nn.Conv2d(decoder_channels[-1], num_classes, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        size = x.shape[-2:]
        features = self.encoder(x)
        y = features[-1]
        for block, skip in zip(self.blocks, reversed(features[:-1])):
            y = F.interpolate(y, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            y = block(torch.cat([y, skip], dim=1))
        y = F.interpolate(y, size=size, mode="bilinear", align_corners=False)
        return self.head(y)


class _ASPP(nn.Module):
    def __init__(self, cin: int, cout: int = 256, rates=(6, 12, 18)):
        super().__init__()
        self.branches = nn.ModuleList([_conv_bn_relu(cin, cout, 1)] + [_conv_bn_relu(cin, cout, 3, r) for r in rates])
        self.pool = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Conv2d(cin, cout, 1, bias=False), nn.ReLU(inplace=True))
        self.project = _conv_bn_relu(cout * (len(rates) + 2), cout, 1)

    def forward(self, x):
        pooled = F.interpolate(self.pool(x), size=x.shape[-2:], mode="bilinear", align_corners=False)
        return self.project(torch.cat([b(x) for b in self.branches] + [pooled], dim=1))


class DeepLabV3Plus(nn.Module):
    def __init__(self, encoder: str, num_classes: int, pretrained: bool):
        super().__init__()
        self.encoder = timm.create_model(encoder, features_only=True, pretrained=pretrained)
        reductions = self.encoder.feature_info.reduction()
        channels = self.encoder.feature_info.channels()
        self.low_idx = min(range(len(reductions)), key=lambda i: abs(reductions[i] - 4))
        self.high_idx = len(reductions) - 1
        for i, r in enumerate(reductions):  # prefer output stride 16 for the context features
            if r == 16:
                self.high_idx = i
        self.aspp = _ASPP(channels[self.high_idx])
        self.low_proj = _conv_bn_relu(channels[self.low_idx], 48, 1)
        self.decoder = nn.Sequential(_conv_bn_relu(256 + 48, 256), _conv_bn_relu(256, 256))
        self.classifier = nn.Conv2d(256, num_classes, 1)

    def forward(self, x):
        size = x.shape[-2:]
        features = self.encoder(x)
        low = self.low_proj(features[self.low_idx])
        high = F.interpolate(self.aspp(features[self.high_idx]), size=low.shape[-2:], mode="bilinear", align_corners=False)
        y = self.classifier(self.decoder(torch.cat([high, low], dim=1)))
        return F.interpolate(y, size=size, mode="bilinear", align_corners=False)


ARCHITECTURES: Dict[str, Callable[..., nn.Module]] = {
    "unet": UNet,
    "deeplabv3plus": DeepLabV3Plus,
}


def build_segmentation_model(architecture: str, encoder: str, num_classes: int, pretrained: bool) -> nn.Module:
    if architecture not in ARCHITECTURES:
        raise ValueError(f"Unknown segmentation architecture '{architecture}'. Known: {sorted(ARCHITECTURES)}")
    return ARCHITECTURES[architecture](encoder=encoder, num_classes=num_classes, pretrained=pretrained)
