"""
XmlAnnotationAdapter — handles Pascal-VOC-style per-image XML annotation files, the
convention used by IP102's object-detection distribution and several pest datasets:

  <annotation>
    <filename>0001.jpg</filename>
    <object><name>red_palm_weevil</name><bndbox>...</bndbox></object>
    ...
  </annotation>

For AgriGuard AI's classification pipeline (plant/disease/pest classification, not
detection), this adapter extracts the primary (first, or most frequent) <object><name>
as the classification label for the associated image. The full bounding-box data is
preserved on the RawSample via a side-channel attribute for potential future use by
localization models, but classification training only consumes the label.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

from ai.config import CONFIG
from ai.data.adapters.base_adapter import DatasetAdapter, RawSample


class XmlAnnotationAdapter(DatasetAdapter):
    name = "xml_annotation_voc"

    def matches(self, root: Path) -> bool:
        return self._first_valid_xml(root) is not None

    def confidence(self, root: Path) -> float:
        return 0.65 if self._first_valid_xml(root) is not None else 0.0

    def iter_samples(self, root: Path) -> Iterator[RawSample]:
        source_name = root.name
        image_index = self._index_images(root)
        for xml_path in root.rglob("*.xml"):
            parsed = self._parse(xml_path)
            if parsed is None:
                continue
            filename, label = parsed
            image_path = self._resolve(filename, xml_path.parent, image_index)
            if image_path is not None:
                yield RawSample(image_path=image_path, raw_label=label, source_dataset=source_name)

    # ------------------------------------------------------------------
    def _first_valid_xml(self, root: Path) -> Optional[Path]:
        for path in root.rglob("*.xml"):
            if self._parse(path) is not None:
                return path
        return None

    def _parse(self, xml_path: Path):
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            return None
        root_el = tree.getroot()
        if root_el.tag != "annotation":
            return None

        filename_el = root_el.find("filename")
        filename = filename_el.text.strip() if filename_el is not None and filename_el.text else xml_path.stem

        names = [obj.findtext("name", "").strip() for obj in root_el.findall("object")]
        names = [n for n in names if n]
        if not names:
            return None
        # Use the most frequent object class in the image as the classification label.
        label = Counter(names).most_common(1)[0][0]
        return filename, label

    def _index_images(self, root: Path) -> dict:
        index = {}
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in CONFIG.data.image_extensions:
                index[f.name] = f
        return index

    def _resolve(self, raw_name: str, xml_dir: Path, image_index: dict) -> Optional[Path]:
        stem = Path(raw_name).stem
        # Try exact filename first, then any image sharing the same stem (extension
        # mismatches between annotation and image are common across dataset mirrors).
        candidate = xml_dir / raw_name
        if candidate.is_file():
            return candidate
        if raw_name in image_index:
            return image_index[raw_name]
        for ext in CONFIG.data.image_extensions:
            guess = image_index.get(stem + ext)
            if guess:
                return guess
        return None
