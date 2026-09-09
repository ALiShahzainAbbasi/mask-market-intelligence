"""Narrow ports used by the research-run application layer."""

from __future__ import annotations

from typing import Protocol

from mask_api.research_runner.artifacts import ArtifactKind, ArtifactReceipt


class ArtifactStore(Protocol):
    def write_bytes(
        self, kind: ArtifactKind, relative_path: str, content: bytes
    ) -> ArtifactReceipt: ...

    def read_bytes(self, kind: ArtifactKind, relative_path: str) -> bytes: ...

    def list_artifacts(self, kind: ArtifactKind | None = None) -> tuple[ArtifactReceipt, ...]: ...
