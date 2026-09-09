"""Deterministic M5 competitive-intelligence calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentBreakdown,
    ComponentStatus,
    M5CompetitorGap,
    M5Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import canonical_sha256
from mask_api.modules.method_metrics.transforms import (
    simple_component_breakdown,
    weighted_mean_sqrt_score,
)
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import MethodFormula, MethodId

M5_COMPONENTS = (
    "competitor_proof",
    "pricing_proof",
    "unresolved_gap",
    "differentiation_space",
    "traction_proof",
)
M5_UNRESOLVED_GAP_TOP_N = 5
M5_MIN_SAMPLE_COMPETITORS = 20


class M5CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M5 calculation contract."""


def calculate_m5(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M5Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)
    breakdown = (
        simple_component_breakdown(
            "competitor_proof",
            inputs.active_relevant_competitor_count,
            formula.components["competitor_proof"],
            missing_reason="m5.active_relevant_competitor_count_missing",
        ),
        simple_component_breakdown(
            "pricing_proof",
            inputs.median_annualized_customer_price_usd,
            formula.components["pricing_proof"],
            missing_reason="m5.median_annualized_customer_price_usd_missing",
        ),
        _unresolved_gap_breakdown(inputs.competitor_gaps, formula),
        simple_component_breakdown(
            "differentiation_space",
            inputs.median_offer_similarity_0_1,
            formula.components["differentiation_space"],
            missing_reason="m5.median_offer_similarity_0_1_missing",
        ),
        simple_component_breakdown(
            "traction_proof",
            inputs.verified_reference_count,
            formula.components["traction_proof"],
            missing_reason="m5.verified_reference_count_missing",
        ),
    )
    missing = tuple(item.component for item in breakdown if item.status == ComponentStatus.MISSING)

    unknown_reasons: list[str] = []
    if missing:
        unknown_reasons.append("m5.required_component_missing")

    provisional_reasons: list[str] = []
    score: Decimal | None = None
    status = MethodMetricStatus.UNKNOWN
    if not missing:
        contributions = tuple(
            item.weighted_contribution
            for item in breakdown
            if item.weighted_contribution is not None
        )
        score = clamp10(sum(contributions, ZERO))
        sample_size = (
            inputs.active_relevant_competitor_count.value
            if inputs.active_relevant_competitor_count is not None
            else ZERO
        )
        if sample_size < M5_MIN_SAMPLE_COMPETITORS:
            provisional_reasons.append("m5.competitor_sample_below_20")
        status = (
            MethodMetricStatus.PROVISIONAL if provisional_reasons else MethodMetricStatus.COMPLETE
        )

    return MethodMetricResult(
        method_id=MethodId.M5,
        market_id=inputs.market_id,
        formula_version=formula_version,
        inputs_sha256=canonical_sha256(inputs),
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=tuple(unknown_reasons),
        provisional_reasons=tuple(provisional_reasons),
    )


def _unresolved_gap_breakdown(
    gaps: tuple[M5CompetitorGap, ...],
    formula: MethodFormula,
) -> ComponentBreakdown:
    definition = formula.components["unresolved_gap"]
    if not gaps:
        return ComponentBreakdown(
            component="unresolved_gap",
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason="m5.competitor_gap_findings_missing",
        )
    score = weighted_mean_sqrt_score(
        tuple((item.gap_score_0_10, item.evidence_count) for item in gaps),
        top_n=M5_UNRESOLVED_GAP_TOP_N,
    )
    if score is None:  # pragma: no cover - guaranteed by the non-empty gaps check above
        raise M5CalculationError("M5 unresolved_gap unexpectedly had no values")
    references = tuple(reference for item in gaps for reference in item.evidence_references)
    return ComponentBreakdown(
        component="unresolved_gap",
        status=ComponentStatus.AVAILABLE,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=references,
    )


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != set(M5_COMPONENTS):
        raise M5CalculationError("M5 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M5CalculationError("M5 aggregation kind does not match v1")
