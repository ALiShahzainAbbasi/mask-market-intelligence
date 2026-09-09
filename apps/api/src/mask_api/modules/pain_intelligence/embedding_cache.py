"""Immutable local artifact cache for versioned mention embeddings."""

from __future__ import annotations

import hashlib

from pydantic import ValidationError

from mask_api.modules.pain_intelligence.contracts import (
    EmbeddingCacheRecord,
    EmbeddingItem,
    EmbeddingVector,
)
from mask_api.research_runner.artifacts import ArtifactKind, ArtifactStoreError
from mask_api.research_runner.ports import ArtifactStore


class EmbeddingCacheError(RuntimeError):
    """An embedding cache artifact could not be trusted."""


def embedding_identity(
    input_sha256: str,
    *,
    provider: str,
    model_reference: str,
    embedding_version: str,
    dimensions: int,
) -> str:
    value = "\x1f".join(
        (provider, model_reference, embedding_version, str(dimensions), input_sha256)
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ArtifactEmbeddingCache:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts
        self._known_paths: set[str] | None = None

    def get(
        self,
        item: EmbeddingItem,
        *,
        provider: str,
        model_reference: str,
        embedding_version: str,
        dimensions: int,
    ) -> EmbeddingVector | None:
        identity = embedding_identity(
            item.input_sha256,
            provider=provider,
            model_reference=model_reference,
            embedding_version=embedding_version,
            dimensions=dimensions,
        )
        path = f"embeddings/{identity[:24]}/{item.mention_id[:24]}.json"
        try:
            if path not in self._paths():
                return None
            payload = self._artifacts.read_bytes(ArtifactKind.CACHE, path)
        except ArtifactStoreError as error:
            raise EmbeddingCacheError("embedding cache could not be read") from error
        try:
            vector = EmbeddingCacheRecord.model_validate_json(payload).vector
        except ValidationError as error:
            raise EmbeddingCacheError("embedding cache record is invalid") from error
        if (
            vector.mention_id != item.mention_id
            or vector.input_sha256 != item.input_sha256
            or vector.provider != provider
            or vector.model_reference != model_reference
            or vector.embedding_version != embedding_version
            or vector.dimensions != dimensions
        ):
            raise EmbeddingCacheError("embedding cache identity does not match its request")
        return vector

    def put(self, vector: EmbeddingVector) -> None:
        identity = embedding_identity(
            vector.input_sha256,
            provider=vector.provider,
            model_reference=vector.model_reference,
            embedding_version=vector.embedding_version,
            dimensions=vector.dimensions,
        )
        path = f"embeddings/{identity[:24]}/{vector.mention_id[:24]}.json"
        record = EmbeddingCacheRecord(vector=vector)
        try:
            self._artifacts.write_bytes(
                ArtifactKind.CACHE,
                path,
                record.model_dump_json(indent=2).encode("utf-8") + b"\n",
            )
            self._paths().add(path)
        except ArtifactStoreError as error:
            raise EmbeddingCacheError("embedding cache record could not be written") from error

    def _paths(self) -> set[str]:
        if self._known_paths is None:
            try:
                self._known_paths = {
                    receipt.relative_path
                    for receipt in self._artifacts.list_artifacts(ArtifactKind.CACHE)
                }
            except ArtifactStoreError as error:
                raise EmbeddingCacheError("embedding cache could not be listed") from error
        return self._known_paths
