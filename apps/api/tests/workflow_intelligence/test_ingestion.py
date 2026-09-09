from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
from mask_api.modules.analysis.grounding_contracts import (
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.workflow_intelligence.contracts import GroundedWorkflowContext
from mask_api.modules.workflow_intelligence.ingestion import (
    WorkflowIngestionError,
    steps_from_grounding,
)


def test_ingestion_accepts_only_grounded_output_and_preserves_lineage() -> None:
    output = {
        "records": [
            {
                "step_name": "  Manual Invoice Re-Entry  ",
                "role": "dispatcher",
                "system": "quickbooks",
                "input_description": "job ticket",
                "output_description": "invoice",
                "events_per_month": 420.0,
                "labor_hours_per_month": 70.0,
                "waiting_time_minutes": 15.0,
                "failure_rate_0_1": 0.08,
                "consequence_description": "late billing",
                "consequence_score_0_10": 6.0,
                "workaround": "spreadsheet tracker",
                "automation_potential_0_10": 8.0,
                "manual_share_0_1": 0.9,
                "evidence_span": "the dispatcher re-keys every job ticket into QuickBooks by hand",
                "confidence": 0.85,
            }
        ]
    }
    report = accepted_report(output)
    context = GroundedWorkflowContext(
        market_id="us_hvac",
        document_id="doc-1",
        source_family="approved_feed",
        persona="owner",
        source_date=date(2026, 9, 1),
    )

    evidence = steps_from_grounding(context, report)

    assert len(evidence) == 1
    assert evidence[0].normalized_step_name == "manual invoice re-entry"
    assert evidence[0].analysis_cache_key == report.analysis_cache_key
    assert evidence[0].events_per_month == 420
    assert evidence[0].source_family == "approved_feed"
    assert evidence[0].persona.value == "owner"


def test_ingestion_preserves_missing_optional_fields_as_unknown() -> None:
    output = {
        "records": [
            {
                "step_name": "warranty claim filing",
                "role": "office manager",
                "system": None,
                "input_description": None,
                "output_description": None,
                "events_per_month": None,
                "labor_hours_per_month": None,
                "waiting_time_minutes": None,
                "failure_rate_0_1": None,
                "consequence_description": None,
                "consequence_score_0_10": None,
                "workaround": None,
                "automation_potential_0_10": None,
                "manual_share_0_1": None,
                "evidence_span": "the office manager files warranty claims by phone",
                "confidence": 0.6,
            }
        ]
    }
    report = accepted_report(output)
    context = GroundedWorkflowContext(
        market_id="us_hvac", document_id="doc-2", source_family="approved_feed", persona="unknown"
    )

    evidence = steps_from_grounding(context, report)

    assert evidence[0].events_per_month is None
    assert evidence[0].failure_rate is None


def test_ingestion_rejects_quarantined_output() -> None:
    output = {"records": []}
    report = accepted_report(output).model_copy(
        update={
            "disposition": GroundingDisposition.NEEDS_REVIEW,
            "eligible_for_scoring_input": False,
            "scoring_input": None,
        }
    )
    context = GroundedWorkflowContext(
        market_id="us_hvac", document_id="doc-1", source_family="approved_feed", persona="unknown"
    )

    with pytest.raises(WorkflowIngestionError):
        steps_from_grounding(context, report)


def accepted_report(output: dict[str, object]) -> GroundingReport:
    serialized = json.dumps(output, sort_keys=True, separators=(",", ":"))
    return GroundingReport(
        analysis_cache_key="a" * 64,
        normalized_document_sha256="b" * 64,
        structured_output_sha256=hashlib.sha256(serialized.encode()).hexdigest(),
        disposition=GroundingDisposition.ACCEPTED,
        eligible_for_scoring_input=True,
        preserved_output=output,  # type: ignore[arg-type]
        scoring_input=output,  # type: ignore[arg-type]
        issues=(),
        high_impact_claims=(),
        verifications=(),
        contradiction_paths=(),
        injection_signals=(),
    )
