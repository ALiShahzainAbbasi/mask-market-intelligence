"""Narrow embedding and cache ports for pain intelligence."""

from __future__ import annotations

from typing import Protocol

from mask_api.modules.pain_intelligence.contracts import (
    EmbeddingItem,
    EmbeddingRequest,
    EmbeddingVector,
)
from mask_api.research_runner.budgets import BudgetLedger


class EmbeddingProvider(Protocol):
    def embed(
        self,
        request: EmbeddingRequest,
        ledger: BudgetLedger,
    ) -> tuple[EmbeddingVector, ...]: ...


class EmbeddingCache(Protocol):
    def get(
        self,
        item: EmbeddingItem,
        *,
        provider: str,
        model_reference: str,
        embedding_version: str,
        dimensions: int,
    ) -> EmbeddingVector | None: ...

    def put(self, vector: EmbeddingVector) -> None: ...
