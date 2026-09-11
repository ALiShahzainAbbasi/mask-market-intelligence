"""A small local filesystem cache for the one shared O*NET database archive.

This is deliberately not `research_runner.ports.ArtifactStore`: that store's
raw/normalized/evidence/metrics/reports/manifests/lineage/logs layout and
per-run root are shaped for one research run's output tree. The O*NET
archive is a single static reference dataset shared across every run, so it
gets its own narrow, purpose-built cache instead of stretching a per-run
store to fit a cross-run concern.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from mask_api.modules.onet_data.contracts import OnetDatasetDescriptor

_DESCRIPTOR_FILENAME = "dataset_descriptor.json"


class OnetCacheError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("O*NET cache could not be read or written safely")


class OnetCache(Protocol):
    def read_descriptor(self) -> OnetDatasetDescriptor | None: ...

    def read_archive(self, archive_filename: str) -> bytes: ...

    def write(self, descriptor: OnetDatasetDescriptor, archive_bytes: bytes) -> None: ...


class LocalOnetCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def read_descriptor(self) -> OnetDatasetDescriptor | None:
        path = self._cache_dir / _DESCRIPTOR_FILENAME
        if not path.is_file():
            return None
        try:
            return OnetDatasetDescriptor.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, ValueError) as error:
            raise OnetCacheError("onet.cache_descriptor_corrupt") from error

    def read_archive(self, archive_filename: str) -> bytes:
        path = self._safe_archive_path(archive_filename)
        try:
            return path.read_bytes()
        except OSError as error:
            raise OnetCacheError("onet.cache_archive_unreadable") from error

    def write(self, descriptor: OnetDatasetDescriptor, archive_bytes: bytes) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self._safe_archive_path(descriptor.archive_filename)
        descriptor_path = self._cache_dir / _DESCRIPTOR_FILENAME
        try:
            _atomic_write(archive_path, archive_bytes)
            _atomic_write(
                descriptor_path,
                descriptor.model_dump_json(indent=2).encode("utf-8"),
            )
        except OSError as error:
            raise OnetCacheError("onet.cache_write_failed") from error

    def _safe_archive_path(self, archive_filename: str) -> Path:
        candidate = self._cache_dir / archive_filename
        if candidate.parent.resolve() != self._cache_dir.resolve():
            raise OnetCacheError("onet.cache_path_invalid")
        return candidate


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
