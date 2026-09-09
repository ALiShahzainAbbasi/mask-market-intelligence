from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.method_metrics.contracts import (
    ComponentBreakdown,
    ComponentStatus,
    M1Inputs,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.m1 import calculate_m1
from mask_api.modules.method_metrics.provenance import (
    MetricProvenance,
    ObservationState,
    ProvenanceCompatibilityError,
    SourcedMetric,
)
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId
from pydantic import ValidationError

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M1 = FORMULAS.method_formulas[MethodId.M1]


def metric(
    value: Decimal,
    *,
    unit: str,
    geography: str = "US-CBSA-19100",
    population: str = "naics_23_10_99",
    period: str = "2025",
    source_id: str = "census_cbp",
) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id=source_id,
            evidence_reference=f"{source_id}:{unit}:{value}",
            observation_state=ObservationState.OBSERVED,
            geography=geography,
            population=population,
            period=period,
            unit=unit,
        ),
    )


def base_inputs(**overrides: SourcedMetric | None) -> M1Inputs:
    values: dict[str, SourcedMetric | None] = {
        "market_id": "us_hvac_10_99",
        "serviceable_businesses": metric(Decimal("100000"), unit="count"),
        "growth_cagr": metric(Decimal("0.025"), unit="ratio"),
        "fragmentation_share": metric(Decimal("0.60"), unit="ratio"),
        "annual_payroll_per_serviceable_establishment_usd": metric(Decimal("100000"), unit="usd"),
        "target_band_share": metric(Decimal("0.225"), unit="ratio"),
    }
    values.update(overrides)
    return M1Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_five_components() -> None:
    result = calculate_m1(
        formula_version=FORMULAS.formula_version, formula=M1, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("5.5")
    assert result.method_id == MethodId.M1
    buyer_pool = next(item for item in result.breakdown if item.component == "buyer_pool")
    assert buyer_pool.transformed_score == Decimal("10")
    assert buyer_pool.weighted_contribution == Decimal("3.0")


def test_target_band_share_special_case_all_firms_still_scores_ten() -> None:
    result = calculate_m1(
        formula_version=FORMULAS.formula_version,
        formula=M1,
        inputs=base_inputs(target_band_share=metric(Decimal("1.0"), unit="ratio")),
    )
    target_band = next(item for item in result.breakdown if item.component == "target_band_match")
    assert target_band.transformed_score == Decimal("10")


def test_missing_serviceable_businesses_is_unknown_regardless_of_optional_components() -> None:
    result = calculate_m1(
        formula_version=FORMULAS.formula_version,
        formula=M1,
        inputs=base_inputs(serviceable_businesses=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    assert "m1.serviceable_businesses_unavailable" in result.unknown_reasons


def test_exactly_three_of_four_optional_components_is_provisional() -> None:
    result = calculate_m1(
        formula_version=FORMULAS.formula_version,
        formula=M1,
        inputs=base_inputs(target_band_share=None),
    )
    assert result.status == MethodMetricStatus.PROVISIONAL
    assert result.score is not None
    assert "m1.fewer_than_four_optional_components" in result.provisional_reasons
    missing = next(item for item in result.breakdown if item.component == "target_band_match")
    assert missing.reason == "m1.target_band_share_missing"


def test_fewer_than_three_optional_components_is_unknown() -> None:
    result = calculate_m1(
        formula_version=FORMULAS.formula_version,
        formula=M1,
        inputs=base_inputs(target_band_share=None, fragmentation_share=None),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    assert "m1.fewer_than_three_optional_components" in result.unknown_reasons


def test_incompatible_geography_across_components_raises() -> None:
    with pytest.raises(ProvenanceCompatibilityError):
        calculate_m1(
            formula_version=FORMULAS.formula_version,
            formula=M1,
            inputs=base_inputs(
                growth_cagr=metric(Decimal("0.025"), unit="ratio", geography="US-CBSA-99999")
            ),
        )


def test_reproducible_inputs_hash_is_stable_across_key_order() -> None:
    first = calculate_m1(formula_version=FORMULAS.formula_version, formula=M1, inputs=base_inputs())
    second = calculate_m1(
        formula_version=FORMULAS.formula_version, formula=M1, inputs=base_inputs()
    )
    assert first.inputs_sha256 == second.inputs_sha256
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_mismatched_formula_components_are_rejected() -> None:
    bad = M1.model_copy(
        update={"components": dict(M1.components, extra=next(iter(M1.components.values())))}
    )
    with pytest.raises(ValueError):
        calculate_m1(formula_version=FORMULAS.formula_version, formula=bad, inputs=base_inputs())


def test_component_breakdown_requires_evidence_reference_when_available() -> None:
    with pytest.raises(ValidationError):
        ComponentBreakdown(
            component="buyer_pool",
            status=ComponentStatus.AVAILABLE,
            raw_value=Decimal("1"),
            transformed_score=Decimal("1"),
            weight=Decimal("0.30"),
            weighted_contribution=Decimal("0.30"),
            evidence_references=(),
        )
