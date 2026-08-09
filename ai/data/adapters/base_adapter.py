"""
Base interface for dataset adapters.

An adapter's job: given a directory that has been fingerprinted as matching a
particular structural pattern, yield (image_path, raw_label) pairs. Adapters know
NOTHING about which dataset family they belong to by name — they only recognize
STRUCTURE (folder layout, presence of annotation files). This is what makes dataset
discovery automatic and name-agnostic (C1, FR-DATA-1/2).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class RawSample:
    """A single (image, label-as-written-in-the-source-dataset) pair before normalization."""

    image_path: Path
    raw_label: str
    source_dataset: str  # name of the top-level folder under datasets/, for provenance/logging


class DatasetAdapter(abc.ABC):
    """Contract every adapter must satisfy."""

    #: Human-readable adapter name, used in logs and the pre-flight audit report.
    name: str = "base"

    @abc.abstractmethod
    def matches(self, root: Path) -> bool:
        """Return True if this adapter's structural pattern is detected under `root`.

        Implementations must be side-effect-free and fast (only stat/list files,
        never load full images) since `matches` is called by the registry against
        every candidate adapter for every discovered dataset folder.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def iter_samples(self, root: Path) -> Iterator[RawSample]:
        """Yield every (image, raw_label) pair found under `root`."""
        raise NotImplementedError

    def confidence(self, root: Path) -> float:
        """Optional: how confident is this adapter it is the *best* match (0..1).

        Used by the registry to break ties when multiple adapters' `matches()`
        return True for the same folder (e.g., a folder that has both class
        subfolders AND a stray CSV). Default implementation returns 0.5 for any
        match; adapters that want priority should override this.
        """
        return 0.5 if self.matches(root) else 0.0
