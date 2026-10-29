"""Helpers for presenting model class labels ("plant___condition") to people."""
from __future__ import annotations

from typing import Optional, Tuple


def split_label(label: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not label:
        return None, None
    if "___" in label:
        plant, condition = label.split("___", 1)
        return plant, condition
    return None, label


def humanize(token: Optional[str]) -> Optional[str]:
    if not token:
        return token
    text = token.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def display_label(label: Optional[str]) -> Optional[str]:
    """'tomato___early_blight' -> 'Tomato — Early blight'."""
    plant, condition = split_label(label)
    if plant and condition:
        return f"{humanize(plant)} — {humanize(condition)}"
    return humanize(condition)


def is_healthy_label(label: Optional[str]) -> bool:
    return bool(label) and label.endswith("___healthy")
