"""
Upload validation for plant photos (FR-SCAN-1/2): decodes the bytes and checks the
ACTUAL image format, not the client-supplied Content-Type header or filename, which
are trivially spoofed. Rejects corrupted files, unsupported formats, and
decompression bombs (images whose pixel count far exceeds what a phone camera
produces, which could exhaust server memory when decoded).
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import InvalidImageError, UnsupportedMediaTypeError

_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@dataclass
class ValidatedImage:
    image: Image.Image
    format: str
    mime_type: str


def validate_image_bytes(image_bytes: bytes) -> ValidatedImage:
    settings = get_settings()
    if not image_bytes:
        raise InvalidImageError("The uploaded file is empty.")
    allowed = {fmt for fmt, mime in _FORMAT_TO_MIME.items() if mime in settings.allowed_image_content_types}
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            probe = Image.open(io.BytesIO(image_bytes))
            fmt = (probe.format or "").upper()
            width, height = probe.size
            if width * height > settings.max_image_pixels:
                raise InvalidImageError(
                    f"The image is too large ({width}x{height}); the maximum is "
                    f"{settings.max_image_pixels // 1_000_000} megapixels.")
            if fmt not in allowed:
                raise UnsupportedMediaTypeError(
                    f"Unsupported image format '{fmt or 'unknown'}'. Please upload a JPEG, PNG, or WebP photo.")
            probe.verify()
            image = Image.open(io.BytesIO(image_bytes))  # verify() invalidates the handle
            image.load()
        except (InvalidImageError, UnsupportedMediaTypeError):
            raise
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise InvalidImageError("The uploaded file is not a valid, decodable image.")
    return ValidatedImage(image=image, format=fmt, mime_type=_FORMAT_TO_MIME[fmt])
