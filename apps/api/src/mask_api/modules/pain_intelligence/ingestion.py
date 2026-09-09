"""Convert A10-accepted commercial-pain output into lineage-rich mentions."""

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
from mask_api.modules.analysis.schemas import CommercialPainOutput
from mask_api.modules.pain_intelligence.contracts import (
    GroundedPainContext,
    PainFinancialValue,
    PainMention,
)

_WHITESPACE = re.compile(r"\s+")


class PainIngestionError(ValueError):
    """Grounding output is ineligible or is not a commercial-pain contract."""


def normalize_pain_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def mentions_from_grounding(
    context: GroundedPainContext,
    report: GroundingReport,
) -> tuple[PainMention, ...]:
    if (
        report.disposition != GroundingDisposition.ACCEPTED
        or not report.eligible_for_scoring_input
        or report.scoring_input is None
    ):
        raise PainIngestionError("pain ingestion requires an A10-accepted report")
    try:
        output = CommercialPainOutput.model_validate(report.scoring_input)
    except ValueError as error:
        raise PainIngestionError("grounded output is not commercial-pain-v1") from error

    mentions: list[PainMention] = []
    for index, record in enumerate(output.records):
        normalized_text = normalize_pain_text(record.pain_description)
        normalized_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
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
        mention_id = hashlib.sha256(identity_payload.encode("utf-8")).hexdigest()
        mentions.append(
            PainMention(
                mention_id=mention_id,
                market_id=context.market_id,
                document_id=context.document_id,
                normalized_document_sha256=report.normalized_document_sha256,
                analysis_cache_key=report.analysis_cache_key,
                grounding_version=report.grounding_version,
                source_family=context.source_family,
                persona=context.persona,
                source_date=context.source_date,
                pain_category=record.pain_category,
                pain_subcategory=record.pain_subcategory,
                pain_description=record.pain_description,
                normalized_pain_text=normalized_text,
                normalized_pain_sha256=normalized_hash,
                sentiment=record.sentiment,
                severity_1_10=record.severity_1_10,
                urgency_1_10=record.urgency_1_10,
                economic_impact_types=record.economic_impact_types,
                economic_impact_1_10=record.economic_impact_1_10,
                purchase_intent_0_4=record.purchase_intent_0_4,
                existing_workaround=record.existing_workaround,
                solution_dissatisfaction_1_10=record.solution_dissatisfaction_1_10,
                ai_suitability_1_10=record.ai_suitability_1_10,
                software_mentioned=record.software_mentioned,
                financial_values=tuple(
                    PainFinancialValue(
                        amount=Decimal(str(value.amount)),
                        currency=value.currency,
                        period=value.period,
                        evidence_span=value.evidence_span,
                    )
                    for value in record.financial_value_mentioned
                ),
                evidence_span=record.evidence_span,
                extraction_confidence=Decimal(str(record.confidence)),
            )
        )
    return tuple(mentions)
