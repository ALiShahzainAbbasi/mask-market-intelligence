"""Deterministic M9 MASK AI and productization-fit calculator (v1 formula)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import (
    ComponentBreakdown,
    ComponentStatus,
    M9Inputs,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.provenance import canonical_sha256
from mask_api.modules.method_metrics.transforms import (
    apply_transform,
    simple_component_breakdown,
    weighted_coverage_score,
)
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import MethodFormula, MethodId

M9_COMPONENTS = (
    "technical_fit",
    "integration_fit",
    "standardization",
    "recurring_revenue_potential",
    "proof_potential",
    "delivery_simplicity",
    "expansion_potential",
)


class M9CalculationError(ValueError):
    """Inputs do not satisfy the approved v1 M9 calculation contract."""


def calculate_m9(
    *,
    formula_version: str,
    formula: MethodFormula,
    inputs: M9Inputs,
) -> MethodMetricResult:
    _validate_formula(formula)

    breakdown = (
        _technical_fit_breakdown(inputs, formula),
        _integration_fit_breakdown(inputs, formula),
        simple_component_breakdown(
            "standardization",
            inputs.workflow_template_similarity_0_1,
            formula.components["standardization"],
            missing_reason="m9.workflow_template_similarity_missing",
        ),
        simple_component_breakdown(
            "recurring_revenue_potential",
            inputs.recurring_solution_value_share,
            formula.components["recurring_revenue_potential"],
            missing_reason="m9.recurring_solution_value_share_missing",
        ),
        simple_component_breakdown(
            "proof_potential",
            inputs.comparable_internal_project_count,
            formula.components["proof_potential"],
            missing_reason="m9.comparable_internal_project_count_missing",
        ),
        simple_component_breakdown(
            "delivery_simplicity",
            inputs.delivery_complexity_index_0_10,
            formula.components["delivery_simplicity"],
            missing_reason="m9.delivery_complexity_index_missing",
        ),
        simple_component_breakdown(
            "expansion_potential",
            inputs.adjacent_high_value_workflow_count,
            formula.components["expansion_potential"],
            missing_reason="m9.adjacent_high_value_workflow_count_missing",
        ),
    )
    missing = tuple(item.component for item in breakdown if item.status == ComponentStatus.MISSING)

    unknown_reasons: list[str] = []
    if missing:
        unknown_reasons.append("m9.required_component_missing")

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
        method_id=MethodId.M9,
        market_id=inputs.market_id,
        formula_version=formula_version,
        inputs_sha256=canonical_sha256(inputs),
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=tuple(unknown_reasons),
    )


def _technical_fit_breakdown(inputs: M9Inputs, formula: MethodFormula) -> ComponentBreakdown:
    definition = formula.components["technical_fit"]
    if not inputs.capability_requirements:
        return ComponentBreakdown(
            component="technical_fit",
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason="m9.no_capability_requirements",
        )
    coverage_by_id = {item.capability_id: item for item in inputs.capability_coverage}
    if any(item.capability_id not in coverage_by_id for item in inputs.capability_requirements):
        return ComponentBreakdown(
            component="technical_fit",
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason="m9.capability_coverage_incomplete",
        )
    pairs = tuple(
        (
            Decimal(1) if coverage_by_id[item.capability_id].covered else Decimal(0),
            item.required_weight,
        )
        for item in inputs.capability_requirements
    )
    score = weighted_coverage_score(pairs)
    if score is None:  # pragma: no cover - guaranteed by the non-empty requirements check above
        raise M9CalculationError("M9 technical_fit unexpectedly had no capability requirements")
    references = tuple(item.evidence_reference for item in inputs.capability_requirements) + tuple(
        item.evidence_reference for item in inputs.capability_coverage
    )
    return ComponentBreakdown(
        component="technical_fit",
        status=ComponentStatus.AVAILABLE,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=references,
    )


def _integration_fit_breakdown(inputs: M9Inputs, formula: MethodFormula) -> ComponentBreakdown:
    definition = formula.components["integration_fit"]
    if not inputs.integrations:
        return ComponentBreakdown(
            component="integration_fit",
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason="m9.no_integration_records",
        )
    supported_prevalence = sum(
        (item.target_market_prevalence_0_1 for item in inputs.integrations if item.supported),
        Decimal("0"),
    )
    score = apply_transform(supported_prevalence, definition.transform)
    references = tuple(item.evidence_reference for item in inputs.integrations)
    return ComponentBreakdown(
        component="integration_fit",
        status=ComponentStatus.AVAILABLE,
        raw_value=supported_prevalence,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=references,
    )


def _validate_formula(formula: MethodFormula) -> None:
    if set(formula.components) != set(M9_COMPONENTS):
        raise M9CalculationError("M9 formula components do not match v1")
    if formula.aggregation.kind != "weighted_sum":
        raise M9CalculationError("M9 aggregation kind does not match v1")
