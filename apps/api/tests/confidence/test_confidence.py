from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.confidence.confidence import (
    ConfidenceCalculationError,
    calculate_confidence,
    sample_adequacy_score,
)
from mask_api.modules.confidence.contracts import ConfidenceDimensions, ConfidenceLabel
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
CONFIDENCE = FORMULAS.confidence


def dims(value: Decimal | None = Decimal("5")) -> ConfidenceDimensions:
    return ConfidenceDimensions(
        source_diversity_0_10=value,
        sample_adequacy_0_10=value,
        evidence_quality_0_10=value,
        recency_0_10=value,
        cross_source_agreement_0_10=value,
    )


def test_golden_weighted_aggregation() -> None:
    result = calculate_confidence(
        CONFIDENCE,
        ConfidenceDimensions(
            source_diversity_0_10=Decimal("8"),
            sample_adequacy_0_10=Decimal("6"),
            evidence_quality_0_10=Decimal("7"),
            recency_0_10=Decimal("5"),
            cross_source_agreement_0_10=Decimal("9"),
        ),
    )
    # 10*(0.25*8 + 0.25*6 + 0.20*7 + 0.10*5 + 0.20*9) = 72
    assert result.numeric_confidence == Decimal("72.00")
    assert result.label == ConfidenceLabel.MEDIUM


def test_boundary_exactly_fifty_is_medium_not_low() -> None:
    result = calculate_confidence(CONFIDENCE, dims(Decimal("5")))
    assert result.numeric_confidence == Decimal("50.00")
    assert result.label == ConfidenceLabel.MEDIUM


def test_boundary_exactly_high_at_least_is_high() -> None:
    result = calculate_confidence(CONFIDENCE, dims(Decimal("7.5")))
    assert result.numeric_confidence == Decimal("75.00")
    assert result.label == ConfidenceLabel.HIGH


def test_zero_dimensions_is_low() -> None:
    result = calculate_confidence(CONFIDENCE, dims(Decimal("0")))
    assert result.numeric_confidence == Decimal("0")
    assert result.label == ConfidenceLabel.LOW


def test_any_missing_dimension_keeps_confidence_unknown() -> None:
    missing_one = ConfidenceDimensions(
        source_diversity_0_10=Decimal("8"),
        sample_adequacy_0_10=Decimal("6"),
        evidence_quality_0_10=Decimal("7"),
        recency_0_10=None,
        cross_source_agreement_0_10=Decimal("9"),
    )
    result = calculate_confidence(CONFIDENCE, missing_one)
    assert result.numeric_confidence is None
    assert result.label is None
    assert "confidence.recency_missing" in result.unknown_reasons


def test_all_missing_dimensions_reports_every_reason() -> None:
    result = calculate_confidence(CONFIDENCE, ConfidenceDimensions())
    assert len(result.unknown_reasons) == 5


def test_sample_adequacy_single_metric_target() -> None:
    assert sample_adequacy_score(CONFIDENCE, MethodId.M2, Decimal("250")) == Decimal("5")
    assert sample_adequacy_score(CONFIDENCE, MethodId.M2, Decimal("500")) == Decimal("10")
    assert sample_adequacy_score(CONFIDENCE, MethodId.M2, Decimal("1000")) == Decimal("10")


def test_sample_adequacy_multi_metric_target_uses_best_ratio() -> None:
    score = sample_adequacy_score(
        CONFIDENCE,
        MethodId.M10,
        {"qualified_leads": Decimal("15"), "qualified_opportunities": Decimal("10")},
    )
    # ratio_score(15,30)=5, ratio_score(10,10)=10 -> best is 10
    assert score == Decimal("10")


def test_sample_adequacy_is_none_without_an_approved_target() -> None:
    assert sample_adequacy_score(CONFIDENCE, MethodId.M1, Decimal("100")) is None


def test_sample_adequacy_is_none_for_unknown_actual_count() -> None:
    assert sample_adequacy_score(CONFIDENCE, MethodId.M2, None) is None


def test_sample_adequacy_rejects_mismatched_shapes() -> None:
    with pytest.raises(ConfidenceCalculationError):
        sample_adequacy_score(CONFIDENCE, MethodId.M2, {"a": Decimal("1")})
    with pytest.raises(ConfidenceCalculationError):
        sample_adequacy_score(CONFIDENCE, MethodId.M10, Decimal("10"))
