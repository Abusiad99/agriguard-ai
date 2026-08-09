"""
CsvAnnotationAdapter — handles datasets that ship a flat image directory plus a CSV
annotation file mapping filenames to labels (a pattern used by several Kaggle plant
pest/disease redistributions and by some IP102 mirrors).

Structural detection: any `.csv` file under `root` (at any depth) that has at least
two columns where one is plausibly a filename/path column (contains an image
extension in its values) and another is plausibly a label column.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator, Optional

from ai.config import CONFIG
from ai.data.adapters.base_adapter import DatasetAdapter, RawSample

_FILENAME_COL_CANDIDATES = {"filename", "file_name", "file", "image", "image_name", "path", "img_path"}
_LABEL_COL_CANDIDATES = {"label", "class", "category", "disease", "diagnosis", "class_name", "target"}


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in CONFIG.data.image_extensions


class CsvAnnotationAdapter(DatasetAdapter):
    name = "csv_annotation"

    def matches(self, root: Path) -> bool:
        return self._find_annotation_csv(root) is not None

    def confidence(self, root: Path) -> float:
        csv_path = self._find_annotation_csv(root)
        if csv_path is None:
            return 0.0
        try:
            rows = self._read_rows(csv_path)
        except Exception:
            return 0.0
        return 0.7 if len(rows) >= CONFIG.data.min_images_per_class else 0.3

    def iter_samples(self, root: Path) -> Iterator[RawSample]:
        source_name = root.name
        csv_path = self._find_annotation_csv(root)
        if csv_path is None:
            return
        filename_col, label_col = self._detect_columns(csv_path)
        if filename_col is None or label_col is None:
            return

        image_index = self._index_images(root)

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_name = (row.get(filename_col) or "").strip()
                label = (row.get(label_col) or "").strip()
                if not raw_name or not label:
                    continue
                image_path = self._resolve_image(raw_name, csv_path.parent, image_index)
                if image_path is not None:
                    yield RawSample(image_path=image_path, raw_label=label, source_dataset=source_name)

    # ------------------------------------------------------------------
    def _find_annotation_csv(self, root: Path) -> Optional[Path]:
        for path in root.rglob("*.csv"):
            filename_col, label_col = self._detect_columns(path)
            if filename_col and label_col:
                return path
        return None

    def _detect_columns(self, csv_path: Path):
        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = [h.strip().lower() for h in (reader.fieldnames or [])]
                first_rows = []
                for i, row in enumerate(reader):
                    first_rows.append(row)
                    if i >= 20:
                        break
        except Exception:
            return None, None

        header_map = {h.strip().lower(): h.strip() for h in (headers or [])}
        filename_col = next((header_map[h] for h in _FILENAME_COL_CANDIDATES if h in header_map), None)
        label_col = next((header_map[h] for h in _LABEL_COL_CANDIDATES if h in header_map), None)

        # Fallback: if no exact header match, sniff by content (values look like image paths).
        if filename_col is None and first_rows:
            for h in headers:
                orig = header_map.get(h, h)
                sample_vals = [str(r.get(orig, "")) for r in first_rows[:5]]
                if any(_is_image(v) for v in sample_vals):
                    filename_col = orig
                    break
        return filename_col, label_col

    def _read_rows(self, csv_path: Path):
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def _index_images(self, root: Path) -> dict:
        """Map basename -> full path for fast lookup, since CSVs often store only
        the bare filename while images live in an arbitrarily nested subfolder."""
        index = {}
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in CONFIG.data.image_extensions:
                index[f.name] = f
        return index

    def _resolve_image(self, raw_name: str, csv_dir: Path, image_index: dict) -> Optional[Path]:
        candidate = (csv_dir / raw_name)
        if candidate.is_file():
            return candidate
        basename = Path(raw_name).name
        return image_index.get(basename)
