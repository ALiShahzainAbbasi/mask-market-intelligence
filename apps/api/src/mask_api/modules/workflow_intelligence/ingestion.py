"""Convert A10-accepted workflow-step output into lineage-rich evidence."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal

from mask_api.modules.analysis.grounding_contracts import (
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.analysis.schemas import WorkflowStepOutput
from mask_api.modules.workflow_intelligence.contracts import (
    GroundedWorkflowContext,
    WorkflowStepEvidence,
)

_WHITESPACE = re.compile(r"\s+")


class WorkflowIngestionError(ValueError):
    """Grounding output is ineligible or is not a workflow-step-v1 contract."""


def normalize_step_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def _optional_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def steps_from_grounding(
    context: GroundedWorkflowContext,
    report: GroundingReport,
) -> tuple[WorkflowStepEvidence, ...]:
    if (
        report.disposition != GroundingDisposition.ACCEPTED
        or not report.eligible_for_scoring_input
        or report.scoring_input is None
    ):
        raise WorkflowIngestionError("workflow ingestion requires an A10-accepted report")
    try:
        output = WorkflowStepOutput.model_validate(report.scoring_input)
    except ValueError as error:
        raise WorkflowIngestionError("grounded output is not workflow-step-v1") from error

    evidence: list[WorkflowStepEvidence] = []
    for index, record in enumerate(output.records):
        normalized_name = normalize_step_name(record.step_name)
        normalized_hash = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
        identity_payload = json.dumps(
            [
                context.market_id,
                context.document_id,
                report.analysis_cache_key,
                index,
                normalized_hash,
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        evidence_id = hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()
        evidence.append(
            WorkflowStepEvidence(
                evidence_id=evidence_id,
                market_id=context.market_id,
                document_id=context.document_id,
                normalized_document_sha256=report.normalized_document_sha256,
                analysis_cache_key=report.analysis_cache_key,
                grounding_version=report.grounding_version,
                source_family=context.source_family,
                persona=context.persona,
                source_date=context.source_date,
                step_name=record.step_name,
                normalized_step_name=normalized_name,
                normalized_step_name_sha256=normalized_hash,
                role=record.role,
                system=record.system,
                input_description=record.input_description,
                output_description=record.output_description,
                events_per_month=_optional_decimal(record.events_per_month),
                labor_hours_per_month=_optional_decimal(record.labor_hours_per_month),
                waiting_time_minutes=_optional_decimal(record.waiting_time_minutes),
                failure_rate=_optional_decimal(record.failure_rate_0_1),
                consequence_description=record.consequence_description,
                consequence_score=_optional_decimal(record.consequence_score_0_10),
                workaround=record.workaround,
                automation_potential=_optional_decimal(record.automation_potential_0_10),
                manual_share=_optional_decimal(record.manual_share_0_1),
                evidence_span=record.evidence_span,
                extraction_confidence=Decimal(str(record.confidence)),
            )
        )
    return tuple(evidence)
