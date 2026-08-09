"""
DatasetScanner — top-level discovery entry point (FR-DATA-1).

Scans `CONFIG.paths.datasets_dir` for candidate dataset folders (any immediate
subdirectory is treated as one dataset "family", matching how a user would extract
PlantVillage/PlantDoc/etc. as separate folders), resolves an adapter per folder via
AdapterRegistry, and produces a pre-flight audit so `train.py` can fail fast with an
actionable message (C2) instead of crashing deep inside training.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List

from ai.config import CONFIG
from ai.data.adapters.adapter_registry import AdapterRegistry
from ai.data.adapters.base_adapter import RawSample

logger = logging.getLogger("agriguard.data.scanner")


@dataclass
class DatasetAuditEntry:
    dataset_name: str
    path: Path
    adapter_name: str | None
    sample_count: int
    class_count: int


@dataclass
class DatasetAudit:
    entries: List[DatasetAuditEntry] = field(default_factory=list)

    @property
    def total_samples(self) -> int:
        return sum(e.sample_count for e in self.entries)

    @property
    def usable_entries(self) -> List[DatasetAuditEntry]:
        return [e for e in self.entries if e.adapter_name is not None and e.sample_count > 0]

    def report(self) -> str:
        lines = ["Dataset Audit Report", "=" * 60]
        if not self.entries:
            lines.append("No subdirectories found under datasets/.")
        for e in self.entries:
            status = f"adapter={e.adapter_name}, samples={e.sample_count}, classes={e.class_count}" \
                if e.adapter_name else "NO MATCHING ADAPTER — skipped"
            lines.append(f"  [{e.dataset_name}] -> {status}")
        lines.append("-" * 60)
        lines.append(f"Total usable datasets: {len(self.usable_entries)} / {len(self.entries)}")
        lines.append(f"Total usable samples:  {self.total_samples}")
        return "\n".join(lines)


class DatasetScanner:
    def __init__(self, datasets_dir: Path | None = None, registry: AdapterRegistry | None = None):
        self.datasets_dir = datasets_dir or CONFIG.paths.datasets_dir
        self.registry = registry or AdapterRegistry()

    def discover_dataset_roots(self) -> List[Path]:
        """Every immediate subdirectory of datasets/ is a candidate dataset family."""
        if not self.datasets_dir.exists():
            return []
        return sorted(
            p for p in self.datasets_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    def audit(self) -> DatasetAudit:
        audit = DatasetAudit()
        for root in self.discover_dataset_roots():
            adapter = self.registry.select_adapter(root)
            if adapter is None:
                audit.entries.append(DatasetAuditEntry(root.name, root, None, 0, 0))
                continue
            samples = list(adapter.iter_samples(root))
            classes = {s.raw_label for s in samples}
            audit.entries.append(
                DatasetAuditEntry(root.name, root, adapter.name, len(samples), len(classes))
            )
        return audit

    def iter_all_samples(self) -> Iterator[RawSample]:
        for root in self.discover_dataset_roots():
            yield from self.registry.iter_samples_for_dataset(root)

    def preflight_check(self) -> DatasetAudit:
        """Raise a clear, actionable error if datasets/ has nothing usable (C2)."""
        roots = self.discover_dataset_roots()
        if not roots:
            raise RuntimeError(
                f"No dataset folders found under '{self.datasets_dir}'.\n"
                "Place one or more datasets (e.g. PlantVillage, PlantDoc, the Kaggle "
                "New Plant Diseases Dataset, IP102, a Date Palm Disease dataset, a Red "
                "Palm Weevil dataset) as subfolders of 'datasets/' and re-run "
                "`python train.py`. Each subfolder may use any internal structure "
                "(class-per-folder, or images + a CSV/JSON/XML annotation file)."
            )
        audit = self.audit()
        if not audit.usable_entries:
            raise RuntimeError(
                "Found dataset folder(s) under 'datasets/' but none matched a "
                "recognizable structure (class-labeled subfolders, or images with a "
                "CSV/JSON/XML annotation file).\n\n" + audit.report()
            )
        logger.info("\n%s", audit.report())
        return audit
