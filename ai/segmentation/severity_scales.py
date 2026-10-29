"""
Crop/disease-specific severity scales.

Mapping "% visible affected leaf area" to mild / moderate / severe is only meaningful
with a documented, crop-appropriate scale (e.g. a published standard area diagram
or an extension-service rating scale) — and even then a single photo is not a field
assessment. No such scale has been validated for this project, so the registry below
is EMPTY by default and `categorize_severity` returns
{"level": None, "basis": "no_validated_scale"}; the UI then shows only the measured
percentage and explains that categories require calibration.

To add a scale, operators supply a JSON file via AGRIGUARD_SEVERITY_SCALES_FILE:

    {
      "tomato___early_blight": {
        "source": "<citation of the published scale>",
        "bands": [{"max_pct": 5, "level": "mild"},
                  {"max_pct": 25, "level": "moderate"},
                  {"max_pct": 100, "level": "severe"}]
      }
    }

Keys are canonical labels ("plant___condition") or a bare plant name ("tomato") to
apply a plant-wide scale. Every entry MUST carry a "source"; entries without one are
rejected at load time.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("agriguard.segmentation.severity")

_ALLOWED_LEVELS = {"mild", "moderate", "severe"}


@lru_cache(maxsize=1)
def load_scales() -> Dict[str, dict]:
    path = os.environ.get("AGRIGUARD_SEVERITY_SCALES_FILE", "")
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        logger.warning("AGRIGUARD_SEVERITY_SCALES_FILE=%s does not exist; no severity scales loaded.", path)
        return {}
    raw = json.loads(p.read_text())
    scales = {}
    for key, entry in raw.items():
        bands = entry.get("bands") or []
        if not entry.get("source"):
            logger.warning("Severity scale '%s' has no source citation and was ignored.", key)
            continue
        if not bands or any(b.get("level") not in _ALLOWED_LEVELS for b in bands):
            logger.warning("Severity scale '%s' has invalid bands and was ignored.", key)
            continue
        scales[key.lower()] = {"source": entry["source"],
                               "bands": sorted(bands, key=lambda b: float(b["max_pct"]))}
    return scales


def categorize_severity(affected_pct: float, *, plant: Optional[str] = None,
                        condition: Optional[str] = None) -> dict:
    scales = load_scales()
    keys = []
    if plant and condition:
        keys.append(f"{plant}___{condition}".lower())
    if plant:
        keys.append(plant.lower())
    for key in keys:
        scale = scales.get(key)
        if scale:
            for band in scale["bands"]:
                if affected_pct <= float(band["max_pct"]):
                    return {"level": band["level"], "basis": "configured_scale",
                            "scale_key": key, "source": scale["source"]}
    return {"level": None, "basis": "no_validated_scale"}
