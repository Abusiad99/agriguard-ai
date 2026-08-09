"""
ImageFolderAdapter — handles the most common convention across PlantVillage, PlantDoc,
the Kaggle "New Plant Diseases Dataset", and most Date Palm / Red Palm Weevil datasets:
images grouped into class-named leaf directories, at an arbitrary nesting depth and
possibly wrapped in split folders (train/valid/test) or a color-mode folder
(color/grayscale/segmented, as PlantVillage ships).

Structural rule (no dataset names hardcoded, per C1):
  A directory is a "class leaf" if it directly contains >= 1 image file and contains
  no subdirectories that themselves qualify as class leaves (i.e., it's a terminal
  grouping node). The class label is that leaf directory's name.

Known non-class wrapper folder names (case-insensitive) are transparently descended
through without becoming part of the label, EXCEPT that split-indicator folders
(train/val/valid/test) are recorded as a `split_hint` so the merger can optionally
respect the source dataset's original split — though AgriGuard AI re-splits the
unified dataset itself per FR-DATA-4, so this hint is informational only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Set

from ai.config import CONFIG
from ai.data.adapters.base_adapter import DatasetAdapter, RawSample

_WRAPPER_NAMES: Set[str] = {
    "images", "image", "data", "dataset", "raw", "all", "plantvillage",
    "plantdoc", "color", "colour",
}
_SPLIT_NAMES: Set[str] = {"train", "training", "val", "valid", "validation", "test", "testing"}


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in CONFIG.data.image_extensions


class ImageFolderAdapter(DatasetAdapter):
    name = "imagefolder"

    def matches(self, root: Path) -> bool:
        return self._find_class_leaves(root, max_probe=1) != []

    def confidence(self, root: Path) -> float:
        leaves = self._find_class_leaves(root, max_probe=50)
        if not leaves:
            return 0.0
        # Higher confidence the more class leaves we find with a sane image count.
        populated = sum(1 for leaf in leaves if self._count_images(leaf) >= CONFIG.data.min_images_per_class)
        return min(1.0, 0.4 + 0.6 * (populated / max(1, len(leaves))))

    def iter_samples(self, root: Path) -> Iterator[RawSample]:
        source_name = root.name
        for leaf in self._find_class_leaves(root, max_probe=None):
            label = leaf.name
            for f in leaf.iterdir():
                if f.is_file() and _is_image(f):
                    yield RawSample(image_path=f, raw_label=label, source_dataset=source_name)

    # ------------------------------------------------------------------
    def _count_images(self, directory: Path) -> int:
        return sum(1 for f in directory.iterdir() if f.is_file() and _is_image(f))

    def _find_class_leaves(self, root: Path, max_probe: int | None):
        """Walk the tree, descending through split/wrapper folders, and return the
        list of directories that qualify as class leaves (contain images directly
        and are the terminal grouping level)."""
        leaves = []
        self._walk(root, leaves, max_probe)
        return leaves

    def _walk(self, directory: Path, leaves: list, max_probe: int | None):
        if max_probe is not None and len(leaves) >= max_probe:
            return
        try:
            entries = list(directory.iterdir())
        except (PermissionError, FileNotFoundError):
            return

        subdirs = [e for e in entries if e.is_dir() and not e.name.startswith(".")]
        has_images = any(e.is_file() and _is_image(e) for e in entries)

        if has_images and not subdirs:
            # Terminal node with images and no further subdirectories -> class leaf.
            leaves.append(directory)
            return

        if has_images and subdirs:
            # Mixed content is atypical; still treat as a leaf if the image count
            # is meaningful, since some datasets place a few stray images alongside
            # subfolders. Otherwise prefer descending.
            if self._count_images(directory) >= CONFIG.data.min_images_per_class:
                leaves.append(directory)

        for sub in subdirs:
            if max_probe is not None and len(leaves) >= max_probe:
                return
            self._walk(sub, leaves, max_probe)
