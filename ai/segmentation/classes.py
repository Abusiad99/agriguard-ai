"""
Class mapping for segmentation datasets and models (`class_mapping.json`).

Every class has a training id (contiguous from 0), a name, a kind and a display color:

  kind = "background"  pixels outside the plant/leaf
  kind = "leaf"        healthy plant/leaf tissue
  kind = "disease"     visibly affected tissue (one class per disease, or one generic class)

How raw annotations map onto training ids:
  source_values   raw mask pixel values (PNG masks) and YOLO class indices
  source_names    COCO category names
  ignore_values   raw mask values to exclude from loss and metrics (e.g. a "void" label)

Affected-area percentages need a valid denominator (leaf pixels). They are only
computed when the mapping has at least one "leaf" class, i.e. the dataset annotates
healthy tissue as well as lesions. A binary background/lesion dataset can localize
lesions but cannot say what fraction of the leaf they cover.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

IGNORE_INDEX = 255
KINDS = ("background", "leaf", "disease")


@dataclass
class SegClass:
    id: int
    name: str
    kind: str
    color: List[int]
    source_values: List[int] = field(default_factory=list)
    source_names: List[str] = field(default_factory=list)


@dataclass
class ClassMapping:
    classes: List[SegClass]
    ignore_values: List[int] = field(default_factory=list)
    version: int = 1

    # ------------------------------------------------------------------ queries
    @property
    def num_classes(self) -> int:
        return len(self.classes)

    @property
    def names(self) -> List[str]:
        return [c.name for c in self.classes]

    def ids_of(self, kind: str) -> List[int]:
        return [c.id for c in self.classes if c.kind == kind]

    @property
    def background_id(self) -> int:
        return self.ids_of("background")[0]

    @property
    def disease_ids(self) -> List[int]:
        return self.ids_of("disease")

    @property
    def leaf_ids(self) -> List[int]:
        return self.ids_of("leaf")

    @property
    def has_leaf_annotation(self) -> bool:
        return bool(self.leaf_ids)

    def class_for_name(self, source_name: str) -> Optional[SegClass]:
        key = source_name.strip().lower()
        for c in self.classes:
            if key == c.name.lower() or key in (n.lower() for n in c.source_names):
                return c
        return None

    def class_for_value(self, value: int) -> Optional[SegClass]:
        for c in self.classes:
            if value in c.source_values:
                return c
        return None

    def value_lut(self) -> np.ndarray:
        """256-entry lookup table: raw mask value -> training id (IGNORE_INDEX for
        ignore values). Unmapped values map to -1 so callers can detect them."""
        lut = np.full(256, -1, dtype=np.int16)
        for c in self.classes:
            for v in c.source_values:
                if 0 <= v <= 255:
                    lut[v] = c.id
        for v in self.ignore_values:
            lut[v] = IGNORE_INDEX
        return lut

    # ------------------------------------------------------------------ io
    @classmethod
    def from_dict(cls, data: dict) -> "ClassMapping":
        classes = [SegClass(id=int(c["id"]), name=str(c["name"]), kind=str(c["kind"]),
                            color=[int(x) for x in c.get("color", [255, 0, 0])][:3],
                            source_values=[int(v) for v in c.get("source_values", [])],
                            source_names=[str(n) for n in c.get("source_names", [])])
                   for c in data["classes"]]
        mapping = cls(classes=sorted(classes, key=lambda c: c.id),
                      ignore_values=[int(v) for v in data.get("ignore_values", [])],
                      version=int(data.get("version", 1)))
        mapping.check()
        return mapping

    @classmethod
    def load(cls, path: Path) -> "ClassMapping":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {"version": self.version, "ignore_values": self.ignore_values,
                "classes": [c.__dict__ for c in self.classes]}

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def check(self) -> None:
        """Raise ValueError for a mapping the pipeline can't use."""
        ids = [c.id for c in self.classes]
        if ids != list(range(len(ids))):
            raise ValueError(f"class ids must be contiguous from 0, got {ids}")
        bad = [c.name for c in self.classes if c.kind not in KINDS]
        if bad:
            raise ValueError(f"unknown class kind for {bad}; use one of {KINDS}")
        if len(self.ids_of("background")) != 1:
            raise ValueError("exactly one class must have kind 'background'")
        if not self.disease_ids:
            raise ValueError("at least one class must have kind 'disease'")
        if len(self.classes) >= IGNORE_INDEX:
            raise ValueError("too many classes")
        seen: Dict[int, str] = {}
        for c in self.classes:
            for v in c.source_values:
                if v in seen:
                    raise ValueError(f"source value {v} is mapped to both {seen[v]} and {c.name}")
                seen[v] = c.name
        overlap = set(seen) & set(self.ignore_values)
        if overlap:
            raise ValueError(f"values {sorted(overlap)} are both mapped and ignored")
