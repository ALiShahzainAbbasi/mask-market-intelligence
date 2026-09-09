from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.evidence.domain import EvidencePersona
from mask_api.modules.scoring.math import clamp10, weighted_mean
from mask_api.modules.workflow_intelligence.contracts import (
    M3Status,
    WorkflowContradiction,
    WorkflowStepEvidence,
)
from mask_api.modules.workflow_intelligence.metrics import calculate_m3
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M3 = FORMULAS.method_formulas[MethodId.M3]


def step(
    *,
    step_name: str,
    document_id: str,
    events_per_month: Decimal | None,
    labor_hours_per_month: Decimal | None,
    failure_rate: Decimal | None,
    consequence_score: Decimal | None,
    automation_potential: Decimal | None,
    manual_share: Decimal | None,
    source_family: str = "analyst_upload",
    persona: EvidencePersona = EvidencePersona.OWNER,
    confidence: Decimal = Decimal("0.9"),
) -> WorkflowStepEvidence:
    normalized = step_name.strip().casefold()
    normalized_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    evidence_id = hashlib.sha256(f"{document_id}:{step_name}".encode()).hexdigest()
    return WorkflowStepEvidence(
        evidence_id=evidence_id,
        market_id="us_hvac",
        document_id=document_id,
        normalized_document_sha256=hashlib.sha256(document_id.encode()).hexdigest(),
        analysis_cache_key=hashlib.sha256(f"analysis-{document_id}".encode()).hexdigest(),
        grounding_version="grounding-v1",
        source_family=source_family,
        persona=persona,
        source_date=date(2026, 8, 1),
        step_name=step_name,
        normalized_step_name=normalized,
        normalized_step_name_sha256=normalized_hash,
        role="dispatcher",
        system="quickbooks",
        input_description="job ticket",
        output_description="invoice",
        events_per_month=events_per_month,
        labor_hours_per_month=labor_hours_per_month,
        waiting_time_minutes=Decimal("15"),
        failure_rate=failure_rate,
        consequence_description="customer billing delay",
        consequence_score=consequence_score,
        workaround="manual spreadsheet",
        automation_potential=automation_potential,
        manual_share=manual_share,
        evidence_span="dispatcher re-keys the job ticket into QuickBooks by hand",
        extraction_confidence=confidence,
    )


def _full(
    step_name: str,
    document_id: str,
    *,
    volume: Decimal,
    labor: Decimal,
    failure: Decimal,
    consequence: Decimal,
    automation: Decimal,
    manuality: Decimal,
) -> WorkflowStepEvidence:
    return step(
        step_name=step_name,
        document_id=document_id,
        events_per_month=volume,
        labor_hours_per_month=labor,
        failure_rate=failure,
        consequence_score=consequence,
        automation_potential=automation,
        manual_share=manuality,
    )


def test_golden_top_five_of_six_bottlenecks_and_component_breakdown() -> None:
    max_step = tuple(
        _full(
            "manual_invoice_re_entry",
            f"doc-max-{index}",
            volume=Decimal("10000"),
            labor=Decimal("1000"),
            failure=Decimal("0.20"),
            consequence=Decimal("10"),
            automation=Decimal("10"),
            manuality=Decimal("1.00"),
        )
        for index in range(4)
    )
    mixed_step = _full(
        "estimate_follow_up_calls",
        "doc-mixed",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.10"),
        consequence=Decimal("8"),
        automation=Decimal("7"),
        manuality=Decimal("0.60"),
    )
    high_no_labor_step = _full(
        "spare_parts_lookup",
        "doc-c",
        volume=Decimal("10000"),
        labor=Decimal("10"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    high_no_volume_step = _full(
        "warranty_claim_filing",
        "doc-d",
        volume=Decimal("10"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    low_impact_step = _full(
        "route_confirmation_text",
        "doc-e",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.00"),
        consequence=Decimal("0"),
        automation=Decimal("0"),
        manuality=Decimal("0.20"),
    )
    excluded_step = tuple(
        _full(
            "parking_lot_small_talk",
            f"doc-excluded-{index}",
            volume=Decimal("10"),
            labor=Decimal("10"),
            failure=Decimal("0.00"),
            consequence=Decimal("0"),
            automation=Decimal("0"),
            manuality=Decimal("0.20"),
        )
        for index in range(9)
    )

    evidence = (
        *max_step,
        mixed_step,
        high_no_labor_step,
        high_no_volume_step,
        low_impact_step,
        *excluded_step,
    )
    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=evidence,
    )

    assert result.status == M3Status.COMPLETE
    assert result.report.unique_steps == 6
    assert result.report.total_input_evidence == len(evidence)

    by_key = {item.step_name: item for item in result.bottlenecks}
    assert by_key["manual_invoice_re_entry"].bottleneck_score == Decimal("10")
    assert by_key["manual_invoice_re_entry"].evidence_count == 4
    # high volume/labor but zero failure/consequence/automation/manuality:
    # only the 0.15 + 0.20 volume/labor weights contribute.
    assert by_key["route_confirmation_text"].bottleneck_score == Decimal("3.50")
    assert by_key["parking_lot_small_talk"].bottleneck_score == Decimal("0")
    assert by_key["parking_lot_small_talk"].evidence_count == 9

    top_five = sorted(
        result.bottlenecks,
        key=lambda item: (-item.bottleneck_score, item.step_key),  # type: ignore[operator]
    )[:5]
    assert "parking_lot_small_talk" not in {item.step_name for item in top_five}
    assert set(result.top_bottleneck_ids) == {item.step_key for item in top_five}

    scores = tuple(item.bottleneck_score for item in top_five)
    weights = tuple(Decimal(item.evidence_count).sqrt() for item in top_five)
    expected_mean = weighted_mean(scores, weights)
    assert expected_mean is not None
    expected_score = clamp10(
        M3.aggregation.max_weight * max(scores) + M3.aggregation.mean_weight * expected_mean  # type: ignore[operator]
    )
    assert result.score == expected_score


def test_missing_component_on_any_step_keeps_the_whole_method_unknown() -> None:
    complete = _full(
        "manual_invoice_re_entry",
        "doc-a",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    incomplete = step(
        step_name="warranty_claim_filing",
        document_id="doc-b",
        events_per_month=Decimal("500"),
        labor_hours_per_month=Decimal("40"),
        failure_rate=None,
        consequence_score=Decimal("6"),
        automation_potential=Decimal("5"),
        manual_share=Decimal("0.50"),
    )

    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(complete, incomplete),
    )

    assert result.status == M3Status.UNKNOWN
    assert result.score is None
    assert "m3.step_component_missing" in result.unknown_reasons
    incomplete_metrics = next(
        item for item in result.bottlenecks if item.step_name == "warranty_claim_filing"
    )
    assert "failure_rate" in incomplete_metrics.missing_components


def test_no_evidence_is_unknown() -> None:
    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(),
    )
    assert result.status == M3Status.UNKNOWN
    assert result.score is None
    assert "m3.no_workflow_steps" in result.unknown_reasons
    assert result.report.unique_steps == 0


def test_zero_volume_floors_log_scale_component_instead_of_raising() -> None:
    zero_volume = _full(
        "rare_edge_case_step",
        "doc-zero",
        volume=Decimal("0"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(zero_volume,),
    )
    metrics = result.bottlenecks[0]
    assert metrics.component_scores.volume == Decimal("0")
    assert metrics.bottleneck_score is not None


def test_duplicate_evidence_averages_instead_of_summing_and_does_not_inflate() -> None:
    single = _full(
        "manual_invoice_re_entry",
        "doc-single",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    repeated_low = tuple(
        _full(
            "manual_invoice_re_entry",
            f"doc-repeat-{index}",
            volume=Decimal("10"),
            labor=Decimal("10"),
            failure=Decimal("0.00"),
            consequence=Decimal("0"),
            automation=Decimal("0"),
            manuality=Decimal("0.20"),
        )
        for index in range(5)
    )

    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(single, *repeated_low),
    )
    metrics = result.bottlenecks[0]
    assert metrics.evidence_count == 6
    assert metrics.component_values.volume == (Decimal("10000") + 5 * Decimal("10")) / 6


def test_duplicate_evidence_id_is_rejected() -> None:
    original = _full(
        "manual_invoice_re_entry",
        "doc-a",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    duplicate = original.model_copy()

    with pytest.raises(ValueError, match="unique"):
        calculate_m3(
            market_id="us_hvac",
            formula_version=FORMULAS.formula_version,
            formula=M3,
            evidence=(original, duplicate),
        )


def test_contradiction_links_to_its_step() -> None:
    evidence = _full(
        "manual_invoice_re_entry",
        "doc-a",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    contradiction = WorkflowContradiction(
        contradiction_id=hashlib.sha256(b"contradiction").hexdigest(),
        document_id="doc-contrary",
        source_family="official_page",
        claim="A different source reports this step is already automated.",
        evidence_span="already automated end to end",
        linked_evidence_ids=(evidence.evidence_id,),
    )

    result = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(evidence,),
        contradictions=(contradiction,),
    )
    assert result.report.contradiction_count == 1
    assert result.bottlenecks[0].contradiction_ids == (contradiction.contradiction_id,)


def test_reproducible_input_hash() -> None:
    evidence = _full(
        "manual_invoice_re_entry",
        "doc-a",
        volume=Decimal("10000"),
        labor=Decimal("1000"),
        failure=Decimal("0.20"),
        consequence=Decimal("10"),
        automation=Decimal("10"),
        manuality=Decimal("1.00"),
    )
    first = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(evidence,),
    )
    second = calculate_m3(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        evidence=(evidence,),
    )
    assert first.input_sha256 == second.input_sha256
    assert first.score == second.score
