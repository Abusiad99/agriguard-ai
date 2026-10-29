"""
Image-quality gate run BEFORE the disease classifier.

Purpose: a classifier always outputs *some* class, even for a blurry, black, or
non-plant image. Checking basic capture quality first lets the system ask the user
for a better photo instead of returning a confident-looking result computed from
an unsuitable image.

Checks (all computed on a downscaled grayscale/RGB copy; pure numpy + Pillow so the
backend can run them without torch):

  resolution     shorter side in pixels.
  sharpness      variance of the Laplacian at a fixed working resolution — a classic
                 focus measure (Pech-Pacheco et al., 2000). It also drops for images
                 with genuinely little texture, so it is a heuristic, not a blur
                 detector with guaranteed accuracy.
  exposure       judged on the SUBJECT, not the whole frame: the mean luminance of
                 mid-tone pixels (16..245) and how much of the frame they cover.
                 A leaf scanned on white paper or photographed against a black
                 studio background has large clipped areas but a well-exposed
                 subject and must not be rejected (both occur in PlantWild).
  contrast       luminance standard deviation (near-uniform images).
  vegetation     fraction of pixels whose Excess-Green index is clearly positive
                 (Woebbecke et al., 1995). Diseased tissue, fruit and lesion close-
                 ups are often NOT green, so this is only ever a WARNING, never a
                 rejection on its own.

Thresholds are configurable (env vars below). The defaults were chosen by measuring
the metric distributions on the PlantWild v2 training images and on synthetically
degraded copies of them (see `python -m ai.quality.calibrate_quality` and
docs/AI_RELIABILITY.md). They are heuristic operating points, not validated
detectors of "unsuitable for diagnosis" — that would require images labelled for
diagnostic usability, which the project does not have.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageOps

QUALITY_VERSION = "1.0.0"
_WORKING_LONG_SIDE = 512


def _f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class QualityThresholds:
    min_side_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_MIN_SIDE_REJECT", 96))
    min_side_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_MIN_SIDE_WARN", 224))
    sharpness_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_SHARPNESS_REJECT", 12.0))
    sharpness_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_SHARPNESS_WARN", 40.0))
    dark_mean_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_DARK_MEAN_REJECT", 25.0))
    dark_mean_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_DARK_MEAN_WARN", 50.0))
    bright_clip_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_BRIGHT_CLIP_REJECT", 0.60))
    bright_clip_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_BRIGHT_CLIP_WARN", 0.30))
    dark_clip_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_DARK_CLIP_REJECT", 0.75))
    # Subject (mid-tone) exposure: the subject itself must be too dark / washed out.
    subject_dark_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_SUBJECT_DARK_REJECT", 45.0))
    subject_bright_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_SUBJECT_BRIGHT_REJECT", 185.0))
    min_subject_fraction: float = field(default_factory=lambda: _f("AGRIGUARD_QC_MIN_SUBJECT_FRACTION", 0.08))
    contrast_reject: float = field(default_factory=lambda: _f("AGRIGUARD_QC_CONTRAST_REJECT", 6.0))
    contrast_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_CONTRAST_WARN", 18.0))
    vegetation_warn: float = field(default_factory=lambda: _f("AGRIGUARD_QC_VEGETATION_WARN", 0.03))


@dataclass
class QualityIssue:
    code: str          # stable machine code, localized by the frontend
    severity: str      # "reject" | "warning"
    message: str       # English fallback text
    hint: str          # what the user can do about it
    metric: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class QualityReport:
    status: str  # "ok" | "warning" | "rejected"
    issues: List[QualityIssue]
    metrics: Dict[str, float]
    version: str = QUALITY_VERSION

    @property
    def rejected(self) -> bool:
        return self.status == "rejected"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [asdict(i) for i in self.issues],
            "metrics": self.metrics,
            "version": self.version,
        }


def _laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float64)
    lap = (-4.0 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var()) if lap.size else 0.0


def compute_quality_metrics(image: Image.Image) -> Dict[str, float]:
    """Return the raw metrics (no thresholding). Respects EXIF orientation."""
    img = ImageOps.exif_transpose(image).convert("RGB")
    width, height = img.size
    scale = _WORKING_LONG_SIDE / float(max(width, height))
    if scale < 1.0:
        img = img.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.BILINEAR)
    rgb = np.asarray(img, dtype=np.float64)
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    mid = (lum >= 16) & (lum <= 245)

    total = rgb[..., 0] + rgb[..., 1] + rgb[..., 2] + 1e-6
    r, g, b = rgb[..., 0] / total, rgb[..., 1] / total, rgb[..., 2] / total
    exg = 2.0 * g - r - b
    # Ignore near-black pixels, whose chromaticity is noise.
    valid = lum > 20
    vegetation = float(((exg > 0.05) & valid).sum() / max(1, valid.sum())) if valid.any() else 0.0

    return {
        "width": float(width),
        "height": float(height),
        "min_side": float(min(width, height)),
        "sharpness_laplacian_var": _laplacian_variance(lum),
        "mean_luminance": float(lum.mean()),
        "luminance_std": float(lum.std()),
        "dark_clip_fraction": float((lum < 16).mean()),
        "bright_clip_fraction": float((lum > 245).mean()),
        "midtone_fraction": float(mid.mean()),
        "midtone_mean_luminance": float(lum[mid].mean()) if mid.any() else 0.0,
        "vegetation_fraction": vegetation,
    }


def assess_image_quality(image: Image.Image, thresholds: Optional[QualityThresholds] = None) -> QualityReport:
    t = thresholds or QualityThresholds()
    m = compute_quality_metrics(image)
    issues: List[QualityIssue] = []

    def add(code, severity, message, hint, metric=None, threshold=None):
        issues.append(QualityIssue(code=code, severity=severity, message=message, hint=hint,
                                   metric=None if metric is None else round(float(metric), 4),
                                   threshold=threshold))

    if m["min_side"] < t.min_side_reject:
        add("resolution_too_low", "reject", "The image resolution is too low to examine leaf symptoms.",
            "Use the camera's normal photo mode and move closer so the leaf fills the frame.",
            m["min_side"], t.min_side_reject)
    elif m["min_side"] < t.min_side_warn:
        add("resolution_low", "warning", "The image resolution is low; fine symptoms may be missed.",
            "If possible, retake the photo at a higher resolution.", m["min_side"], t.min_side_warn)

    # Darkness/overexposure are checked before "no detail": a very dark photo is also
    # near-uniform, and "too dark" tells the user what to fix. Both are judged on the
    # subject (mid-tones), so dark or white studio backgrounds are not penalized.
    little_subject = m["midtone_fraction"] < t.min_subject_fraction
    subject_dark = m["midtone_mean_luminance"] < t.subject_dark_reject
    subject_washed_out = m["midtone_mean_luminance"] > t.subject_bright_reject
    if (m["mean_luminance"] < t.dark_mean_reject or m["dark_clip_fraction"] > t.dark_clip_reject) and \
            (little_subject or subject_dark):
        add("too_dark", "reject", "The image is too dark to see the plant tissue.",
            "Photograph in daylight or open shade; avoid night photos without light.",
            m["midtone_mean_luminance"], t.subject_dark_reject)
    elif m["bright_clip_fraction"] > t.bright_clip_reject and (little_subject or subject_washed_out):
        add("overexposed", "reject", "Large parts of the image are washed out by light.",
            "Avoid direct sun glare or flash on the leaf; shade the leaf or change the angle.",
            m["bright_clip_fraction"], t.bright_clip_reject)
    elif m["luminance_std"] < t.contrast_reject:
        add("no_detail", "reject", "The image is almost uniform and shows no visible detail.",
            "Make sure the lens is not covered and the plant is in the frame.",
            m["luminance_std"], t.contrast_reject)
    else:
        if m["mean_luminance"] < t.dark_mean_warn and m["midtone_mean_luminance"] < t.dark_mean_warn + 20:
            add("dark", "warning", "The image is rather dark.", "More even light would help.",
                m["mean_luminance"], t.dark_mean_warn)
        if m["bright_clip_fraction"] > t.bright_clip_warn and m["midtone_mean_luminance"] > t.subject_bright_reject - 25:
            add("partly_overexposed", "warning", "Some areas are overexposed.",
                "Reduce glare by shading the leaf or changing the angle.",
                m["bright_clip_fraction"], t.bright_clip_warn)
        if m["luminance_std"] < t.contrast_warn:
            add("low_contrast", "warning", "The image has low contrast.",
                "Avoid haze or backlight; photograph with light falling on the leaf.",
                m["luminance_std"], t.contrast_warn)

    if not any(i.code in ("no_detail", "too_dark", "overexposed") for i in issues):
        if m["sharpness_laplacian_var"] < t.sharpness_reject:
            add("too_blurry", "reject", "The image is too blurry to examine leaf symptoms.",
                "Hold the camera steady, tap the screen to focus on the leaf, and retake the photo.",
                m["sharpness_laplacian_var"], t.sharpness_reject)
        elif m["sharpness_laplacian_var"] < t.sharpness_warn:
            add("slightly_blurry", "warning", "The image looks slightly out of focus.",
                "Tap to focus on the affected leaf before taking the photo.",
                m["sharpness_laplacian_var"], t.sharpness_warn)

    if m["vegetation_fraction"] < t.vegetation_warn and not any(i.severity == "reject" for i in issues):
        add("little_plant_tissue", "warning",
            "Little green plant tissue was detected. This can be normal for heavily diseased "
            "leaves or fruit, but may also mean the plant is not in the frame.",
            "Make sure the affected leaf or plant part fills most of the photo.",
            m["vegetation_fraction"], t.vegetation_warn)

    if any(i.severity == "reject" for i in issues):
        status = "rejected"
    elif issues:
        status = "warning"
    else:
        status = "ok"
    rounded = {k: round(v, 4) for k, v in m.items()}
    return QualityReport(status=status, issues=issues, metrics=rounded)
