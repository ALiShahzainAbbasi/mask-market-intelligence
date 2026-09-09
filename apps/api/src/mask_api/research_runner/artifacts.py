"""Immutable contracts for research-run artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactKind(StrEnum):
    CACHE = "cache"
    RAW = "raw"
    NORMALIZED = "normalized"
    EVIDENCE = "evidence"
    METRICS = "metrics"
    REPORTS = "reports"
    MANIFESTS = "manifests"
    LINEAGE = "lineage"
    LOGS = "logs"


@dataclass(frozen=True)
class ArtifactLimits:
    max_artifacts: int = 10_000
    max_file_bytes: int = 10 * 1024 * 1024
    max_run_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_artifacts < 1:
            raise ValueError("max_artifacts must be positive")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        if self.max_run_bytes < self.max_file_bytes:
            raise ValueError("max_run_bytes must be at least max_file_bytes")


@dataclass(frozen=True)
class ArtifactReceipt:
    kind: ArtifactKind
    relative_path: str
    sha256: str
    size_bytes: int
    already_present: bool = False


class ArtifactStoreError(RuntimeError):
    """Base class for safe artifact persistence failures."""


class UnsafeArtifactPath(ArtifactStoreError):
    """An artifact name could escape or abuse the selected run directory."""


class ArtifactConflict(ArtifactStoreError):
    """An immutable artifact already exists with different content."""


class ArtifactLimitExceeded(ArtifactStoreError):
    """An artifact write would exceed a configured hard limit."""
