"""Image-quality gate mechanics (synthetic degradations) and label normalization."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from ai.data.label_normalizer import LabelNormalizer
from ai.quality.image_quality import assess_image_quality, compute_quality_metrics


def _textured(size=512, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    base = np.stack([60 + 0 * xx, 140 + 0 * xx, 50 + 0 * xx], axis=-1).astype(float)
    pattern = 40 * np.sin(xx / 5.0) * np.cos(yy / 7.0)
    arr = np.clip(base + pattern[..., None] + rng.normal(0, 15, (size, size, 1)), 0, 255).astype("uint8")
    return Image.fromarray(arr)


def test_sharp_well_exposed_leaf_passes():
    rep = assess_image_quality(_textured())
    assert rep.status == "ok", rep.issues
    assert rep.metrics["vegetation_fraction"] > 0.5


def test_blur_darkness_overexposure_resolution_and_blank_are_detected():
    img = _textured()
    codes = lambda im: {i.code for i in assess_image_quality(im).issues}  # noqa: E731
    assert "too_blurry" in codes(img.filter(ImageFilter.GaussianBlur(8)))
    assert codes(ImageEnhance.Brightness(img).enhance(0.08)) & {"too_dark", "no_detail"}
    assert codes(ImageEnhance.Brightness(img).enhance(4.0)) & {"overexposed", "no_detail"}
    assert "resolution_too_low" in codes(img.resize((60, 60)))
    assert "no_detail" in codes(Image.new("RGB", (400, 400), (128, 128, 128)))


def test_non_green_subject_only_warns():
    arr = np.array(_textured())[..., ::-1]  # swap channels -> reddish/blue image with the same texture
    rep = assess_image_quality(Image.fromarray(arr.copy()))
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
