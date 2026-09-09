from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mask_api.modules.analysis.grounding_contracts import (
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.workflow_intelligence.contracts import GroundedWorkflowContext, M3Status
from mask_api.modules.workflow_intelligence.service import WorkflowIntelligenceService
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
M3 = FORMULAS.method_formulas[MethodId.M3]


def _record(step_name: str, document_id: str) -> dict[str, object]:
    return {
        "step_name": step_name,
        "role": "dispatcher",
        "system": "quickbooks",
        "input_description": "job ticket",
        "output_description": "invoice",
        "events_per_month": 10000.0,
        "labor_hours_per_month": 1000.0,
        "waiting_time_minutes": 15.0,
        "failure_rate_0_1": 0.20,
        "consequence_description": "late billing",
        "consequence_score_0_10": 10.0,
        "workaround": "spreadsheet tracker",
        "automation_potential_0_10": 10.0,
        "manual_share_0_1": 1.00,
        "evidence_span": f"evidence for {step_name} in {document_id}",
        "confidence": 0.9,
    }


def _report(*step_names: str, document_id: str) -> GroundingReport:
    output = {"records": [_record(name, document_id) for name in step_names]}
    serialized = json.dumps(output, sort_keys=True, separators=(",", ":"))
    return GroundingReport(
        analysis_cache_key=hashlib.sha256(f"analysis-{document_id}".encode()).hexdigest(),
        normalized_document_sha256=hashlib.sha256(document_id.encode()).hexdigest(),
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


def test_service_composes_multiple_documents_into_one_result() -> None:
    context_1 = GroundedWorkflowContext(
        market_id="us_hvac", document_id="doc-1", source_family="approved_feed", persona="owner"
    )
    context_2 = GroundedWorkflowContext(
        market_id="us_hvac", document_id="doc-2", source_family="analyst_upload", persona="employee"
    )
    result = WorkflowIntelligenceService().run(
        market_id="us_hvac",
        formula_version=FORMULAS.formula_version,
        formula=M3,
        grounded_documents=(
            (context_1, _report("manual_invoice_re_entry", document_id="doc-1")),
            (context_2, _report("manual_invoice_re_entry", document_id="doc-2")),
        ),
    )

    assert result.status == M3Status.COMPLETE
    assert result.score == 10
    assert result.report.total_input_evidence == 2
    assert result.report.unique_steps == 1
    assert result.bottlenecks[0].evidence_count == 2
    assert result.bottlenecks[0].source_family_count == 2
