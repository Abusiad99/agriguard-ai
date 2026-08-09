"""
JsonAnnotationAdapter — handles two common JSON annotation conventions:

1. COCO-style: {"images": [{"id":..,"file_name":..}], "annotations": [{"image_id":..,
   "category_id":..}], "categories": [{"id":..,"name":..}]}
2. Simple list-of-records: [{"file_name": "...", "label": "..."}, ...] or a dict
   keyed by filename -> label.

Used for datasets like some IP102 mirrors that ship JSON rather than XML/CSV.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from ai.config import CONFIG
from ai.data.adapters.base_adapter import DatasetAdapter, RawSample


class JsonAnnotationAdapter(DatasetAdapter):
    name = "json_annotation"

    def matches(self, root: Path) -> bool:
        return self._find_annotation_json(root) is not None

    def confidence(self, root: Path) -> float:
        return 0.6 if self._find_annotation_json(root) is not None else 0.0

    def iter_samples(self, root: Path) -> Iterator[RawSample]:
        source_name = root.name
        json_path = self._find_annotation_json(root)
        if json_path is None:
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        image_index = self._index_images(root)

        if isinstance(data, dict) and "images" in data and "annotations" in data:
            yield from self._iter_coco(data, json_path.parent, image_index, source_name)
        elif isinstance(data, list):
            yield from self._iter_list(data, json_path.parent, image_index, source_name)
        elif isinstance(data, dict):
            yield from self._iter_dict(data, json_path.parent, image_index, source_name)

    # ------------------------------------------------------------------
    def _find_annotation_json(self, root: Path) -> Optional[Path]:
        for path in root.rglob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict) and "images" in data and "annotations" in data and "categories" in data:
                return path
            if isinstance(data, list) and data and isinstance(data[0], dict) and (
                any(k in data[0] for k in ("file_name", "filename", "image"))
            ):
                return path
            if isinstance(data, dict) and data and isinstance(next(iter(data.values())), str):
                return path
        return None

    def _index_images(self, root: Path) -> dict:
        index = {}
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in CONFIG.data.image_extensions:
                index[f.name] = f
        return index

    def _resolve(self, raw_name: str, base_dir: Path, image_index: dict) -> Optional[Path]:
        candidate = base_dir / raw_name
        if candidate.is_file():
            return candidate
        return image_index.get(Path(raw_name).name)

    def _iter_coco(self, data: dict, base_dir: Path, image_index: dict, source_name: str) -> Iterator[RawSample]:
        cat_id_to_name = {c["id"]: c["name"] for c in data.get("categories", [])}
        img_id_to_file = {img["id"]: img.get("file_name") or img.get("filename") for img in data.get("images", [])}
        for ann in data.get("annotations", []):
            file_name = img_id_to_file.get(ann.get("image_id"))
            label = cat_id_to_name.get(ann.get("category_id"))
            if not file_name or not label:
                continue
            path = self._resolve(file_name, base_dir, image_index)
            if path is not None:
                yield RawSample(image_path=path, raw_label=str(label), source_dataset=source_name)

    def _iter_list(self, data: list, base_dir: Path, image_index: dict, source_name: str) -> Iterator[RawSample]:
        for record in data:
            file_name = record.get("file_name") or record.get("filename") or record.get("image")
            label = record.get("label") or record.get("class") or record.get("category")
            if not file_name or not label:
                continue
            path = self._resolve(str(file_name), base_dir, image_index)
            if path is not None:
                yield RawSample(image_path=path, raw_label=str(label), source_dataset=source_name)

    def _iter_dict(self, data: dict, base_dir: Path, image_index: dict, source_name: str) -> Iterator[RawSample]:
        for file_name, label in data.items():
            if not isinstance(label, str):
                continue
            path = self._resolve(file_name, base_dir, image_index)
            if path is not None:
                yield RawSample(image_path=path, raw_label=label, source_dataset=source_name)
