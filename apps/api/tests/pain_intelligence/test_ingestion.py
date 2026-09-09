from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
from mask_api.modules.analysis.grounding_contracts import (
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.pain_intelligence.contracts import GroundedPainContext
from mask_api.modules.pain_intelligence.ingestion import (
    PainIngestionError,
    mentions_from_grounding,
)


def test_ingestion_accepts_only_grounded_output_and_preserves_lineage() -> None:
    output = {
        "records": [
            {
                "pain_present": True,
                "pain_category": "missed_calls",
                "pain_subcategory": None,
                "pain_description": "  Missed\nCalls Cost Revenue  ",
                "sentiment": -2,
                "severity_1_10": 4,
                "urgency_1_10": None,
                "economic_impact_types": ["revenue_leakage"],
                "economic_impact_1_10": 5,
                "purchase_intent_0_4": 1,
                "existing_workaround": None,
                "solution_dissatisfaction_1_10": 4,
                "ai_suitability_1_10": 7,
                "software_mentioned": [],
                "financial_value_mentioned": [],
                "evidence_span": "Missed Calls Cost Revenue",
                "confidence": 0.8,
            }
        ]
    }
    report = accepted_report(output)
    context = GroundedPainContext(
        market_id="us_hvac",
        document_id="doc-1",
        source_family="approved_feed",
        persona="owner",
        source_date=date(2026, 9, 1),
    )

    mentions = mentions_from_grounding(context, report)

    assert len(mentions) == 1
    assert mentions[0].normalized_pain_text == "missed calls cost revenue"
    assert mentions[0].analysis_cache_key == report.analysis_cache_key
    assert mentions[0].source_family == "approved_feed"
    assert mentions[0].persona.value == "owner"


def test_ingestion_rejects_quarantined_output() -> None:
    output = {"records": []}
    report = accepted_report(output).model_copy(
        update={
            "disposition": GroundingDisposition.NEEDS_REVIEW,
            "eligible_for_scoring_input": False,
            "scoring_input": None,
        }
    )
    context = GroundedPainContext(
        market_id="us_hvac",
        document_id="doc-1",
        source_family="approved_feed",
        persona="unknown",
    )

    with pytest.raises(PainIngestionError):
        mentions_from_grounding(context, report)


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
