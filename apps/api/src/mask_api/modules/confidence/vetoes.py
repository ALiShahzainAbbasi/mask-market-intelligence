"""Deterministic detection of the three fully-numeric v1 vetoes.

The other three v1.yaml veto triggers need either an explicit human-verified
evidence flag (`major_access_or_regulatory_barrier`, `dominant_platform_
solves_problem`'s "dominant-solution evidence") or M8/M10 data that does not
exist yet (`no_qualified_buying_intent`, A18/A19). This module honestly
reports them as `not_evaluated` in every result rather than guessing at an
unapproved evidence contract.

Every v1 veto is treated as `critical` severity: v1.yaml's `vetoes` block
defines only vetoes (not a broader warning/red-flag taxonomy), and each one
describes a condition SCORING.md treats as advancement-blocking once
confirmed.
"""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    VetoAssessmentResult,
    VetoFinding,
    VetoId,
    VetoStatus,
)
from mask_api.modules.method_metrics import ComponentBreakdown, ComponentStatus, MethodMetricResult
from mask_api.research_runner.contracts import FormulaConfiguration

_NOT_EVALUATED = (
    VetoId.MAJOR_ACCESS_OR_REGULATORY_BARRIER,
    VetoId.DOMINANT_PLATFORM_SOLVES_PROBLEM,
    VetoId.NO_QUALIFIED_BUYING_INTENT,
)

_EXPECTED_TRIGGERS = {
    VetoId.NO_REACHABLE_ECONOMIC_BUYER: "M7 buyer_identification < 2 with HIGH confidence",
    VetoId.NO_MEANINGFUL_BUDGET: "M4 < 2 with HIGH confidence",
    VetoId.HIGHLY_BESPOKE_DELIVERY: (
        "M9 standardization < 3 and delivery_simplicity < 3 with MEDIUM or HIGH confidence"
    ),
}


class VetoAssessmentError(ValueError):
    """Inputs do not satisfy the approved v1 veto trigger contract."""


def evaluate_automatic_vetoes(
    formula: FormulaConfiguration,
    *,
    market_id: str,
    m4_result: MethodMetricResult | None = None,
    m4_confidence: ConfidenceResult | None = None,
    m7_result: MethodMetricResult | None = None,
    m7_confidence: ConfidenceResult | None = None,
    m9_result: MethodMetricResult | None = None,
    m9_confidence: ConfidenceResult | None = None,
) -> VetoAssessmentResult:
    _validate_formula(formula)
    findings: list[VetoFinding] = []

    if m4_result is not None and m4_result.score is not None and m4_result.score < Decimal("2"):
        findings.append(
            VetoFinding(
                veto_id=VetoId.NO_MEANINGFUL_BUDGET,
                severity="critical",
                status=VetoStatus.CONFIRMED if _is_high(m4_confidence) else VetoStatus.SUSPECTED,
                trigger_detail=f"M4 score {m4_result.score} < 2",
                evidence_references=_all_evidence(m4_result),
            )
        )

    buyer_identification = _find_component(m7_result, "buyer_identification")
    if buyer_identification is not None and _below(buyer_identification, Decimal("2")):
        findings.append(
            VetoFinding(
                veto_id=VetoId.NO_REACHABLE_ECONOMIC_BUYER,
                severity="critical",
                status=VetoStatus.CONFIRMED if _is_high(m7_confidence) else VetoStatus.SUSPECTED,
                trigger_detail=(
                    f"M7 buyer_identification {buyer_identification.transformed_score} < 2"
                ),
                evidence_references=buyer_identification.evidence_references,
            )
        )

    standardization = _find_component(m9_result, "standardization")
    delivery_simplicity = _find_component(m9_result, "delivery_simplicity")
    if (
        standardization is not None
        and delivery_simplicity is not None
        and _below(standardization, Decimal("3"))
        and _below(delivery_simplicity, Decimal("3"))
    ):
        findings.append(
            VetoFinding(
                veto_id=VetoId.HIGHLY_BESPOKE_DELIVERY,
                severity="critical",
                status=(
                    VetoStatus.CONFIRMED
                    if _is_medium_or_high(m9_confidence)
                    else VetoStatus.SUSPECTED
                ),
                trigger_detail=(
                    f"M9 standardization {standardization.transformed_score} < 3 and "
                    f"delivery_simplicity {delivery_simplicity.transformed_score} < 3"
                ),
                evidence_references=(
                    standardization.evidence_references + delivery_simplicity.evidence_references
                ),
            )
        )

    return VetoAssessmentResult(
        market_id=market_id,
        formula_version=formula.formula_version,
        findings=tuple(findings),
        not_evaluated=tuple(item.value for item in _NOT_EVALUATED),
    )


def _find_component(result: MethodMetricResult | None, component: str) -> ComponentBreakdown | None:
    if result is None:
        return None
    return next((item for item in result.breakdown if item.component == component), None)


def _below(component: ComponentBreakdown, threshold: Decimal) -> bool:
    return (
        component.status == ComponentStatus.AVAILABLE
        and component.transformed_score is not None
        and component.transformed_score < threshold
    )


def _all_evidence(result: MethodMetricResult) -> tuple[str, ...]:
    return tuple(
        reference
        for item in result.breakdown
        if item.status == ComponentStatus.AVAILABLE
        for reference in item.evidence_references
    )


def _is_high(confidence: ConfidenceResult | None) -> bool:
    return confidence is not None and confidence.label == ConfidenceLabel.HIGH


def _is_medium_or_high(confidence: ConfidenceResult | None) -> bool:
    return confidence is not None and confidence.label in (
        ConfidenceLabel.MEDIUM,
        ConfidenceLabel.HIGH,
    )


def _validate_formula(formula: FormulaConfiguration) -> None:
    if set(formula.vetoes) != {item.value for item in VetoId}:
        raise VetoAssessmentError("v1 veto taxonomy does not match the loaded formula")
    for veto_id, expected_trigger in _EXPECTED_TRIGGERS.items():
        if formula.vetoes[veto_id.value].trigger != expected_trigger:
            raise VetoAssessmentError(f"{veto_id} trigger text does not match v1")
