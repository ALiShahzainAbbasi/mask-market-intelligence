"""Deterministic M4 economic-pain-and-existing-spend calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentStatus,
    M4Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import (
    SourcedMetric,
    canonical_sha256,
    require_shared_currency,
    require_shared_period,
)
from mask_api.modules.method_metrics.transforms import simple_component_breakdown
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import MethodFormula, MethodId

M4_RAW_INPUT_BY_COMPONENT: dict[str, str] = {
    "annual_burden": "annual_problem_cost_usd",
    "existing_paid_spend": "annual_existing_paid_spend_usd",
    "paid_workaround_penetration": "verified_paid_workaround_share",
    "commercial_intent": "mean_m2_purchase_intent_0_4",
}
M4_COMPONENTS = tuple(M4_RAW_INPUT_BY_COMPONENT)
_MONETARY_COMPONENTS = ("annual_burden", "existing_paid_spend")


class M4CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M4 calculation contract."""


def calculate_m4(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M4Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)
    metrics_by_component: dict[str, SourcedMetric | None] = {
        component: getattr(inputs, M4_RAW_INPUT_BY_COMPONENT[component])
        for component in M4_COMPONENTS
    }
    monetary_metrics = tuple(
        metrics_by_component[component]
        for component in _MONETARY_COMPONENTS
        if metrics_by_component[component] is not None
    )
    require_shared_currency(monetary_metrics)  # type: ignore[arg-type]
    require_shared_period(monetary_metrics)  # type: ignore[arg-type]

    breakdown = tuple(
        simple_component_breakdown(
            component,
            metrics_by_component[component],
            formula.components[component],
            missing_reason=f"m4.{M4_RAW_INPUT_BY_COMPONENT[component]}_missing",
        )
        for component in M4_COMPONENTS
    )
    missing = tuple(item.component for item in breakdown if item.status == ComponentStatus.MISSING)

    unknown_reasons: list[str] = []
    if missing:
        unknown_reasons.append("m4.required_component_missing")

    score: Decimal | None = None
    status = MethodMetricStatus.UNKNOWN
    if not missing:
        contributions = tuple(
            item.weighted_contribution
            for item in breakdown
            if item.weighted_contribution is not None
        )
        score = clamp10(sum(contributions, ZERO))
        status = MethodMetricStatus.COMPLETE

    return MethodMetricResult(
        method_id=MethodId.M4,
        market_id=inputs.market_id,
        formula_version=formula_version,
        inputs_sha256=canonical_sha256(inputs),
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=tuple(unknown_reasons),
    )


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != set(M4_COMPONENTS):
        raise M4CalculationError("M4 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M4CalculationError("M4 aggregation kind does not match v1")
