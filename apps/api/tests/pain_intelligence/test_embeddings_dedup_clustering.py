from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from mask_api.modules.evidence.domain import EvidencePersona
from mask_api.modules.pain_intelligence.clustering import cluster_mentions
from mask_api.modules.pain_intelligence.contracts import (
    ClusteringConfiguration,
    EmbeddingRequest,
    EmbeddingVector,
    PainMention,
)
from mask_api.modules.pain_intelligence.deduplication import (
    exact_deduplicate,
    near_deduplicate,
)
from mask_api.modules.pain_intelligence.embedding_cache import ArtifactEmbeddingCache
from mask_api.modules.pain_intelligence.embeddings import (
    LOCAL_HASHING_MODEL,
    LOCAL_HASHING_PROVIDER,
    LOCAL_HASHING_VERSION,
    EmbeddingService,
    LocalHashingEmbeddingProvider,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.local_artifacts import LocalArtifactStore


def budget() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=0,
            max_documents=0,
            max_total_bytes=1_000_000,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0"),
        )
    )


def mention(seed: str, text: str, persona: EvidencePersona = EvidencePersona.OWNER) -> PainMention:
    normalized = text.casefold()
    return PainMention(
        mention_id=hashlib.sha256(seed.encode()).hexdigest(),
        market_id="us_hvac",
        document_id=f"doc-{seed}",
        normalized_document_sha256=hashlib.sha256(f"document-{seed}".encode()).hexdigest(),
        analysis_cache_key=hashlib.sha256(f"analysis-{seed}".encode()).hexdigest(),
        grounding_version="grounding-v1",
        source_family="approved_feed",
        persona=persona,
        source_date=date(2026, 9, 1),
        pain_category="missed_calls",
        pain_description=text,
        normalized_pain_text=normalized,
        normalized_pain_sha256=hashlib.sha256(normalized.encode()).hexdigest(),
        sentiment=-1,
        severity_1_10=5,
        economic_impact_types=(),
        economic_impact_1_10=5,
        purchase_intent_0_4=2,
        solution_dissatisfaction_1_10=5,
        software_mentioned=(),
        financial_values=(),
        evidence_span=text,
        extraction_confidence=Decimal("0.8"),
    )


@dataclass
class CountingLocalProvider:
    calls: int = 0

    def embed(self, request: EmbeddingRequest, ledger: BudgetLedger) -> tuple[EmbeddingVector, ...]:
        self.calls += 1
        return LocalHashingEmbeddingProvider().embed(request, ledger)


def test_local_embeddings_are_cached_and_require_no_network_budget(tmp_path: Path) -> None:
    provider = CountingLocalProvider()
    service = EmbeddingService(
        provider,
        ArtifactEmbeddingCache(LocalArtifactStore(tmp_path)),
        provider_name=LOCAL_HASHING_PROVIDER,
        model_reference=LOCAL_HASHING_MODEL,
        embedding_version=LOCAL_HASHING_VERSION,
        dimensions=64,
    )
    mentions = (mention("a", "missed calls lose revenue"),)

    first = service.embed_mentions(mentions, budget())
    second = service.embed_mentions(mentions, budget())

    assert first == second
    assert provider.calls == 1
    assert len(first[0].values) == 64


def test_exact_dedupe_never_merges_different_personas() -> None:
    owner = mention("a", "missed calls lose revenue", EvidencePersona.OWNER)
    duplicate = mention("b", "missed calls lose revenue", EvidencePersona.OWNER).model_copy(
        update={"normalized_document_sha256": owner.normalized_document_sha256}
    )
    employee = mention("c", "missed calls lose revenue", EvidencePersona.EMPLOYEE)

    result = exact_deduplicate((duplicate, employee, owner))

    assert len(result.retained_mentions) == 2
    assert len(result.links) == 1
    assert {item.persona for item in result.retained_mentions} == {
        EvidencePersona.OWNER,
        EvidencePersona.EMPLOYEE,
    }


def test_near_dedupe_uses_vectors_but_preserves_persona_boundary() -> None:
    owner_a = mention("a", "first owner wording", EvidencePersona.OWNER)
    owner_b = mention("b", "second owner wording", EvidencePersona.OWNER)
    employee = mention("c", "employee wording", EvidencePersona.EMPLOYEE)
    vectors = (
        vector(owner_a, (1.0, 0.0)),
        vector(owner_b, (1.0, 0.0)),
        vector(employee, (1.0, 0.0)),
    )

    result = near_deduplicate((owner_a, owner_b, employee), vectors, threshold=Decimal("0.95"))

    assert len(result.retained_mentions) == 2
    assert len(result.links) == 1
    assert result.links[0].similarity == Decimal("1.000000000000")


def test_complete_linkage_clustering_is_deterministic_and_persona_separated() -> None:
    owner_a = mention("a", "dispatch delay", EvidencePersona.OWNER)
    owner_b = mention("b", "dispatch backlog", EvidencePersona.OWNER)
    employee = mention("c", "dispatch queue", EvidencePersona.EMPLOYEE)
    vectors = (
        vector(owner_a, (1.0, 0.0)),
        vector(owner_b, (0.9, 0.1)),
        vector(employee, (1.0, 0.0)),
    )
    configuration = ClusteringConfiguration(
        clustering_version="v1",
        similarity_threshold=Decimal("0.8"),
        near_duplicate_threshold=Decimal("0.98"),
        min_cluster_size=2,
        max_mentions=100,
    )

    first = cluster_mentions((employee, owner_b, owner_a), vectors, configuration)
    second = cluster_mentions((owner_a, employee, owner_b), tuple(reversed(vectors)), configuration)

    assert first == second
    assert len(first.clusters) == 2
    assert {cluster.persona for cluster in first.clusters} == {
        EvidencePersona.OWNER,
        EvidencePersona.EMPLOYEE,
    }
    assert sum(cluster.is_outlier for cluster in first.clusters) == 1


def vector(item: PainMention, first_two: tuple[float, float]) -> EmbeddingVector:
    values = (*first_two, *(0.0 for _ in range(14)))
    return EmbeddingVector(
        mention_id=item.mention_id,
        provider="fixture",
        model_reference="fixture-vectors",
        embedding_version="v1",
        input_sha256=item.normalized_pain_sha256,
        dimensions=16,
        values=values,
    )
