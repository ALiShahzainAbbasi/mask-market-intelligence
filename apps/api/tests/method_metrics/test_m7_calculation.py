from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.method_metrics.contracts import M7Inputs, MethodMetricStatus
from mask_api.modules.method_metrics.m7 import calculate_m7
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
M7 = FORMULAS.method_formulas[MethodId.M7]


def metric(value: Decimal, *, unit: str, geography: str = "US") -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="crm_export",
            evidence_reference=f"crm_export:{unit}:{value}",
            observation_state=ObservationState.OBSERVED,
            geography=geography,
            population="target_accounts_hvac_10_99",
            period="2026-Q1",
            unit=unit,
        ),
    )


def base_inputs(**overrides: SourcedMetric | None) -> M7Inputs:
    values: dict[str, SourcedMetric | None] = {
        "market_id": "us_hvac_10_99",
        "accounts_with_economic_buyer": metric(Decimal("50"), unit="count"),
        "target_accounts": metric(Decimal("100"), unit="count"),
        "accounts_with_valid_reachable_channel": metric(Decimal("100"), unit="count"),
        "viable_channel_count": metric(Decimal("3"), unit="count"),
        "median_days_to_decision": metric(Decimal("105"), unit="days"),
        "procurement_complexity_index_0_10": metric(Decimal("1"), unit="index_0_10"),
        "active_relevant_advertisers": metric(Decimal("10"), unit="count"),
        "account_social_presence_rate": metric(Decimal("0.60"), unit="ratio"),
    }
    values.update(overrides)
    return M7Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_six_components() -> None:
    result = calculate_m7(
        formula_version=FORMULAS.formula_version, formula=M7, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("7.10")
    buyer_identification = next(
        item for item in result.breakdown if item.component == "buyer_identification"
    )
    assert buyer_identification.raw_value == Decimal("0.5")
    assert buyer_identification.transformed_score == Decimal("5")
    procurement = next(
        item for item in result.breakdown if item.component == "procurement_simplicity"
    )
    assert procurement.transformed_score == Decimal("9")
    meta_fit = next(item for item in result.breakdown if item.component == "meta_fit")
    assert meta_fit.transformed_score == Decimal("10")


def test_zero_target_accounts_leaves_both_ratio_components_missing() -> None:
    result = calculate_m7(
        formula_version=FORMULAS.formula_version,
        formula=M7,
        inputs=base_inputs(target_accounts=metric(Decimal("0"), unit="count")),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    buyer_identification = next(
        item for item in result.breakdown if item.component == "buyer_identification"
    )
    contact_coverage = next(
        item for item in result.breakdown if item.component == "contact_coverage"
    )
    assert buyer_identification.reason == "m7.target_accounts_is_zero"
    assert contact_coverage.reason == "m7.target_accounts_is_zero"


def test_m7_has_no_provisional_state_only_unknown_or_complete() -> None:
    result = calculate_m7(
        formula_version=FORMULAS.formula_version,
        formula=M7,
        inputs=base_inputs(viable_channel_count=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.provisional_reasons == ()


def test_incompatible_geography_across_account_metrics_raises() -> None:
    with pytest.raises(ProvenanceCompatibilityError):
        calculate_m7(
            formula_version=FORMULAS.formula_version,
            formula=M7,
            inputs=base_inputs(
                target_accounts=metric(Decimal("100"), unit="count", geography="CA")
            ),
        )


def test_reachable_channel_ratio_clamps_above_one() -> None:
    result = calculate_m7(
        formula_version=FORMULAS.formula_version,
        formula=M7,
        inputs=base_inputs(
            accounts_with_valid_reachable_channel=metric(Decimal("250"), unit="count")
        ),
    )
    contact_coverage = next(
        item for item in result.breakdown if item.component == "contact_coverage"
    )
    assert contact_coverage.transformed_score == Decimal("10")
