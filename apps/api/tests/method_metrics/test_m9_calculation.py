from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.method_metrics.contracts import (
    CapabilityCoverage,
    CapabilityRequirement,
    IntegrationRecord,
    M9Inputs,
    MethodMetricStatus,
)
from mask_api.modules.method_metrics.m9 import calculate_m9
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
M9 = FORMULAS.method_formulas[MethodId.M9]


def metric(value: Decimal, *, unit: str) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="technical_review",
            evidence_reference=f"technical_review:{unit}:{value}",
            observation_state=ObservationState.OBSERVED,
            geography="US",
            population="mask_ai_capability_registry",
            period="2026-Q1",
            unit=unit,
        ),
    )


THREE_REQUIREMENTS = (
    CapabilityRequirement(
        capability_id="dispatch_automation",
        description="automate dispatch scheduling",
        required_weight=Decimal("1"),
        evidence_reference="registry:dispatch_automation",
    ),
    CapabilityRequirement(
        capability_id="invoice_sync",
        description="sync invoices to accounting software",
        required_weight=Decimal("1"),
        evidence_reference="registry:invoice_sync",
    ),
    CapabilityRequirement(
        capability_id="call_transcription",
        description="transcribe inbound calls",
        required_weight=Decimal("2"),
        evidence_reference="registry:call_transcription",
    ),
)
FULL_COVERAGE = tuple(
    CapabilityCoverage(
        capability_id=item.capability_id,
        covered=True,
        evidence_reference=f"coverage:{item.capability_id}",
        source_id="technical_review",
    )
    for item in THREE_REQUIREMENTS
)
INTEGRATIONS = (
    IntegrationRecord(
        platform_id="quickbooks",
        platform_name="QuickBooks",
        target_market_prevalence_0_1=Decimal("0.5"),
        supported=True,
        evidence_reference="integration_discovery:quickbooks",
        source_id="integration_discovery",
    ),
    IntegrationRecord(
        platform_id="servicetitan",
        platform_name="ServiceTitan",
        target_market_prevalence_0_1=Decimal("0.3"),
        supported=False,
        evidence_reference="integration_discovery:servicetitan",
        source_id="integration_discovery",
    ),
)


def base_inputs(**overrides: object) -> M9Inputs:
    values: dict[str, object] = {
        "market_id": "us_hvac_10_99",
        "capability_requirements": THREE_REQUIREMENTS,
        "capability_coverage": FULL_COVERAGE,
        "integrations": INTEGRATIONS,
        "workflow_template_similarity_0_1": metric(Decimal("0.7"), unit="ratio"),
        "recurring_solution_value_share": metric(Decimal("0.50"), unit="ratio"),
        "comparable_internal_project_count": metric(Decimal("10"), unit="count"),
        "delivery_complexity_index_0_10": metric(Decimal("2"), unit="index_0_10"),
        "adjacent_high_value_workflow_count": metric(Decimal("6"), unit="count"),
    }
    values.update(overrides)
    return M9Inputs(**values)  # type: ignore[arg-type]


def test_golden_weighted_sum_with_all_seven_components() -> None:
    result = calculate_m9(
        formula_version=FORMULAS.formula_version, formula=M9, inputs=base_inputs()
    )
    assert result.status == MethodMetricStatus.COMPLETE
    assert result.score == Decimal("7.85")
    technical_fit = next(item for item in result.breakdown if item.component == "technical_fit")
    assert technical_fit.transformed_score == Decimal("10")
    integration_fit = next(item for item in result.breakdown if item.component == "integration_fit")
    assert integration_fit.raw_value == Decimal("0.5")
    assert integration_fit.transformed_score == Decimal("5")


def test_partial_capability_coverage_keeps_the_whole_method_unknown() -> None:
    partial_coverage = FULL_COVERAGE[:-1]  # missing coverage for call_transcription
    result = calculate_m9(
        formula_version=FORMULAS.formula_version,
        formula=M9,
        inputs=base_inputs(capability_coverage=partial_coverage),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    assert result.score is None
    technical_fit = next(item for item in result.breakdown if item.component == "technical_fit")
    assert technical_fit.reason == "m9.capability_coverage_incomplete"
    assert "m9.required_component_missing" in result.unknown_reasons


def test_uncovered_capability_lowers_technical_fit_without_dropping_it() -> None:
    mixed_coverage = FULL_COVERAGE[:-1] + (
        CapabilityCoverage(
            capability_id="call_transcription",
            covered=False,
            evidence_reference="coverage:call_transcription",
            source_id="technical_review",
        ),
    )
    result = calculate_m9(
        formula_version=FORMULAS.formula_version,
        formula=M9,
        inputs=base_inputs(capability_coverage=mixed_coverage),
    )
    technical_fit = next(item for item in result.breakdown if item.component == "technical_fit")
    # weighted_coverage = 10*(1*1 + 1*1 + 2*0)/4 = 5
    assert technical_fit.transformed_score == Decimal("5")
    assert result.status == MethodMetricStatus.COMPLETE


def test_no_capability_requirements_is_unknown() -> None:
    result = calculate_m9(
        formula_version=FORMULAS.formula_version,
        formula=M9,
        inputs=base_inputs(capability_requirements=(), capability_coverage=()),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    technical_fit = next(item for item in result.breakdown if item.component == "technical_fit")
    assert technical_fit.reason == "m9.no_capability_requirements"


def test_no_integration_records_is_unknown() -> None:
    result = calculate_m9(
        formula_version=FORMULAS.formula_version,
        formula=M9,
        inputs=base_inputs(integrations=()),
    )
    assert result.status == MethodMetricStatus.UNKNOWN
    integration_fit = next(item for item in result.breakdown if item.component == "integration_fit")
    assert integration_fit.reason == "m9.no_integration_records"


def test_zero_comparable_projects_floors_log_scale_component() -> None:
    result = calculate_m9(
        formula_version=FORMULAS.formula_version,
        formula=M9,
        inputs=base_inputs(comparable_internal_project_count=metric(Decimal("0"), unit="count")),
    )
    proof_potential = next(item for item in result.breakdown if item.component == "proof_potential")
    assert proof_potential.transformed_score == Decimal("0")


def test_duplicate_capability_requirement_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        base_inputs(capability_requirements=THREE_REQUIREMENTS + (THREE_REQUIREMENTS[0],))


def test_duplicate_integration_platform_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        base_inputs(integrations=INTEGRATIONS + (INTEGRATIONS[0],))


def test_integration_prevalence_cannot_exceed_total_market() -> None:
    over_allocated = INTEGRATIONS + (
        IntegrationRecord(
            platform_id="jobber",
            platform_name="Jobber",
            target_market_prevalence_0_1=Decimal("0.3"),
            supported=True,
            evidence_reference="integration_discovery:jobber",
            source_id="integration_discovery",
        ),
    )
    with pytest.raises(ValidationError):
        base_inputs(integrations=over_allocated)


def test_reproducible_across_repeated_calculation() -> None:
    first = calculate_m9(formula_version=FORMULAS.formula_version, formula=M9, inputs=base_inputs())
    second = calculate_m9(
        formula_version=FORMULAS.formula_version, formula=M9, inputs=base_inputs()
    )
    assert first.inputs_sha256 == second.inputs_sha256
    assert first.score == second.score
