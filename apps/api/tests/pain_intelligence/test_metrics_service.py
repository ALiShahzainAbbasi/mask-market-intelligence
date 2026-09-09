from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from mask_api.modules.evidence.domain import EvidencePersona
from mask_api.modules.pain_intelligence.clustering import cluster_mentions
from mask_api.modules.pain_intelligence.contracts import (
    ClusteringConfiguration,
    EmbeddingVector,
    M2Status,
    PainContradiction,
    PainMention,
)
from mask_api.modules.pain_intelligence.embedding_cache import ArtifactEmbeddingCache
from mask_api.modules.pain_intelligence.embeddings import (
    LOCAL_HASHING_MODEL,
    LOCAL_HASHING_PROVIDER,
    LOCAL_HASHING_VERSION,
    EmbeddingService,
    LocalHashingEmbeddingProvider,
)
from mask_api.modules.pain_intelligence.metrics import calculate_m2
from mask_api.modules.pain_intelligence.service import PainIntelligenceService
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId
from mask_api.research_runner.local_artifacts import LocalArtifactStore

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M2 = FORMULAS.method_formulas[MethodId.M2]


def budget() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=0,
            max_documents=0,
            max_total_bytes=2_000_000,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0"),
        )
    )


def mention(index: int, *, source_family: str | None = None) -> PainMention:
    seed = str(index)
    text = f"dispatch pain example {index}"
    return PainMention(
        mention_id=hashlib.sha256(seed.encode()).hexdigest(),
        market_id="us_hvac",
        document_id=f"doc-{index}",
        normalized_document_sha256=hashlib.sha256(f"doc-{index}".encode()).hexdigest(),
        analysis_cache_key=hashlib.sha256(f"analysis-{index}".encode()).hexdigest(),
        grounding_version="grounding-v1",
        source_family=source_family or f"family_{index % 3}",
        persona=EvidencePersona.OWNER,
        source_date=date(2026, 8, 1 + (index % 28)),
        pain_category="dispatch_delay",
        pain_description=text,
        normalized_pain_text=text,
        normalized_pain_sha256=hashlib.sha256(text.encode()).hexdigest(),
        sentiment=-2,
        severity_1_10=8,
        urgency_1_10=7,
        economic_impact_types=("revenue_leakage",),
        economic_impact_1_10=6,
        purchase_intent_0_4=4,
        solution_dissatisfaction_1_10=7,
        software_mentioned=(),
        financial_values=(),
        evidence_span=text,
        extraction_confidence=Decimal("0.9"),
    )


def fixture_vector(item: PainMention) -> EmbeddingVector:
    return EmbeddingVector(
        mention_id=item.mention_id,
        provider="fixture",
        model_reference="fixture-vectors",
        embedding_version="v1",
        input_sha256=item.normalized_pain_sha256,
        dimensions=16,
        values=(1.0, *(0.0 for _ in range(15))),
    )


def test_formula_driven_m2_golden_result_and_completeness() -> None:
    mentions = tuple(mention(index) for index in range(100))
    vectors = tuple(fixture_vector(item) for item in mentions)
    config = ClusteringConfiguration(
        clustering_version="v1",
        similarity_threshold=Decimal("0.8"),
        near_duplicate_threshold=Decimal("0.99"),
        min_cluster_size=2,
        max_mentions=500,
    )
    clustering = cluster_mentions(mentions, vectors, config)

    result = calculate_m2(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M2,
        all_relevant_unique_documents=500,
        input_mentions=mentions,
        retained_mentions=mentions,
        duplicate_links=(),
        clustering=clustering,
    )

    assert result.status == M2Status.COMPLETE
    assert result.score == Decimal("8.250")
    assert result.report.clusters[0].component_scores.frequency == Decimal("10")
    assert result.report.clusters[0].component_scores.purchase_intent == Decimal("10.0")
    assert result.report.source_family_distribution == {
        "family_0": 34,
        "family_1": 33,
        "family_2": 33,
    }


def test_m2_is_unknown_below_100_relevant_unique_documents() -> None:
    mentions = tuple(mention(index) for index in range(3))
    vectors = tuple(fixture_vector(item) for item in mentions)
    config = ClusteringConfiguration(
        clustering_version="v1",
        similarity_threshold=Decimal("0.8"),
        near_duplicate_threshold=Decimal("0.99"),
        min_cluster_size=2,
        max_mentions=100,
    )
    clustering = cluster_mentions(mentions, vectors, config)

    result = calculate_m2(
        market_id="us_hvac",
        formula_version="v1",
        formula=M2,
        all_relevant_unique_documents=99,
        input_mentions=mentions,
        retained_mentions=mentions,
        duplicate_links=(),
        clustering=clustering,
    )

    assert result.status == M2Status.UNKNOWN
    assert result.score is None
    assert "m2.sample_below_minimum" in result.unknown_reasons


def test_missing_cluster_component_stays_unknown_and_contradiction_is_reported() -> None:
    base = mention(1)
    incomplete = base.model_copy(update={"economic_impact_1_10": None})
    vectors = (fixture_vector(incomplete),)
    config = ClusteringConfiguration(
        clustering_version="v1",
        similarity_threshold=Decimal("0.8"),
        near_duplicate_threshold=Decimal("0.99"),
        min_cluster_size=1,
        max_mentions=100,
    )
    clustering = cluster_mentions((incomplete,), vectors, config)
    contradiction = PainContradiction(
        contradiction_id=hashlib.sha256(b"contradiction").hexdigest(),
        document_id="doc-contradiction",
        source_family="official_page",
        claim="A contrary source reports no measurable impact.",
        evidence_span="no measurable impact",
        linked_mention_ids=(incomplete.mention_id,),
    )

    result = calculate_m2(
        market_id="us_hvac",
        formula_version="v1",
        formula=M2,
        all_relevant_unique_documents=500,
        input_mentions=(incomplete,),
        retained_mentions=(incomplete,),
        duplicate_links=(),
        clustering=clustering,
        contradictions=(contradiction,),
    )

    assert result.status == M2Status.UNKNOWN
    assert result.score is None
    assert result.report.contradiction_count == 1
    assert result.report.clusters[0].contradiction_ids == (contradiction.contradiction_id,)
    assert "economic_impact" in result.report.clusters[0].missing_components


def test_end_to_end_offline_service_deduplicates_before_weighting(tmp_path: Path) -> None:
    first = mention(1)
    duplicate = first.model_copy(
        update={
            "mention_id": hashlib.sha256(b"duplicate").hexdigest(),
            "document_id": "duplicate-doc",
            "normalized_document_sha256": first.normalized_document_sha256,
            "analysis_cache_key": hashlib.sha256(b"duplicate-analysis").hexdigest(),
        }
    )
    config = ClusteringConfiguration(
        clustering_version="v1",
        similarity_threshold=Decimal("0.2"),
        near_duplicate_threshold=Decimal("0.95"),
        min_cluster_size=1,
        max_mentions=100,
    )
    embeddings = EmbeddingService(
        LocalHashingEmbeddingProvider(),
        ArtifactEmbeddingCache(LocalArtifactStore(tmp_path)),
        provider_name=LOCAL_HASHING_PROVIDER,
        model_reference=LOCAL_HASHING_MODEL,
        embedding_version=LOCAL_HASHING_VERSION,
        dimensions=64,
    )

    result = PainIntelligenceService(embeddings, config).run(
        market_id="us_hvac",
        formula_version="v1",
        formula=M2,
        all_relevant_unique_documents=99,
        mentions=(duplicate, first),
        ledger=budget(),
    )

    assert result.report.total_input_mentions == 2
    assert result.report.unique_mentions == 1
    assert result.report.exact_duplicates == 1
    assert result.report.clusters[0].unique_document_count == 1
    assert result.status == M2Status.UNKNOWN
