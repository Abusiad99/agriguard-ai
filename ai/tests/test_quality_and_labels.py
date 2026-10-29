"""Image-quality gate mechanics (synthetic degradations) and label normalization."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from ai.data.label_normalizer import LabelNormalizer
from ai.quality.image_quality import assess_image_quality, compute_quality_metrics


def _textured(size=512, seed=0):
    """Synthetic 'leaf photo': a green ellipse with vein texture on a brown background
    (low-frequency structure plus fine detail, like a real photo)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    leaf = ((xx - size / 2) / (0.4 * size)) ** 2 + ((yy - size / 2) / (0.3 * size)) ** 2 <= 1
    arr = np.zeros((size, size, 3), dtype=float)
    arr[...] = (200, 185, 160)
    arr[leaf] = (60, 140, 50)
    pattern = 30 * np.sin(xx / 5.0) * np.cos(yy / 7.0)
    arr = np.clip(arr + pattern[..., None] * leaf[..., None] + rng.normal(0, 10, (size, size, 1)), 0, 255)
    return Image.fromarray(arr.astype("uint8"))


def test_sharp_well_exposed_leaf_passes():
    rep = assess_image_quality(_textured())
    assert rep.status == "ok", rep.issues
    assert rep.metrics["vegetation_fraction"] > 0.3


def test_blur_darkness_overexposure_resolution_and_blank_are_detected():
    img = _textured()
    codes = lambda im: {i.code for i in assess_image_quality(im).issues}  # noqa: E731
    assert "too_blurry" in codes(img.filter(ImageFilter.GaussianBlur(8)))
    assert "too_dark" in codes(ImageEnhance.Brightness(img).enhance(0.08))
    assert codes(ImageEnhance.Brightness(img).enhance(4.0)) & {"overexposed", "partly_overexposed"}
    assert "resolution_too_low" in codes(img.resize((60, 60)))
    assert "no_detail" in codes(Image.new("RGB", (400, 400), (128, 128, 128)))


def test_non_green_subject_only_warns():
    # e.g. a close-up of a rotting fruit: sharp and well exposed, but not green
    arr = np.array(_textured()).astype(float)
    arr = np.stack([arr[..., 1], arr[..., 1] * 0.5, arr[..., 2] * 0.6], axis=-1)
    rep = assess_image_quality(Image.fromarray(np.clip(arr, 0, 255).astype("uint8")))
    assert not rep.rejected
    assert any(i.code == "little_plant_tissue" and i.severity == "warning" for i in rep.issues)


def test_metrics_respect_exif_orientation_and_downscale():
    m = compute_quality_metrics(_textured(size=1600))
    assert m["min_side"] == 1600 and m["sharpness_laplacian_var"] > 0


def test_label_normalizer_keeps_distinct_diseases_distinct():
    n = LabelNormalizer()
    labels = ["wheat leaf rust", "wheat stem rust", "wheat stripe rust", "soybean rust", "bean rust"]
    canon = [n.normalize(x).canonical for x in labels]
    assert len(set(canon)) == len(labels)
    assert n.normalize("soybean rust").plant == "soybean"
    assert n.normalize("bell pepper bacterial spot").canonical == "pepper___bacterial_spot"
    assert n.normalize("Tomato___Tomato_Yellow_Leaf_Curl_Virus").canonical == "tomato___yellow_leaf_curl_virus"
    assert n.normalize("Apple___Cedar_apple_rust").canonical == "apple___cedar_apple_rust"
    assert n.normalize("Tomato leaf").canonical == "tomato___healthy"
    assert n.normalize("Apple Scab Leaf").canonical == "apple___scab"
    assert n.normalize("tomato leaf mold").canonical == "tomato___leaf_mold"
    assert n.normalize("mystery plant blight").plant == "unknown"
