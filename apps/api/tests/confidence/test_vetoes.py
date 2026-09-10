from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    VetoId,
    VetoStatus,
)
from mask_api.modules.confidence.vetoes import VetoAssessmentError, evaluate_automatic_vetoes
from mask_api.modules.method_metrics.contracts import (
    ComponentBreakdown,
    ComponentStatus,
    MethodMetricResult,
    MethodMetricStatus,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value


def method_result(
    method_id: MethodId,
    *,
    score: Decimal | None,
    components: dict[str, Decimal | None],
) -> MethodMetricResult:
    breakdown = tuple(
        ComponentBreakdown(
            component=name,
            status=ComponentStatus.AVAILABLE if value is not None else ComponentStatus.MISSING,
            transformed_score=value,
            weight=Decimal("0.20"),
            weighted_contribution=(value * Decimal("0.20")) if value is not None else None,
            evidence_references=(f"evidence:{name}",) if value is not None else (),
            reason=None if value is not None else f"m.{name}_missing",
        )
        for name, value in components.items()
    )
    status = MethodMetricStatus.COMPLETE if score is not None else MethodMetricStatus.UNKNOWN
    return MethodMetricResult(
        method_id=method_id,
        market_id="us_hvac",
        formula_version="v1",
        inputs_sha256="a" * 64,
        status=status,
        score=score,
        breakdown=breakdown,
        unknown_reasons=() if score is not None else ("m.required_component_missing",),
    )


def confidence(label: ConfidenceLabel) -> ConfidenceResult:
    value = {
        ConfidenceLabel.LOW: Decimal("20"),
        ConfidenceLabel.MEDIUM: Decimal("60"),
        ConfidenceLabel.HIGH: Decimal("85"),
    }[label]
    return ConfidenceResult(numeric_confidence=value, label=label)


def test_no_finding_when_nothing_is_supplied() -> None:
    result = evaluate_automatic_vetoes(FORMULAS, market_id="us_hvac")
    assert result.findings == ()
    assert set(result.not_evaluated) == {
        VetoId.MAJOR_ACCESS_OR_REGULATORY_BARRIER.value,
        VetoId.DOMINANT_PLATFORM_SOLVES_PROBLEM.value,
        VetoId.NO_QUALIFIED_BUYING_INTENT.value,
    }


def test_no_meaningful_budget_confirmed_with_high_confidence() -> None:
    m4 = method_result(
        MethodId.M4, score=Decimal("1.5"), components={"annual_burden": Decimal("1")}
    )
    result = evaluate_automatic_vetoes(
        FORMULAS,
        market_id="us_hvac",
        m4_result=m4,
        m4_confidence=confidence(ConfidenceLabel.HIGH),
    )
    finding = next(item for item in result.findings if item.veto_id == VetoId.NO_MEANINGFUL_BUDGET)
    assert finding.status == VetoStatus.CONFIRMED
    assert finding.severity == "critical"
    assert finding.evidence_references == ("evidence:annual_burden",)


def test_no_meaningful_budget_suspected_without_high_confidence() -> None:
    m4 = method_result(
        MethodId.M4, score=Decimal("1.5"), components={"annual_burden": Decimal("1")}
    )
    result = evaluate_automatic_vetoes(
        FORMULAS,
        market_id="us_hvac",
        m4_result=m4,
        m4_confidence=confidence(ConfidenceLabel.MEDIUM),
    )
    finding = next(item for item in result.findings if item.veto_id == VetoId.NO_MEANINGFUL_BUDGET)
    assert finding.status == VetoStatus.SUSPECTED

    result_no_confidence = evaluate_automatic_vetoes(FORMULAS, market_id="us_hvac", m4_result=m4)
    finding_no_confidence = next(
        item
        for item in result_no_confidence.findings
        if item.veto_id == VetoId.NO_MEANINGFUL_BUDGET
    )
    assert finding_no_confidence.status == VetoStatus.SUSPECTED


def test_no_meaningful_budget_not_raised_above_threshold() -> None:
    m4 = method_result(MethodId.M4, score=Decimal("5"), components={"annual_burden": Decimal("8")})
    result = evaluate_automatic_vetoes(
        FORMULAS, market_id="us_hvac", m4_result=m4, m4_confidence=confidence(ConfidenceLabel.HIGH)
    )
    assert not any(item.veto_id == VetoId.NO_MEANINGFUL_BUDGET for item in result.findings)


def test_no_reachable_economic_buyer_confirmed_with_high_confidence() -> None:
    m7 = method_result(
        MethodId.M7,
        score=Decimal("5"),
        components={"buyer_identification": Decimal("1")},
    )
    result = evaluate_automatic_vetoes(
        FORMULAS,
        market_id="us_hvac",
        m7_result=m7,
        m7_confidence=confidence(ConfidenceLabel.HIGH),
    )
    finding = next(
        item for item in result.findings if item.veto_id == VetoId.NO_REACHABLE_ECONOMIC_BUYER
    )
    assert finding.status == VetoStatus.CONFIRMED


def test_missing_buyer_identification_component_raises_no_finding() -> None:
    m7 = method_result(MethodId.M7, score=None, components={"buyer_identification": None})
    result = evaluate_automatic_vetoes(FORMULAS, market_id="us_hvac", m7_result=m7)
    assert not any(item.veto_id == VetoId.NO_REACHABLE_ECONOMIC_BUYER for item in result.findings)


def test_highly_bespoke_delivery_requires_both_components_below_three() -> None:
    only_one_low = method_result(
        MethodId.M9,
        score=Decimal("5"),
        components={"standardization": Decimal("2"), "delivery_simplicity": Decimal("8")},
    )
    result = evaluate_automatic_vetoes(FORMULAS, market_id="us_hvac", m9_result=only_one_low)
    assert not any(item.veto_id == VetoId.HIGHLY_BESPOKE_DELIVERY for item in result.findings)

    both_low = method_result(
        MethodId.M9,
        score=Decimal("2"),
        components={"standardization": Decimal("2"), "delivery_simplicity": Decimal("1")},
    )
    confirmed = evaluate_automatic_vetoes(
        FORMULAS,
        market_id="us_hvac",
        m9_result=both_low,
        m9_confidence=confidence(ConfidenceLabel.MEDIUM),
    )
    finding = next(
        item for item in confirmed.findings if item.veto_id == VetoId.HIGHLY_BESPOKE_DELIVERY
    )
    assert finding.status == VetoStatus.CONFIRMED  # MEDIUM confidence is sufficient here
    assert set(finding.evidence_references) == {
        "evidence:standardization",
        "evidence:delivery_simplicity",
    }

    suspected = evaluate_automatic_vetoes(FORMULAS, market_id="us_hvac", m9_result=both_low)
    suspected_finding = next(
        item for item in suspected.findings if item.veto_id == VetoId.HIGHLY_BESPOKE_DELIVERY
    )
    assert suspected_finding.status == VetoStatus.SUSPECTED


def test_trigger_text_drift_is_rejected() -> None:
    drifted = FORMULAS.model_copy(
        update={
            "vetoes": dict(
                FORMULAS.vetoes,
                no_meaningful_budget=FORMULAS.vetoes["no_meaningful_budget"].model_copy(
                    update={"trigger": "something else entirely"}
                ),
            )
        }
    )
    with pytest.raises(VetoAssessmentError):
        evaluate_automatic_vetoes(drifted, market_id="us_hvac")


def test_incomplete_veto_taxonomy_is_rejected() -> None:
    missing_one = FORMULAS.model_copy(
        update={
            "vetoes": {
                key: value
                for key, value in FORMULAS.vetoes.items()
                if key != VetoId.NO_QUALIFIED_BUYING_INTENT.value
            }
        }
    )
    with pytest.raises(VetoAssessmentError):
        evaluate_automatic_vetoes(missing_one, market_id="us_hvac")
