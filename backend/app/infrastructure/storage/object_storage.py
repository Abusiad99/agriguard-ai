"""
IObjectStorage — abstraction over where uploaded images, heatmaps, and generated PDF
reports are persisted (FR-REPORT, FR-SCAN). `LocalObjectStorage` is the default
(bind-mounted Docker volume); an S3-compatible implementation can be substituted
without touching any calling code, per Dependency Inversion (NFR-MAINT-2).
"""
from __future__ import annotations

import abc
import shutil
import uuid
from pathlib import Path


class IObjectStorage(abc.ABC):
    @abc.abstractmethod
    def save_bytes(self, data: bytes, relative_path: str) -> str:
        """Persist raw bytes, return a storage reference (path/key)."""
        ...

    @abc.abstractmethod
    def save_file(self, source_path: Path, relative_path: str) -> str:
        ...

    @abc.abstractmethod
    def read_bytes(self, ref: str) -> bytes: ...

    @abc.abstractmethod
    def resolve_path(self, ref: str) -> Path:
        """Return a local filesystem path usable for streaming a response."""
        ...

    @abc.abstractmethod
    def exists(self, ref: str) -> bool: ...


class LocalObjectStorage(IObjectStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _full_path(self, relative_path: str) -> Path:
        full = (self.base_dir / relative_path).resolve()
        if not str(full).startswith(str(self.base_dir.resolve())):
            raise ValueError("Path traversal detected in storage reference.")
        return full

    def save_bytes(self, data: bytes, relative_path: str) -> str:
        full = self._full_path(relative_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return relative_path

    def save_file(self, source_path: Path, relative_path: str) -> str:
        full = self._full_path(relative_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, full)
        return relative_path

    def read_bytes(self, ref: str) -> bytes:
        return self._full_path(ref).read_bytes()

    def resolve_path(self, ref: str) -> Path:
        return self._full_path(ref)

    def exists(self, ref: str) -> bool:
        return self._full_path(ref).exists()


def generate_storage_key(prefix: str, extension: str) -> str:
    return f"{prefix}/{uuid.uuid4().hex}.{extension.lstrip('.')}"
