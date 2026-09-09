"""Deterministic M1 quantitative-market-analysis calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentStatus,
    M1Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import (
    SourcedMetric,
    canonical_sha256,
    require_shared_geography,
    require_shared_population,
)
from mask_api.modules.method_metrics.transforms import simple_component_breakdown
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import MethodFormula, MethodId

M1_RAW_INPUT_BY_COMPONENT: dict[str, str] = {
    "buyer_pool": "serviceable_businesses",
    "growth": "growth_cagr",
    "fragmentation": "fragmentation_share",
    "economic_capacity": "annual_payroll_per_serviceable_establishment_usd",
    "target_band_match": "target_band_share",
}
M1_COMPONENTS = tuple(M1_RAW_INPUT_BY_COMPONENT)
M1_OPTIONAL_COMPONENTS = ("growth", "fragmentation", "economic_capacity", "target_band_match")
M1_MIN_OPTIONAL_COMPONENTS = 3

# target_band_match uses transform {kind: linear, low: 0.05, high: 0.40,
# special_case: intentionally_all_firms_is_10}: linear() already clamps any share
# at or above 0.40 (including an undifferentiated 1.0 "all firms" share) to 10.
# The special_case is documentation of that approved, intentional behavior, not a
# separate code path.


class M1CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M1 calculation contract."""


def calculate_m1(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M1Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)
    metrics_by_component: dict[str, SourcedMetric | None] = {
        component: getattr(inputs, M1_RAW_INPUT_BY_COMPONENT[component])
        for component in M1_COMPONENTS
    }
    present_metrics = tuple(
        metric for metric in metrics_by_component.values() if metric is not None
    )
    require_shared_geography(present_metrics)
    require_shared_population(present_metrics)

    breakdown = tuple(
        simple_component_breakdown(
            component,
            metrics_by_component[component],
            formula.components[component],
            missing_reason=f"m1.{M1_RAW_INPUT_BY_COMPONENT[component]}_missing",
        )
        for component in M1_COMPONENTS
    )
    present = {item.component for item in breakdown if item.status == ComponentStatus.AVAILABLE}

    unknown_reasons: list[str] = []
    if "buyer_pool" not in present:
        unknown_reasons.append("m1.serviceable_businesses_unavailable")
    optional_present = len(present & set(M1_OPTIONAL_COMPONENTS))
    if optional_present < M1_MIN_OPTIONAL_COMPONENTS:
        unknown_reasons.append("m1.fewer_than_three_optional_components")

    provisional_reasons: list[str] = []
    score: Decimal | None = None
    status = MethodMetricStatus.UNKNOWN
    if not unknown_reasons:
        score = clamp10(
            sum(
                (
                    item.weighted_contribution
                    for item in breakdown
                    if item.weighted_contribution is not None
                ),
                ZERO,
            )
        )
        if optional_present < len(M1_OPTIONAL_COMPONENTS):
            provisional_reasons.append("m1.fewer_than_four_optional_components")
        status = (
            MethodMetricStatus.PROVISIONAL if provisional_reasons else MethodMetricStatus.COMPLETE
        )

    return MethodMetricResult(
        method_id=MethodId.M1,
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
    if set(formula.components) != set(M1_COMPONENTS):
        raise M1CalculationError("M1 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M1CalculationError("M1 aggregation kind does not match v1")
