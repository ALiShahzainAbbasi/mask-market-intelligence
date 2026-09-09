"""Deterministic M6 search-and-buying-intent calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentStatus,
    M6Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import SourcedMetric, canonical_sha256
from mask_api.modules.method_metrics.transforms import simple_component_breakdown
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import MethodFormula, MethodId

M6_RAW_INPUT_BY_COMPONENT: dict[str, str] = {
    "weighted_demand": "weighted_monthly_volume",
    "commercial_cpc": "weighted_avg_cpc_usd",
    "high_intent_mix": "high_intent_share",
    "trend": "growth",
    "switching_demand": "switching_share",
}
M6_COMPONENTS = tuple(M6_RAW_INPUT_BY_COMPONENT)
M6_MIN_SAMPLE_KEYWORDS = 100


class M6CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M6 calculation contract."""


def calculate_m6(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M6Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)
    metrics_by_component: dict[str, SourcedMetric | None] = {
        component: getattr(inputs, M6_RAW_INPUT_BY_COMPONENT[component])
        for component in M6_COMPONENTS
    }
    breakdown = tuple(
        simple_component_breakdown(
            component,
            metrics_by_component[component],
            formula.components[component],
            missing_reason=f"m6.{M6_RAW_INPUT_BY_COMPONENT[component]}_missing",
        )
        for component in M6_COMPONENTS
    )
    missing = tuple(item.component for item in breakdown if item.status == ComponentStatus.MISSING)

    unknown_reasons: list[str] = []
    if missing:
        unknown_reasons.append("m6.required_component_missing")
    if inputs.qualified_keyword_count is None:
        unknown_reasons.append("m6.qualified_keyword_count_missing")

    provisional_reasons: list[str] = []
    score: Decimal | None = None
    status = MethodMetricStatus.UNKNOWN
    if not unknown_reasons:
        contributions = tuple(
            item.weighted_contribution
            for item in breakdown
            if item.weighted_contribution is not None
        )
        score = clamp10(sum(contributions, ZERO))
        sample_size = inputs.qualified_keyword_count.value  # type: ignore[union-attr]
        if sample_size < M6_MIN_SAMPLE_KEYWORDS:
            provisional_reasons.append("m6.keyword_sample_below_100")
        status = (
            MethodMetricStatus.PROVISIONAL if provisional_reasons else MethodMetricStatus.COMPLETE
        )

    return MethodMetricResult(
        method_id=MethodId.M6,
        market_id=inputs.market_id,
        formula_version=formula_version,
        inputs_sha256=canonical_sha256(inputs),
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=tuple(unknown_reasons),
        provisional_reasons=tuple(provisional_reasons),
    )


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != set(M6_COMPONENTS):
        raise M6CalculationError("M6 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M6CalculationError("M6 aggregation kind does not match v1")
