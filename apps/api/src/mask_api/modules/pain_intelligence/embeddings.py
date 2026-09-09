"""Bounded embedding coordination and zero-cost local lexical adapter."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from mask_api.modules.pain_intelligence.contracts import (
    EmbeddingItem,
    EmbeddingRequest,
    EmbeddingVector,
    PainMention,
)
from mask_api.modules.pain_intelligence.ports import EmbeddingCache, EmbeddingProvider
from mask_api.research_runner.budgets import BudgetLedger

LOCAL_HASHING_PROVIDER = "local_hashing"
LOCAL_HASHING_MODEL = "mask-lexical-hashing"
LOCAL_HASHING_VERSION = "v1"

_TOKEN = re.compile(r"[a-z0-9]+")


class EmbeddingError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("pain embedding could not be completed safely")


class LocalHashingEmbeddingProvider:
    """Deterministic signed feature hashing; no network, model, or paid usage."""

    def embed(
        self,
        request: EmbeddingRequest,
        ledger: BudgetLedger,
    ) -> tuple[EmbeddingVector, ...]:
        if request.provider != LOCAL_HASHING_PROVIDER:
            raise EmbeddingError("embedding.provider_mismatch")
        if request.model_reference != LOCAL_HASHING_MODEL:
            raise EmbeddingError("embedding.model_mismatch")
        if request.embedding_version != LOCAL_HASHING_VERSION:
            raise EmbeddingError("embedding.version_unsupported")
        return tuple(_local_vector(item, request) for item in request.items)


class EmbeddingService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        cache: EmbeddingCache,
        *,
        provider_name: str,
        model_reference: str,
        embedding_version: str,
        dimensions: int,
        max_items: int = 1_000,
        max_total_characters: int = 1_000_000,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._provider_name = provider_name
        self._model_reference = model_reference
        self._embedding_version = embedding_version
        self._dimensions = dimensions
        self._max_items = max_items
        self._max_total_characters = max_total_characters

    def embed_mentions(
        self,
        mentions: tuple[PainMention, ...],
        ledger: BudgetLedger,
    ) -> tuple[EmbeddingVector, ...]:
        items = tuple(
            EmbeddingItem(
                mention_id=mention.mention_id,
                input_text=mention.normalized_pain_text,
                input_sha256=mention.normalized_pain_sha256,
            )
            for mention in sorted(mentions, key=lambda item: item.mention_id)
        )
        if not items:
            return ()
        cached: dict[str, EmbeddingVector] = {}
        missing: list[EmbeddingItem] = []
        for item in items:
            vector = self._cache.get(
                item,
                provider=self._provider_name,
                model_reference=self._model_reference,
                embedding_version=self._embedding_version,
                dimensions=self._dimensions,
            )
            if vector is None:
                missing.append(item)
            else:
                cached[item.mention_id] = vector
        if missing:
            request = EmbeddingRequest(
                provider=self._provider_name,
                model_reference=self._model_reference,
                embedding_version=self._embedding_version,
                dimensions=self._dimensions,
                max_items=self._max_items,
                max_total_characters=self._max_total_characters,
                items=tuple(missing),
            )
            produced = self._provider.embed(request, ledger)
            expected = {item.mention_id: item for item in missing}
            if len(produced) != len(expected) or {item.mention_id for item in produced} != set(
                expected
            ):
                raise EmbeddingError("embedding.response_items_mismatch")
            for vector in produced:
                source = expected[vector.mention_id]
                if (
                    vector.provider != request.provider
                    or vector.model_reference != request.model_reference
                    or vector.embedding_version != request.embedding_version
                    or vector.dimensions != request.dimensions
                    or vector.input_sha256 != source.input_sha256
                ):
                    raise EmbeddingError("embedding.response_lineage_mismatch")
                self._cache.put(vector)
                cached[vector.mention_id] = vector
        return tuple(cached[item.mention_id] for item in items)


def _local_vector(item: EmbeddingItem, request: EmbeddingRequest) -> EmbeddingVector:
    tokens = _TOKEN.findall(item.input_text)
    features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False)]
    counts = Counter(features or [item.input_text])
    values = [0.0] * request.dimensions
    for feature, count in sorted(counts.items()):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % request.dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        values[index] += sign * float(count)
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise EmbeddingError("embedding.local_zero_vector")
    normalized = tuple(value / norm for value in values)
    return EmbeddingVector(
        mention_id=item.mention_id,
        provider=request.provider,
        model_reference=request.model_reference,
        embedding_version=request.embedding_version,
        input_sha256=item.input_sha256,
        dimensions=request.dimensions,
        values=normalized,
    )
