from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    MethodStatusSnapshot,
)
from mask_api.modules.market_scoring.scoring import (
    MarketScoringError,
    aggregate_confidence,
    calculate_automated_research_score,
    risk_adjusted_method_score,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
OVERALL_WEIGHTS = dict(FORMULAS.overall_weights)
CONFIDENCE_CONFIG = FORMULAS.confidence

_PRESENT_METHODS = (
    MethodId.M1,
    MethodId.M2,
    MethodId.M3,
    MethodId.M4,
    MethodId.M5,
    MethodId.M6,
    MethodId.M7,
    MethodId.M9,
)


def confidence(numeric: Decimal | None) -> ConfidenceResult | None:
    if numeric is None:
        return None
    return ConfidenceResult(
        numeric_confidence=numeric,
        label=ConfidenceLabel.HIGH if numeric >= Decimal("75") else ConfidenceLabel.MEDIUM,
    )


def snapshot(
    method_id: MethodId,
    *,
    score: Decimal | None,
    numeric_confidence: Decimal | None,
) -> MethodStatusSnapshot:
    status = "complete" if score is not None else "unknown"
    return MethodStatusSnapshot(
        method_id=method_id,
        status=status,
        score=score,
        completeness=classify_completeness(status),
        confidence=confidence(numeric_confidence),
    )


def all_ten(*, score: Decimal, numeric_confidence: Decimal) -> dict[MethodId, MethodStatusSnapshot]:
    methods = {
        method: snapshot(method, score=score, numeric_confidence=numeric_confidence)
        for method in _PRESENT_METHODS
    }
    methods[MethodId.M8] = snapshot(MethodId.M8, score=None, numeric_confidence=None)
    methods[MethodId.M10] = snapshot(MethodId.M10, score=None, numeric_confidence=None)
    return methods


def test_golden_automated_research_score_is_the_raw_weighted_sum() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    score, observed_weight, contributing, missing = calculate_automated_research_score(
        OVERALL_WEIGHTS, methods
    )
    # A constant score of 8 across every contributing method: the weighted
    # sum collapses to 8 * observed_weight regardless of individual weights.
    expected_weight = Decimal("1") - OVERALL_WEIGHTS[MethodId.M8] - OVERALL_WEIGHTS[MethodId.M10]
    assert observed_weight == expected_weight
    assert score == Decimal("8") * expected_weight
    assert set(contributing) == set(_PRESENT_METHODS)
    assert set(missing) == {MethodId.M8, MethodId.M10}


def test_automated_research_score_is_none_with_no_contributing_methods() -> None:
    methods = {method: snapshot(method, score=None, numeric_confidence=None) for method in MethodId}
    score, observed_weight, contributing, missing = calculate_automated_research_score(
        OVERALL_WEIGHTS, methods
    )
    assert score is None
    assert observed_weight == Decimal("0")
    assert contributing == ()
    assert set(missing) == set(MethodId)


def test_automated_research_score_never_renormalizes() -> None:
    single = {
        MethodId.M9: snapshot(MethodId.M9, score=Decimal("10"), numeric_confidence=Decimal("90"))
    }
    score, observed_weight, contributing, _ = calculate_automated_research_score(
        OVERALL_WEIGHTS, single
    )
    # M9's own weight is 0.05: a perfect M9 score alone must not look like a
    # complete market score of 10.
    assert observed_weight == OVERALL_WEIGHTS[MethodId.M9]
    assert score == Decimal("10") * OVERALL_WEIGHTS[MethodId.M9]
    assert score < Decimal("1")
    assert contributing == (MethodId.M9,)


def test_golden_gate_confidence_aggregation() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    result = aggregate_confidence(
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        required_methods=_PRESENT_METHODS,
        methods=methods,
    )
    # A constant confidence of 80 across every required method collapses to
    # 80 regardless of the renormalized weights.
    assert result.numeric_confidence == Decimal("80")
    assert result.label == ConfidenceLabel.HIGH


def test_confidence_aggregation_is_unknown_if_any_required_method_lacks_confidence() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    result = aggregate_confidence(
        confidence_config=CONFIDENCE_CONFIG,
        overall_weights=OVERALL_WEIGHTS,
        required_methods=tuple(MethodId),  # includes M8/M10, which have no confidence
        methods=methods,
    )
    assert result.numeric_confidence is None
    assert result.label is None
    assert "confidence.M8_missing" in result.unknown_reasons
    assert "confidence.M10_missing" in result.unknown_reasons


def test_confidence_aggregation_rejects_empty_required_methods() -> None:
    with pytest.raises(MarketScoringError):
        aggregate_confidence(
            confidence_config=CONFIDENCE_CONFIG,
            overall_weights=OVERALL_WEIGHTS,
            required_methods=(),
            methods={},
        )


def test_risk_adjusted_score_matches_the_approved_formula() -> None:
    # RawMethodScore * (0.70 + 0.30 * Confidence/100)
    result = risk_adjusted_method_score(Decimal("8"), confidence(Decimal("80")))
    assert result == Decimal("8") * (Decimal("0.70") + Decimal("0.30") * Decimal("0.80"))


def test_risk_adjusted_score_is_unknown_without_either_input() -> None:
    assert risk_adjusted_method_score(None, confidence(Decimal("80"))) is None
    assert risk_adjusted_method_score(Decimal("8"), None) is None
    unknown_confidence = ConfidenceResult(unknown_reasons=("confidence.recency_missing",))
    assert risk_adjusted_method_score(Decimal("8"), unknown_confidence) is None
