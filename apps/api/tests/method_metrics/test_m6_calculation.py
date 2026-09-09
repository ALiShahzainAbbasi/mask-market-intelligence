from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from mask_api.modules.method_metrics.contracts import M6Inputs, MethodMetricStatus
from mask_api.modules.method_metrics.m6 import calculate_m6
from mask_api.modules.method_metrics.provenance import (
    MetricProvenance,
    ObservationState,
    SourcedMetric,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M6 = FORMULAS.method_formulas[MethodId.M6]


def metric(value: Decimal, *, unit: str, currency: str | None = None) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="google_ads_keyword_planner",
            evidence_reference=f"google_ads:{unit}:{value}",
            observation_state=ObservationState.OBSERVED,
            geography="US",
            population="qualified_keywords",
            period="trailing_12_months",
            currency=currency,
            unit=unit,
        ),
    )


def base_inputs(**overrides: SourcedMetric | None) -> M6Inputs:
    values: dict[str, SourcedMetric | None] = {
        "market_id": "us_hvac_10_99",
        "weighted_monthly_volume": metric(Decimal("100000"), unit="searches_per_month"),
        "weighted_avg_cpc_usd": metric(Decimal("1"), unit="usd", currency="USD"),
        "high_intent_share": metric(Decimal("0.5"), unit="ratio"),
        "growth": metric(Decimal("0.05"), unit="ratio"),
        "switching_share": metric(Decimal("0.08"), unit="ratio"),
        "qualified_keyword_count": metric(Decimal("100"), unit="count"),
    }
    values.update(overrides)
    return M6Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_five_components() -> None:
    result = calculate_m6(
        formula_version=FORMULAS.formula_version, formula=M6, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("5.25")


def test_below_100_qualified_keywords_is_provisional() -> None:
    result = calculate_m6(
        formula_version=FORMULAS.formula_version,
        formula=M6,
        inputs=base_inputs(qualified_keyword_count=metric(Decimal("40"), unit="count")),
    )
    assert result.status == MethodMetricStatus.PROVISIONAL
    assert "m6.keyword_sample_below_100" in result.provisional_reasons


def test_missing_qualified_keyword_count_is_unknown_even_with_all_components_present() -> None:
    result = calculate_m6(
        formula_version=FORMULAS.formula_version,
        formula=M6,
        inputs=base_inputs(qualified_keyword_count=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    assert "m6.qualified_keyword_count_missing" in result.unknown_reasons


def test_missing_switching_share_is_unknown() -> None:
    result = calculate_m6(
        formula_version=FORMULAS.formula_version,
        formula=M6,
        inputs=base_inputs(switching_share=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    missing = next(item for item in result.breakdown if item.component == "switching_demand")
    assert missing.reason == "m6.switching_share_missing"


def test_negative_trend_is_still_within_bounds_and_scores_zero() -> None:
    result = calculate_m6(
        formula_version=FORMULAS.formula_version,
        formula=M6,
        inputs=base_inputs(growth=metric(Decimal("-0.20"), unit="ratio")),
    )
    trend = next(item for item in result.breakdown if item.component == "trend")
    assert trend.transformed_score == Decimal("0")
