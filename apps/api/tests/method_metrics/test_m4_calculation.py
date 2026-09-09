from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.method_metrics.contracts import M4Inputs, MethodMetricStatus
from mask_api.modules.method_metrics.m4 import calculate_m4
from mask_api.modules.method_metrics.provenance import (
    MetricProvenance,
    ObservationState,
    ProvenanceCompatibilityError,
    SourcedMetric,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M4 = FORMULAS.method_formulas[MethodId.M4]


def metric(
    value: Decimal,
    *,
    unit: str,
    currency: str | None = None,
    period: str = "2025",
    observation_state: ObservationState = ObservationState.OBSERVED,
) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="analyst_upload",
            evidence_reference=f"analyst_upload:{unit}:{value}",
            observation_state=observation_state,
            geography="US-CBSA-19100",
            population="naics_23_10_99",
            period=period,
            currency=currency,
            unit=unit,
        ),
    )


def base_inputs(**overrides: SourcedMetric | None) -> M4Inputs:
    values: dict[str, SourcedMetric | None] = {
        "market_id": "us_hvac_10_99",
        "annual_problem_cost_usd": metric(Decimal("250000"), unit="usd", currency="USD"),
        "annual_existing_paid_spend_usd": metric(Decimal("1000"), unit="usd", currency="USD"),
        "verified_paid_workaround_share": metric(Decimal("0.275"), unit="ratio"),
        "mean_m2_purchase_intent_0_4": metric(Decimal("2"), unit="scale_0_4"),
    }
    values.update(overrides)
    return M4Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_four_components() -> None:
    result = calculate_m4(
        formula_version=FORMULAS.formula_version, formula=M4, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("5.5")
    intent = next(item for item in result.breakdown if item.component == "commercial_intent")
    assert intent.transformed_score == Decimal("5")
    assert intent.weighted_contribution == Decimal("0.75")


def test_m4_has_no_provisional_state_only_unknown_or_complete() -> None:
    result = calculate_m4(
        formula_version=FORMULAS.formula_version,
        formula=M4,
        inputs=base_inputs(annual_existing_paid_spend_usd=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    assert result.provisional_reasons == ()
    assert "m4.required_component_missing" in result.unknown_reasons
    missing = next(item for item in result.breakdown if item.component == "existing_paid_spend")
    assert missing.reason == "m4.annual_existing_paid_spend_usd_missing"


def test_incompatible_currency_across_monetary_components_raises() -> None:
    with pytest.raises(ProvenanceCompatibilityError):
        calculate_m4(
            formula_version=FORMULAS.formula_version,
            formula=M4,
            inputs=base_inputs(
                annual_existing_paid_spend_usd=metric(Decimal("1000"), unit="usd", currency="EUR")
            ),
        )


def test_incompatible_period_across_monetary_components_raises() -> None:
    with pytest.raises(ProvenanceCompatibilityError):
        calculate_m4(
            formula_version=FORMULAS.formula_version,
            formula=M4,
            inputs=base_inputs(
                annual_existing_paid_spend_usd=metric(
                    Decimal("1000"), unit="usd", currency="USD", period="2024"
                )
            ),
        )


def test_estimated_observation_state_is_still_a_valid_input() -> None:
    result = calculate_m4(
        formula_version=FORMULAS.formula_version,
        formula=M4,
        inputs=base_inputs(
            annual_problem_cost_usd=metric(
                Decimal("250000"),
                unit="usd",
                currency="USD",
                observation_state=ObservationState.ESTIMATED,
            )
        ),
    )
    assert result.status == MethodMetricStatus.COMPLETE


def test_reproducible_across_repeated_calculation() -> None:
    first = calculate_m4(formula_version=FORMULAS.formula_version, formula=M4, inputs=base_inputs())
    second = calculate_m4(
        formula_version=FORMULAS.formula_version, formula=M4, inputs=base_inputs()
    )
    assert first.inputs_sha256 == second.inputs_sha256
    assert first.score == second.score
