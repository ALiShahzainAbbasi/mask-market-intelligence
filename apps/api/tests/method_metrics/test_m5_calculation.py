from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.method_metrics.contracts import M5CompetitorGap, M5Inputs, MethodMetricStatus
from mask_api.modules.method_metrics.m5 import calculate_m5
from mask_api.modules.method_metrics.provenance import (
    MetricProvenance,
    ObservationState,
    SourcedMetric,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId
from pydantic import ValidationError

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M5 = FORMULAS.method_formulas[MethodId.M5]


def metric(value: Decimal, *, unit: str, currency: str | None = None) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="analyst_upload",
            evidence_reference=f"analyst_upload:{unit}:{value}",
            observation_state=ObservationState.OBSERVED,
            geography="US",
            population="direct_ai_vendors_and_alternatives",
            period="2026-Q1",
            currency=currency,
            unit=unit,
        ),
    )


def gap(competitor_id: str, score: Decimal, evidence_count: int) -> M5CompetitorGap:
    return M5CompetitorGap(
        competitor_id=competitor_id,
        gap_score_0_10=score,
        evidence_count=evidence_count,
        evidence_references=(f"analyst_upload:{competitor_id}",),
    )


THREE_GAPS = (
    gap("competitor_a", Decimal("8"), 4),
    gap("competitor_b", Decimal("6"), 4),
    gap("competitor_c", Decimal("4"), 1),
)


def base_inputs(**overrides: object) -> M5Inputs:
    values: dict[str, object] = {
        "market_id": "us_hvac_10_99",
        "active_relevant_competitor_count": metric(Decimal("50"), unit="count"),
        "median_annualized_customer_price_usd": metric(Decimal("500"), unit="usd", currency="USD"),
        "competitor_gaps": THREE_GAPS,
        "median_offer_similarity_0_1": metric(Decimal("0.5"), unit="ratio"),
        "verified_reference_count": metric(Decimal("100"), unit="count"),
    }
    values.update(overrides)
    return M5Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_five_components() -> None:
    result = calculate_m5(
        formula_version=FORMULAS.formula_version, formula=M5, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("6.845")
    gap_component = next(item for item in result.breakdown if item.component == "unresolved_gap")
    assert gap_component.transformed_score == Decimal("6.4")
    differentiation = next(
        item for item in result.breakdown if item.component == "differentiation_space"
    )
    assert differentiation.transformed_score == Decimal("9.5")


def test_below_twenty_competitors_is_provisional_not_unknown() -> None:
    result = calculate_m5(
        formula_version=FORMULAS.formula_version,
        formula=M5,
        inputs=base_inputs(active_relevant_competitor_count=metric(Decimal("5"), unit="count")),
    )
    assert result.status == MethodMetricStatus.PROVISIONAL
    assert result.score is not None
    assert "m5.competitor_sample_below_20" in result.provisional_reasons


def test_missing_competitor_gap_findings_is_unknown() -> None:
    result = calculate_m5(
        formula_version=FORMULAS.formula_version,
        formula=M5,
        inputs=base_inputs(competitor_gaps=()),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    missing = next(item for item in result.breakdown if item.component == "unresolved_gap")
    assert missing.reason == "m5.competitor_gap_findings_missing"


def test_only_top_five_gaps_are_used_extras_do_not_inflate_the_score() -> None:
    six_gaps = THREE_GAPS + (
        gap("competitor_d", Decimal("3"), 1),
        gap("competitor_e", Decimal("2"), 1),
        gap("competitor_f", Decimal("1"), 100),  # huge evidence weight, still ranked 6th by score
    )
    with_six = calculate_m5(
        formula_version=FORMULAS.formula_version,
        formula=M5,
        inputs=base_inputs(competitor_gaps=six_gaps),
    )
    with_top_five_only = calculate_m5(
        formula_version=FORMULAS.formula_version,
        formula=M5,
        inputs=base_inputs(competitor_gaps=THREE_GAPS + six_gaps[3:5]),
    )
    assert with_six.score == with_top_five_only.score


def test_duplicate_competitor_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        base_inputs(competitor_gaps=THREE_GAPS + (gap("competitor_a", Decimal("9"), 2),))


def test_zero_active_competitor_count_floors_the_log_scale_component_to_zero() -> None:
    result = calculate_m5(
        formula_version=FORMULAS.formula_version,
        formula=M5,
        inputs=base_inputs(active_relevant_competitor_count=metric(Decimal("0"), unit="count")),
    )
    competitor_proof = next(
        item for item in result.breakdown if item.component == "competitor_proof"
    )
    assert competitor_proof.transformed_score == Decimal("0")
    assert result.status == MethodMetricStatus.PROVISIONAL
