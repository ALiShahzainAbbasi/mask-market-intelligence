"""Formula-driven deterministic M2 cluster and market calculation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from mask_api.modules.pain_intelligence.contracts import (
    ClusteringResult,
    M2ComponentScores,
    M2ComponentValues,
    M2Result,
    M2Status,
    PainCluster,
    PainClusterMetrics,
    PainContradiction,
    PainDuplicateLink,
    PainMention,
    PainReportSection,
)
from mask_api.modules.scoring.math import clamp10, linear, weighted_mean
from mask_api.research_runner.contracts import (
    MethodFormula,
    TransformConfiguration,
    TransformKind,
)

M2_COMPONENTS = {
    "frequency",
    "severity",
    "economic_impact",
    "purchase_intent",
    "dissatisfaction",
}
M2_MIN_SOURCE_FAMILIES = 3


class M2CalculationError(ValueError):
    """Inputs do not satisfy the approved M2 calculation contract."""


def calculate_m2(
    *,
    market_id: str,
    formula_version: str,
    formula: MethodFormula,
    all_relevant_unique_documents: int,
    input_mentions: tuple[PainMention, ...],
    retained_mentions: tuple[PainMention, ...],
    duplicate_links: tuple[PainDuplicateLink, ...],
    clustering: ClusteringResult,
    contradictions: tuple[PainContradiction, ...] = (),
) -> M2Result:
    _validate_formula(formula)
    if all_relevant_unique_documents < 0:
        raise M2CalculationError("relevant unique document count cannot be negative")
    if any(mention.market_id != market_id for mention in input_mentions):
        raise M2CalculationError("M2 input cannot mix markets")
    input_ids = {mention.mention_id for mention in input_mentions}
    if len(input_ids) != len(input_mentions):
        raise M2CalculationError("M2 input mention IDs must be unique")
    retained_by_id = {mention.mention_id: mention for mention in retained_mentions}
    if len(retained_by_id) != len(retained_mentions):
        raise M2CalculationError("retained mention IDs must be unique")
    if len({mention.document_id for mention in retained_mentions}) > all_relevant_unique_documents:
        raise M2CalculationError("pain documents exceed the relevant unique denominator")
    membership_ids = [
        membership.mention_id
        for cluster in clustering.clusters
        for membership in cluster.memberships
    ]
    if len(membership_ids) != len(set(membership_ids)) or set(membership_ids) != set(
        retained_by_id
    ):
        raise M2CalculationError("clustering membership must cover each retained mention once")
    if any(
        linked not in input_ids
        for contradiction in contradictions
        for linked in contradiction.linked_mention_ids
    ):
        raise M2CalculationError("contradiction links must reference input mentions")

    alias = _duplicate_aliases(duplicate_links)
    metrics = tuple(
        _cluster_metrics(
            cluster,
            retained_by_id,
            all_relevant_unique_documents,
            formula,
            contradictions,
            alias,
        )
        for cluster in clustering.clusters
    )
    unknown_reasons: list[str] = []
    sample = formula.sample
    if sample is None or sample.unknown_below is None or sample.full_target is None:
        raise M2CalculationError("M2 formula requires explicit sample thresholds")
    if all_relevant_unique_documents < sample.unknown_below:
        unknown_reasons.append("m2.sample_below_minimum")
    non_outlier_ids = {
        cluster.cluster_id for cluster in clustering.clusters if not cluster.is_outlier
    }
    eligible = tuple(item for item in metrics if item.cluster_id in non_outlier_ids)
    if not eligible:
        unknown_reasons.append("m2.no_non_outlier_cluster")
    if any(item.opportunity_score is None for item in eligible):
        unknown_reasons.append("m2.cluster_component_missing")

    score: Decimal | None = None
    top_ids: tuple[str, ...] = ()
    if not unknown_reasons:
        ranked = tuple(
            sorted(
                eligible,
                key=lambda item: (
                    -_known_score(item),
                    item.cluster_id,
                ),
            )
        )
        aggregation = formula.aggregation
        if (
            aggregation.kind != "max_and_weighted_top"
            or aggregation.max_weight is None
            or aggregation.mean_weight is None
            or aggregation.top_n is None
        ):
            raise M2CalculationError("M2 formula requires max_and_weighted_top aggregation")
        top = ranked[: aggregation.top_n]
        scores = tuple(_known_score(item) for item in top)
        weights = tuple(Decimal(item.unique_document_count).sqrt() for item in top)
        mean = weighted_mean(scores, weights)
        if mean is None:
            raise M2CalculationError("M2 top-cluster mean unexpectedly had no values")
        score = clamp10(aggregation.max_weight * max(scores) + aggregation.mean_weight * mean)
        top_ids = tuple(item.cluster_id for item in top)

    source_distribution = Counter(mention.source_family for mention in retained_mentions)
    persona_distribution = Counter(mention.persona for mention in retained_mentions)
    dates = sorted(
        mention.source_date for mention in retained_mentions if mention.source_date is not None
    )
    outlier_ids = {
        membership.mention_id
        for cluster in clustering.clusters
        if cluster.is_outlier
        for membership in cluster.memberships
    }
    report = PainReportSection(
        market_id=market_id,
        total_input_mentions=len(input_mentions),
        unique_mentions=len(retained_mentions),
        exact_duplicates=sum(link.duplicate_kind.value == "exact" for link in duplicate_links),
        near_duplicates=sum(link.duplicate_kind.value == "near" for link in duplicate_links),
        outlier_mentions=len(outlier_ids),
        source_family_distribution=dict(sorted(source_distribution.items())),
        persona_distribution=dict(
            sorted(persona_distribution.items(), key=lambda item: item[0].value)
        ),
        earliest_source_date=dates[0] if dates else None,
        latest_source_date=dates[-1] if dates else None,
        contradiction_count=len(contradictions),
        clusters=metrics,
    )

    provisional_reasons: list[str] = []
    status = M2Status.UNKNOWN
    if score is not None:
        if all_relevant_unique_documents < sample.full_target:
            provisional_reasons.append("m2.sample_below_full_target")
        if len(source_distribution) < M2_MIN_SOURCE_FAMILIES:
            provisional_reasons.append("m2.source_families_below_minimum")
        status = M2Status.PROVISIONAL if provisional_reasons else M2Status.COMPLETE
    return M2Result(
        market_id=market_id,
        formula_version=formula_version,
        clustering_input_sha256=clustering.input_sha256,
        status=status,
        score=score,
        top_cluster_ids=top_ids,
        unknown_reasons=tuple(unknown_reasons),
        provisional_reasons=tuple(provisional_reasons),
        duplicate_links=duplicate_links,
        clusters=clustering.clusters,
        report=report,
    )


def _cluster_metrics(
    cluster: PainCluster,
    mentions: dict[str, PainMention],
    denominator: int,
    formula: MethodFormula,
    contradictions: tuple[PainContradiction, ...],
    alias: dict[str, str],
) -> PainClusterMetrics:
    cluster_mentions = tuple(mentions[item.mention_id] for item in cluster.memberships)
    documents = {item.document_id for item in cluster_mentions}
    families = {item.source_family for item in cluster_mentions}
    frequency = Decimal(len(documents)) / Decimal(denominator) if denominator else Decimal("0")
    severity = _mean(item.severity_1_10 for item in cluster_mentions)
    economic = _mean(item.economic_impact_1_10 for item in cluster_mentions)
    intent = _mean(item.purchase_intent_0_4 for item in cluster_mentions)
    dissatisfaction = _mean(item.solution_dissatisfaction_1_10 for item in cluster_mentions)
    values = M2ComponentValues(
        frequency=frequency,
        severity=severity,
        economic_impact=economic,
        purchase_intent=intent,
        dissatisfaction=dissatisfaction,
    )
    scored: dict[str, Decimal | None] = {
        "frequency": _transform(values.frequency, formula.components["frequency"].transform),
        "severity": _transform(values.severity, formula.components["severity"].transform),
        "economic_impact": _transform(
            values.economic_impact, formula.components["economic_impact"].transform
        ),
        "purchase_intent": _transform(
            values.purchase_intent, formula.components["purchase_intent"].transform
        ),
        "dissatisfaction": _transform(
            values.dissatisfaction, formula.components["dissatisfaction"].transform
        ),
    }
    scores = M2ComponentScores(**scored)
    missing = tuple(name for name in sorted(M2_COMPONENTS) if scored[name] is None)
    opportunity: Decimal | None = None
    if not missing:
        opportunity = clamp10(
            sum(
                (
                    _required(scored[name]) * formula.components[name].weight
                    for name in sorted(M2_COMPONENTS)
                ),
                Decimal("0"),
            )
        )
    cluster_ids = {item.mention_id for item in cluster_mentions}
    contradiction_ids = tuple(
        sorted(
            item.contradiction_id
            for item in contradictions
            if {alias.get(link, link) for link in item.linked_mention_ids} & cluster_ids
        )
    )
    representatives = tuple(
        item.mention_id
        for item in sorted(
            cluster_mentions,
            key=lambda item: (-item.extraction_confidence, item.mention_id),
        )[:3]
    )
    return PainClusterMetrics(
        cluster_id=cluster.cluster_id,
        unique_document_count=len(documents),
        source_family_count=len(families),
        mention_count=len(cluster_mentions),
        component_values=values,
        component_scores=scores,
        component_sample_counts={
            "frequency": len(documents),
            "severity": sum(item.severity_1_10 is not None for item in cluster_mentions),
            "economic_impact": sum(
                item.economic_impact_1_10 is not None for item in cluster_mentions
            ),
            "purchase_intent": sum(
                item.purchase_intent_0_4 is not None for item in cluster_mentions
            ),
            "dissatisfaction": sum(
                item.solution_dissatisfaction_1_10 is not None for item in cluster_mentions
            ),
        },
        opportunity_score=opportunity,
        missing_components=missing,
        representative_mention_ids=representatives,
        contradiction_ids=contradiction_ids,
    )


def _mean(values: Iterable[int | None]) -> Decimal | None:
    present = tuple(Decimal(value) for value in values if value is not None)
    if not present:
        return None
    return sum(present, Decimal("0")) / Decimal(len(present))


def _transform(
    value: Decimal | None,
    transform: TransformConfiguration,
) -> Decimal | None:
    if value is None:
        return None
    raw = value
    kind = transform.kind
    if kind == TransformKind.IDENTITY:
        return clamp10(raw)
    if kind == TransformKind.LINEAR:
        if transform.low is None or transform.high is None:
            raise M2CalculationError("linear M2 transform requires bounds")
        return linear(raw, transform.low, transform.high)
    if kind == TransformKind.MULTIPLY:
        if transform.multiplier is None:
            raise M2CalculationError("multiply M2 transform requires a multiplier")
        return clamp10(raw * transform.multiplier)
    raise M2CalculationError("M2 component uses an unsupported transform")


def _required(value: Decimal | None) -> Decimal:
    if value is None:
        raise M2CalculationError("required M2 component was unexpectedly missing")
    return value


def _known_score(item: PainClusterMetrics) -> Decimal:
    if item.opportunity_score is None:
        raise M2CalculationError("ranked M2 cluster has no opportunity score")
    return item.opportunity_score


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != M2_COMPONENTS:
        raise M2CalculationError("M2 formula components do not match v1")
    if formula.aggregation.kind != "max_and_weighted_top":
        raise M2CalculationError("M2 aggregation kind does not match v1")


def _duplicate_aliases(links: tuple[PainDuplicateLink, ...]) -> dict[str, str]:
    duplicates = [item.duplicate_mention_id for item in links]
    if len(duplicates) != len(set(duplicates)):
        raise M2CalculationError("one mention cannot have multiple duplicate links")
    direct = {item.duplicate_mention_id: item.retained_mention_id for item in links}
    resolved: dict[str, str] = {}
    for duplicate in direct:
        current = duplicate
        visited: set[str] = set()
        while current in direct:
            if current in visited:
                raise M2CalculationError("duplicate links contain a cycle")
            visited.add(current)
            current = direct[current]
        resolved[duplicate] = current
    return resolved
