"""Deterministic M7 buyer-accessibility-and-channel-fit calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentBreakdown,
    ComponentStatus,
    M7Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import (
    SourcedMetric,
    canonical_sha256,
    require_shared_geography,
    require_shared_population,
)
from mask_api.modules.method_metrics.transforms import (
    apply_transform,
    composite_weighted_linear,
    simple_component_breakdown,
)
from mask_api.modules.scoring.math import ZERO, clamp10, safe_rate
from mask_api.research_runner.contracts import MethodFormula, MethodId

M7_COMPONENTS = (
    "buyer_identification",
    "contact_coverage",
    "channel_diversity",
    "sales_cycle_simplicity",
    "procurement_simplicity",
    "meta_fit",
)

# The v1 audit expression for meta_fit's composite transform; a drift guard checks
# the loaded formula still says exactly this before the hardcoded sub-bounds below
# (0..10 for advertiser count, 0.10..0.60 for social-presence rate) are applied.
_META_FIT_EXPRESSION = (
    "0.50*linear(active_relevant_advertisers,0,10) + "
    "0.50*linear(account_social_presence_rate,0.10,0.60)"
)


class M7CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M7 calculation contract."""


def calculate_m7(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M7Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)
    population_metrics = tuple(
        metric
        for metric in (
            inputs.accounts_with_economic_buyer,
            inputs.target_accounts,
            inputs.accounts_with_valid_reachable_channel,
        )
        if metric is not None
    )
    require_shared_geography(population_metrics)
    require_shared_population(population_metrics)

    breakdown = (
        _ratio_breakdown(
            "buyer_identification",
            inputs.accounts_with_economic_buyer,
            inputs.target_accounts,
            formula,
            missing_reason="m7.buyer_identification_rate_missing",
            zero_denominator_reason="m7.target_accounts_is_zero",
        ),
        _ratio_breakdown(
            "contact_coverage",
            inputs.accounts_with_valid_reachable_channel,
            inputs.target_accounts,
            formula,
            missing_reason="m7.contact_coverage_rate_missing",
            zero_denominator_reason="m7.target_accounts_is_zero",
        ),
        simple_component_breakdown(
            "channel_diversity",
            inputs.viable_channel_count,
            formula.components["channel_diversity"],
            missing_reason="m7.viable_channel_count_missing",
        ),
        simple_component_breakdown(
            "sales_cycle_simplicity",
            inputs.median_days_to_decision,
            formula.components["sales_cycle_simplicity"],
            missing_reason="m7.median_days_to_decision_missing",
        ),
        simple_component_breakdown(
            "procurement_simplicity",
            inputs.procurement_complexity_index_0_10,
            formula.components["procurement_simplicity"],
            missing_reason="m7.procurement_complexity_index_missing",
        ),
        _meta_fit_breakdown(
            inputs.active_relevant_advertisers, inputs.account_social_presence_rate, formula
        ),
    )
    missing = tuple(item.component for item in breakdown if item.status == ComponentStatus.MISSING)

    unknown_reasons: list[str] = []
    if missing:
        unknown_reasons.append("m7.required_component_missing")

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
        method_id=MethodId.M7,
        market_id=inputs.market_id,
        formula_version=formula_version,
        inputs_sha256=canonical_sha256(inputs),
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=tuple(unknown_reasons),
    )


def _ratio_breakdown(
    component: str,
    numerator: SourcedMetric | None,
    denominator: SourcedMetric | None,
    formula: MethodFormula,
    *,
    missing_reason: str,
    zero_denominator_reason: str,
) -> ComponentBreakdown:
    definition = formula.components[component]
    if numerator is None or denominator is None:
        return ComponentBreakdown(
            component=component,
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason=missing_reason,
        )
    ratio = safe_rate(numerator.value, denominator.value)
    if ratio is None:
        return ComponentBreakdown(
            component=component,
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason=zero_denominator_reason,
        )
    score = apply_transform(ratio, definition.transform)
    return ComponentBreakdown(
        component=component,
        status=ComponentStatus.AVAILABLE,
        raw_value=ratio,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=(
            numerator.provenance.evidence_reference,
            denominator.provenance.evidence_reference,
        ),
    )


def _meta_fit_breakdown(
    advertisers: SourcedMetric | None,
    presence: SourcedMetric | None,
    formula: MethodFormula,
) -> ComponentBreakdown:
    definition = formula.components["meta_fit"]
    if definition.transform.expression != _META_FIT_EXPRESSION:
        raise M7CalculationError("M7 meta_fit composite expression does not match v1")
    if advertisers is None or presence is None:
        return ComponentBreakdown(
            component="meta_fit",
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason="m7.meta_fit_inputs_missing",
        )
    score = composite_weighted_linear(
        (
            (advertisers.value, Decimal("0.50"), Decimal("0"), Decimal("10")),
            (presence.value, Decimal("0.50"), Decimal("0.10"), Decimal("0.60")),
        )
    )
    return ComponentBreakdown(
        component="meta_fit",
        status=ComponentStatus.AVAILABLE,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=(
            advertisers.provenance.evidence_reference,
            presence.provenance.evidence_reference,
        ),
    )


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != set(M7_COMPONENTS):
        raise M7CalculationError("M7 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M7CalculationError("M7 aggregation kind does not match v1")
