"""
Compact U-Net (Ronneberger et al., 2015) for 3-class leaf/lesion segmentation
(background, leaf, lesion — see masks.py).

Chosen over YOLO-seg or a large transformer because: (1) it is pure PyTorch with no
new dependency, (2) it trains on CPU for small annotated sets, and (3) semantic
(per-pixel) output is exactly what the affected-area formula needs; instance masks
are not required. `base_channels` can be raised when a GPU and more data exist.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

NUM_SEG_CLASSES = 3


class _DoubleConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    def __init__(self, in_channels: int = 3, num_classes: int = NUM_SEG_CLASSES,
                 base_channels: int = 32, depth: int = 4):
        super().__init__()
        if depth < 1:
            raise ValueError("depth must be >= 1")
        self.depth = depth
        chans = [base_channels * (2 ** i) for i in range(depth + 1)]
        self.downs = nn.ModuleList()
        prev = in_channels
        for c in chans[:-1]:
            self.downs.append(_DoubleConv(prev, c))
            prev = c
        self.bottleneck = _DoubleConv(chans[-2], chans[-1])
        self.ups = nn.ModuleList()
        self.up_convs = nn.ModuleList()
        for c in reversed(chans[:-1]):
            self.ups.append(nn.ConvTranspose2d(c * 2, c, kernel_size=2, stride=2))
            self.up_convs.append(_DoubleConv(c * 2, c))
        self.head = nn.Conv2d(chans[0], num_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skips = []
        for down in self.downs:
            x = down(x)
            skips.append(x)
            x = F.max_pool2d(x, 2)
        x = self.bottleneck(x)
        for up, conv, skip in zip(self.ups, self.up_convs, reversed(skips)):
            x = up(x)
            if x.shape[-2:] != skip.shape[-2:]:
                x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            x = conv(torch.cat([skip, x], dim=1))
        return self.head(x)
