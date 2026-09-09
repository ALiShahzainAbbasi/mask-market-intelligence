"""Application service composing the offline M2 pain pipeline."""

from __future__ import annotations

from mask_api.modules.pain_intelligence.clustering import cluster_mentions
from mask_api.modules.pain_intelligence.contracts import (
    ClusteringConfiguration,
    M2Result,
    PainContradiction,
    PainMention,
)
from mask_api.modules.pain_intelligence.deduplication import (
    exact_deduplicate,
    near_deduplicate,
)
from mask_api.modules.pain_intelligence.embeddings import EmbeddingService
from mask_api.modules.pain_intelligence.metrics import calculate_m2
from mask_api.research_runner.budgets import BudgetLedger
from mask_api.research_runner.contracts import MethodFormula


class PainIntelligenceService:
    def __init__(
        self,
        embeddings: EmbeddingService,
        clustering: ClusteringConfiguration,
    ) -> None:
        self._embeddings = embeddings
        self._clustering = clustering

    def run(
        self,
        *,
        market_id: str,
        formula_version: str,
        formula: MethodFormula,
        all_relevant_unique_documents: int,
        mentions: tuple[PainMention, ...],
        ledger: BudgetLedger,
        contradictions: tuple[PainContradiction, ...] = (),
    ) -> M2Result:
        exact = exact_deduplicate(mentions)
        vectors = self._embeddings.embed_mentions(exact.retained_mentions, ledger)
        near = near_deduplicate(
            exact.retained_mentions,
            vectors,
            threshold=self._clustering.near_duplicate_threshold,
        )
        retained_ids = {item.mention_id for item in near.retained_mentions}
        retained_vectors = tuple(item for item in vectors if item.mention_id in retained_ids)
        clustering = cluster_mentions(near.retained_mentions, retained_vectors, self._clustering)
        return calculate_m2(
            market_id=market_id,
            formula_version=formula_version,
            formula=formula,
            all_relevant_unique_documents=all_relevant_unique_documents,
            input_mentions=mentions,
            retained_mentions=near.retained_mentions,
            duplicate_links=(*exact.links, *near.links),
            clustering=clustering,
            contradictions=contradictions,
        )
