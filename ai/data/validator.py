"""
ImageValidator — validates that a file is a genuine, decodable image before it enters
the training pipeline (FR-DATA — implicit data quality requirement; mirrors FR-SCAN-2's
runtime validation, applied here at dataset-build time).

Uses Pillow's `verify()` for a fast structural check, then a full `load()` on a second
open (verify() invalidates the file handle for further use) to catch truncation errors
that `verify()` alone can miss.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Iterator, Tuple

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("agriguard.data.validator")


class ImageValidator:
    def is_valid(self, path: Path) -> bool:
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                img.load()
                if img.mode not in ("RGB", "L", "RGBA", "P", "CMYK"):
                    return False
                width, height = img.size
                if width < 10 or height < 10:
                    return False
            return True
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
            return False

    def filter_valid(self, paths: Iterable[Path]) -> Iterator[Path]:
        for p in paths:
            if self.is_valid(p):
                yield p
            else:
                logger.debug("Rejected corrupted/unreadable image: %s", p)

    def validate_batch(self, paths: Iterable[Path]) -> Tuple[list, list]:
        valid, invalid = [], []
        for p in paths:
            (valid if self.is_valid(p) else invalid).append(p)
        return valid, invalid
