"""
Image quality checks run on every scan (before classification) and used when two
scans of the same plant are compared.

These are simple, documented heuristics — not a learned quality model. They flag
images that are too small, too dark, overexposed or blurry so that results computed
from them (and comparisons between them) carry an explicit caveat. They never block a
scan on their own.

Thresholds are module constants so they can be tuned with real field photos later.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List

import numpy as np
from PIL import Image

MIN_SIDE_PX = 224            # below this, lesion detail is largely lost at model input size
DARK_MEAN_LUMA = 40.0        # mean luma (0-255) below this: underexposed
BRIGHT_MEAN_LUMA = 220.0     # mean luma above this: overexposed / washed out
BLUR_LAPLACIAN_VAR = 60.0    # variance of the Laplacian below this: likely out of focus
_ANALYSIS_SIDE = 512         # images are downscaled to this before analysis (speed, scale-invariance)


@dataclass
class ImageQuality:
    width: int
    height: int
    mean_luma: float
    sharpness: float  # variance of the Laplacian on the downscaled grayscale image
    issues: List[str] = field(default_factory=list)  # too_small | too_dark | overexposed | blurry

    @property
    def acceptable(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        data = asdict(self)
        data["acceptable"] = self.acceptable
        return data


def assess(image: Image.Image) -> ImageQuality:
    width, height = image.size
    gray = image.convert("L")
    gray.thumbnail((_ANALYSIS_SIDE, _ANALYSIS_SIDE))
    pixels = np.asarray(gray, dtype=np.float32)

    mean_luma = float(pixels.mean())
    # 4-neighbour Laplacian without SciPy/OpenCV.
    lap = (-4 * pixels[1:-1, 1:-1] + pixels[:-2, 1:-1] + pixels[2:, 1:-1]
           + pixels[1:-1, :-2] + pixels[1:-1, 2:])
    sharpness = float(lap.var()) if lap.size else 0.0

    issues = []
    if min(width, height) < MIN_SIDE_PX:
        issues.append("too_small")
    if mean_luma < DARK_MEAN_LUMA:
        issues.append("too_dark")
    elif mean_luma > BRIGHT_MEAN_LUMA:
        issues.append("overexposed")
    if sharpness < BLUR_LAPLACIAN_VAR:
        issues.append("blurry")
    return ImageQuality(width=width, height=height, mean_luma=round(mean_luma, 2),
                        sharpness=round(sharpness, 2), issues=issues)
