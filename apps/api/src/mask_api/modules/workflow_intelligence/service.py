"""Application service composing the offline M3 workflow pipeline."""

from __future__ import annotations

from mask_api.modules.analysis.grounding_contracts import GroundingReport
from mask_api.modules.workflow_intelligence.contracts import (
    GroundedWorkflowContext,
    M3Result,
    WorkflowContradiction,
)
from mask_api.modules.workflow_intelligence.ingestion import steps_from_grounding
from mask_api.modules.workflow_intelligence.metrics import calculate_m3
from mask_api.research_runner.contracts import MethodFormula


class WorkflowIntelligenceService:
    def run(
        self,
        *,
        market_id: str,
        formula_version: str,
        formula: MethodFormula,
        grounded_documents: tuple[tuple[GroundedWorkflowContext, GroundingReport], ...],
        contradictions: tuple[WorkflowContradiction, ...] = (),
    ) -> M3Result:
        evidence = tuple(
            item
            for context, report in grounded_documents
            for item in steps_from_grounding(context, report)
        )
        return calculate_m3(
            market_id=market_id,
            formula_version=formula_version,
            formula=formula,
            evidence=evidence,
            contradictions=contradictions,
        )
