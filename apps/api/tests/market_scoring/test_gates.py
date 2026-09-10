from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    MethodStatusSnapshot,
    VetoAssessmentResult,
    VetoFinding,
    VetoId,
    VetoStatus,
)
from mask_api.modules.market_scoring.contracts import GateId, GateResultStatus
from mask_api.modules.market_scoring.gates import evaluate_all_gates, evaluate_gate
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
OVERALL_WEIGHTS = dict(FORMULAS.overall_weights)
CONFIDENCE_CONFIG = FORMULAS.confidence
NO_VETOES = VetoAssessmentResult(
    market_id="us_hvac", formula_version="v1", findings=(), not_evaluated=()
)


def confidence(numeric: Decimal) -> ConfidenceResult:
    label = ConfidenceLabel.HIGH if numeric >= Decimal("75") else ConfidenceLabel.MEDIUM
    if numeric < Decimal("50"):
        label = ConfidenceLabel.LOW
    return ConfidenceResult(numeric_confidence=numeric, label=label)


def snapshot(
    method_id: MethodId, *, score: Decimal | None, numeric_confidence: Decimal | None
) -> MethodStatusSnapshot:
    status = "complete" if score is not None else "unknown"
    return MethodStatusSnapshot(
        method_id=method_id,
        status=status,
        score=score,
        completeness=classify_completeness(status),
        confidence=confidence(numeric_confidence) if numeric_confidence is not None else None,
    )


def all_ten(*, score: Decimal, numeric_confidence: Decimal) -> dict[MethodId, MethodStatusSnapshot]:
    methods = {
        method: snapshot(method, score=score, numeric_confidence=numeric_confidence)
        for method in MethodId
    }
    methods[MethodId.M8] = snapshot(MethodId.M8, score=None, numeric_confidence=None)
    methods[MethodId.M10] = snapshot(MethodId.M10, score=None, numeric_confidence=None)
    return methods


def test_gate_1_eligible_with_constant_score_above_minimum() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    result = evaluate_gate(
        GateId.GATE_1,
        FORMULAS.gates["gate_1"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=NO_VETOES,
    )
    assert result.status == GateResultStatus.ELIGIBLE_TO_ADVANCE
    assert result.gate_score == Decimal("8")
    assert result.gate_confidence is not None
    assert result.gate_confidence.label == ConfidenceLabel.HIGH
    assert result.unresolved_reasons == ()


def test_gate_2_not_ready_when_m8_is_missing() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    result = evaluate_gate(
        GateId.GATE_2,
        FORMULAS.gates["gate_2"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=NO_VETOES,
    )
    assert result.status == GateResultStatus.NOT_READY
    assert MethodId.M8 in result.missing_methods
    assert result.gate_score is None
    assert "gate.required_method_score_missing" in result.unresolved_reasons


def test_gate_does_not_meet_gate_when_score_below_minimum() -> None:
    methods = all_ten(score=Decimal("3"), numeric_confidence=Decimal("80"))
    result = evaluate_gate(
        GateId.GATE_1,
        FORMULAS.gates["gate_1"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=NO_VETOES,
    )
    assert result.status == GateResultStatus.DOES_NOT_MEET_GATE
    assert result.gate_score == Decimal("3")
    assert "gate.minimum_score_not_met" in result.unresolved_reasons


def test_gate_not_ready_when_confidence_below_minimum() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("20"))
    result = evaluate_gate(
        GateId.GATE_2,
        FORMULAS.gates["gate_2"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods={
            **methods,
            MethodId.M8: snapshot(
                MethodId.M8, score=Decimal("8"), numeric_confidence=Decimal("20")
            ),
        },
        vetoes=NO_VETOES,
    )
    assert result.status == GateResultStatus.NOT_READY
    assert result.gate_score is not None  # computed before the confidence check
    assert "gate.confidence_below_minimum" in result.unresolved_reasons


def test_gate_4_eligible_when_score_meets_the_preference_exactly() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("90"))
    full = {
        **methods,
        MethodId.M8: snapshot(MethodId.M8, score=Decimal("8"), numeric_confidence=Decimal("90")),
        MethodId.M10: snapshot(MethodId.M10, score=Decimal("8"), numeric_confidence=Decimal("90")),
    }
    result = evaluate_gate(
        GateId.GATE_4,
        FORMULAS.gates["gate_4"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=full,
        vetoes=NO_VETOES,
    )
    # A constant 8 across all ten methods meets gate_4's 8.0 preference exactly.
    assert result.gate_score == Decimal("8")
    assert result.status == GateResultStatus.ELIGIBLE_TO_ADVANCE


def test_gate_4_founder_review_required_when_score_below_preference() -> None:
    methods = all_ten(score=Decimal("7"), numeric_confidence=Decimal("90"))
    full = {
        **methods,
        MethodId.M8: snapshot(MethodId.M8, score=Decimal("7"), numeric_confidence=Decimal("90")),
        MethodId.M10: snapshot(MethodId.M10, score=Decimal("7"), numeric_confidence=Decimal("90")),
    }
    result = evaluate_gate(
        GateId.GATE_4,
        FORMULAS.gates["gate_4"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=full,
        vetoes=NO_VETOES,
    )
    assert result.status == GateResultStatus.FOUNDER_REVIEW_REQUIRED
    assert "gate.preferred_score_not_met" in result.unresolved_reasons


def test_gate_blocked_by_confirmed_critical_veto_even_with_a_perfect_score() -> None:
    methods = all_ten(score=Decimal("10"), numeric_confidence=Decimal("95"))
    vetoes = VetoAssessmentResult(
        market_id="us_hvac",
        formula_version="v1",
        findings=(
            VetoFinding(
                veto_id=VetoId.NO_MEANINGFUL_BUDGET,
                severity="critical",
                status=VetoStatus.CONFIRMED,
                trigger_detail="M4 score 1 < 2",
                evidence_references=("evidence:m4",),
            ),
        ),
        not_evaluated=(),
    )
    result = evaluate_gate(
        GateId.GATE_1,
        FORMULAS.gates["gate_1"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=vetoes,
    )
    assert result.status == GateResultStatus.BLOCKED
    assert result.gate_score is None
    assert "veto.no_meaningful_budget_confirmed" in result.unresolved_reasons


def test_suspected_veto_does_not_block() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    vetoes = VetoAssessmentResult(
        market_id="us_hvac",
        formula_version="v1",
        findings=(
            VetoFinding(
                veto_id=VetoId.NO_MEANINGFUL_BUDGET,
                severity="critical",
                status=VetoStatus.SUSPECTED,
                trigger_detail="M4 score 1 < 2",
                evidence_references=("evidence:m4",),
            ),
        ),
        not_evaluated=(),
    )
    result = evaluate_gate(
        GateId.GATE_1,
        FORMULAS.gates["gate_1"],
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=vetoes,
    )
    assert result.status == GateResultStatus.ELIGIBLE_TO_ADVANCE


def test_evaluate_all_gates_covers_all_four() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    results = evaluate_all_gates(
        dict(FORMULAS.gates),
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        methods=methods,
        vetoes=NO_VETOES,
    )
    assert {item.gate_id for item in results} == set(GateId)
