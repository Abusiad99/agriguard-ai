"""Shared logging setup for train.py / evaluate.py / predict.py / inference.py."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from ai.config import CONFIG


def configure_logging(log_filename: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("agriguard")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    log_path = CONFIG.paths.logs_dir / log_filename
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
