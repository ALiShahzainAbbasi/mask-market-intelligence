"""Formula-driven deterministic M3 bottleneck and market calculation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal

from mask_api.modules.scoring.math import clamp10, linear, log_scale, weighted_mean
from mask_api.modules.workflow_intelligence.contracts import (
    M3ComponentScores,
    M3ComponentValues,
    M3Result,
    M3Status,
    WorkflowBottleneckMetrics,
    WorkflowContradiction,
    WorkflowReportSection,
    WorkflowStepEvidence,
)
from mask_api.research_runner.contracts import MethodFormula, TransformConfiguration, TransformKind

M3_COMPONENTS = {
    "volume",
    "labor_burden",
    "failure_rate",
    "business_consequence",
    "automation_potential",
    "manuality",
}


class M3CalculationError(ValueError):
    """Inputs do not satisfy the approved M3 calculation contract."""


def calculate_m3(
    *,
    market_id: str,
    formula_version: str,
    formula: MethodFormula,
    evidence: tuple[WorkflowStepEvidence, ...],
    contradictions: tuple[WorkflowContradiction, ...] = (),
) -> M3Result:
    _validate_formula(formula)
    if any(item.market_id != market_id for item in evidence):
        raise M3CalculationError("M3 input cannot mix markets")
    evidence_ids = {item.evidence_id for item in evidence}
    if len(evidence_ids) != len(evidence):
        raise M3CalculationError("M3 evidence IDs must be unique")
    if any(
        linked not in evidence_ids
        for contradiction in contradictions
        for linked in contradiction.linked_evidence_ids
    ):
        raise M3CalculationError("contradiction links must reference input evidence")

    groups: dict[str, list[WorkflowStepEvidence]] = defaultdict(list)
    for item in evidence:
        groups[item.normalized_step_name_sha256].append(item)

    bottlenecks = tuple(
        _bottleneck_metrics(step_key, items, formula, contradictions)
        for step_key, items in sorted(groups.items())
    )

    unknown_reasons: list[str] = []
    if not bottlenecks:
        unknown_reasons.append("m3.no_workflow_steps")
    if any(item.bottleneck_score is None for item in bottlenecks):
        unknown_reasons.append("m3.step_component_missing")

    score: Decimal | None = None
    top_ids: tuple[str, ...] = ()
    if not unknown_reasons:
        ranked = tuple(
            sorted(
                bottlenecks,
                key=lambda item: (-_known_score(item), item.step_key),
            )
        )
        aggregation = formula.aggregation
        if (
            aggregation.kind != "max_and_weighted_top"
            or aggregation.max_weight is None
            or aggregation.mean_weight is None
            or aggregation.top_n is None
        ):
            raise M3CalculationError("M3 formula requires max_and_weighted_top aggregation")
        top = ranked[: aggregation.top_n]
        scores = tuple(_known_score(item) for item in top)
        weights = tuple(Decimal(item.evidence_count).sqrt() for item in top)
        mean = weighted_mean(scores, weights)
        if mean is None:
            raise M3CalculationError("M3 top-bottleneck mean unexpectedly had no values")
        score = clamp10(aggregation.max_weight * max(scores) + aggregation.mean_weight * mean)
        top_ids = tuple(item.step_key for item in top)

    source_distribution = Counter(item.source_family for item in evidence)
    persona_distribution = Counter(item.persona for item in evidence)
    dates = sorted(item.source_date for item in evidence if item.source_date is not None)
    report = WorkflowReportSection(
        market_id=market_id,
        total_input_evidence=len(evidence),
        unique_steps=len(bottlenecks),
        source_family_distribution=dict(sorted(source_distribution.items())),
        persona_distribution=dict(
            sorted(persona_distribution.items(), key=lambda item: item[0].value)
        ),
        earliest_source_date=dates[0] if dates else None,
        latest_source_date=dates[-1] if dates else None,
        contradiction_count=len(contradictions),
        bottlenecks=bottlenecks,
    )

    return M3Result(
        market_id=market_id,
        formula_version=formula_version,
        input_sha256=_input_sha256(evidence),
        status=M3Status.COMPLETE if score is not None else M3Status.UNKNOWN,
        score=score,
        top_bottleneck_ids=top_ids,
        unknown_reasons=tuple(unknown_reasons),
        bottlenecks=bottlenecks,
        report=report,
    )


def _bottleneck_metrics(
    step_key: str,
    items: list[WorkflowStepEvidence],
    formula: MethodFormula,
    contradictions: tuple[WorkflowContradiction, ...],
) -> WorkflowBottleneckMetrics:
    families = {item.source_family for item in items}
    values = M3ComponentValues(
        volume=_mean(item.events_per_month for item in items),
        labor_burden=_mean(item.labor_hours_per_month for item in items),
        failure_rate=_mean(item.failure_rate for item in items),
        business_consequence=_mean(item.consequence_score for item in items),
        automation_potential=_mean(item.automation_potential for item in items),
        manuality=_mean(item.manual_share for item in items),
    )
    scored: dict[str, Decimal | None] = {
        name: _transform(getattr(values, name), formula.components[name].transform)
        for name in sorted(M3_COMPONENTS)
    }
    scores = M3ComponentScores(**scored)
    missing = tuple(name for name in sorted(M3_COMPONENTS) if scored[name] is None)
    bottleneck_score: Decimal | None = None
    if not missing:
        bottleneck_score = clamp10(
            sum(
                (
                    _required(scored[name]) * formula.components[name].weight
                    for name in sorted(M3_COMPONENTS)
                ),
                Decimal("0"),
            )
        )
    evidence_ids = {item.evidence_id for item in items}
    contradiction_ids = tuple(
        sorted(
            item.contradiction_id
            for item in contradictions
            if set(item.linked_evidence_ids) & evidence_ids
        )
    )
    representatives = tuple(
        item.evidence_id
        for item in sorted(items, key=lambda item: (-item.extraction_confidence, item.evidence_id))[
            :3
        ]
    )
    return WorkflowBottleneckMetrics(
        step_key=step_key,
        step_name=items[0].step_name,
        evidence_count=len(items),
        source_family_count=len(families),
        component_values=values,
        component_scores=scores,
        component_sample_counts={
            "volume": sum(item.events_per_month is not None for item in items),
            "labor_burden": sum(item.labor_hours_per_month is not None for item in items),
            "failure_rate": sum(item.failure_rate is not None for item in items),
            "business_consequence": sum(item.consequence_score is not None for item in items),
            "automation_potential": sum(item.automation_potential is not None for item in items),
            "manuality": sum(item.manual_share is not None for item in items),
        },
        bottleneck_score=bottleneck_score,
        missing_components=missing,
        representative_evidence_ids=representatives,
        contradiction_ids=contradiction_ids,
    )


def _mean(values: Iterable[Decimal | None]) -> Decimal | None:
    present = tuple(value for value in values if value is not None)
    if not present:
        return None
    return sum(present, Decimal("0")) / Decimal(len(present))


def _transform(value: Decimal | None, transform: TransformConfiguration) -> Decimal | None:
    if value is None:
        return None
    kind = transform.kind
    if kind == TransformKind.IDENTITY:
        return clamp10(value)
    if kind == TransformKind.LINEAR:
        if transform.low is None or transform.high is None:
            raise M3CalculationError("linear M3 transform requires bounds")
        return linear(value, transform.low, transform.high)
    if kind == TransformKind.LOG_SCALE:
        if transform.low is None or transform.high is None:
            raise M3CalculationError("log_scale M3 transform requires bounds")
        if value <= Decimal("0"):
            return Decimal("0")
        return log_scale(value, transform.low, transform.high)
    raise M3CalculationError("M3 component uses an unsupported transform")


def _required(value: Decimal | None) -> Decimal:
    if value is None:
        raise M3CalculationError("required M3 component was unexpectedly missing")
    return value


def _known_score(item: WorkflowBottleneckMetrics) -> Decimal:
    if item.bottleneck_score is None:
        raise M3CalculationError("ranked M3 bottleneck has no score")
    return item.bottleneck_score


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != M3_COMPONENTS:
        raise M3CalculationError("M3 formula components do not match v1")
    if formula.aggregation.kind != "max_and_weighted_top":
        raise M3CalculationError("M3 aggregation kind does not match v1")


def _input_sha256(evidence: tuple[WorkflowStepEvidence, ...]) -> str:
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in evidence],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
