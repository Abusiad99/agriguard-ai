"""Upload validation checks the decoded content, not client-supplied metadata."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.application.services.image_validation import validate_image_bytes
from app.core.exceptions import InvalidImageError, UnsupportedMediaTypeError
from tests.conftest import make_leaf_like_image_bytes


def _encode(fmt: str, size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 30)).save(buf, format=fmt)
    return buf.getvalue()


def test_accepts_jpeg_png_webp():
    for fmt in ("JPEG", "PNG", "WEBP"):
        v = validate_image_bytes(_encode(fmt))
        assert v.format == fmt
        assert v.image.size == (64, 64)


def test_rejects_garbage_and_empty():
    with pytest.raises(InvalidImageError):
        validate_image_bytes(b"not an image at all")
    with pytest.raises(InvalidImageError):
        validate_image_bytes(b"")


def test_rejects_truncated_jpeg():
    data = make_leaf_like_image_bytes()
    with pytest.raises(InvalidImageError):
        validate_image_bytes(data[: len(data) // 3])


def test_rejects_decodable_but_disallowed_format():
    with pytest.raises(UnsupportedMediaTypeError):
        validate_image_bytes(_encode("GIF"))
    with pytest.raises(UnsupportedMediaTypeError):
        validate_image_bytes(_encode("BMP"))


def test_rejects_excessive_pixel_count(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_image_pixels", 1000)
    with pytest.raises(InvalidImageError):
        validate_image_bytes(_encode("PNG", size=(100, 100)))
