"""Strict v1 extraction outputs derived from the canonical AI pipeline."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mask_api.modules.analysis.contracts import AnalysisSchemaId
from mask_api.modules.evidence.domain import EvidencePersona
from mask_api.modules.search_intent.contracts import KeywordIntent
from mask_api.research_runner.contracts import MethodId


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class RelevanceLabel(StrEnum):
    RELEVANT = "relevant"
    POSSIBLY_RELEVANT = "possibly_relevant"
    IRRELEVANT = "irrelevant"


class RelevanceOutput(StructuredOutput):
    label: RelevanceLabel
    reasons: tuple[str, ...] = Field(min_length=1, max_length=5)
    evidence_spans: tuple[str, ...] = Field(max_length=5)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def relevant_output_has_span(self) -> RelevanceOutput:
        if self.label != RelevanceLabel.IRRELEVANT and not self.evidence_spans:
            raise ValueError("relevant classifications require an evidence span")
        return self


class PersonaOutput(StructuredOutput):
    persona: EvidencePersona
    evidence_span: str | None
    confidence: float = Field(ge=0, le=1)


class FinancialValue(StructuredOutput):
    amount: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    period: str = Field(min_length=1, max_length=100)
    evidence_span: str = Field(min_length=1, max_length=4_000)


class CommercialPainRecord(StructuredOutput):
    pain_present: Literal[True]
    pain_category: str | None = Field(max_length=100)
    pain_subcategory: str | None = Field(max_length=100)
    pain_description: str = Field(min_length=1, max_length=1_000)
    sentiment: int = Field(ge=-2, le=2)
    severity_1_10: int | None = Field(ge=1, le=10)
    urgency_1_10: int | None = Field(ge=1, le=10)
    economic_impact_types: tuple[str, ...] = Field(max_length=10)
    economic_impact_1_10: int | None = Field(ge=1, le=10)
    purchase_intent_0_4: int | None = Field(ge=0, le=4)
    existing_workaround: str | None = Field(max_length=2_000)
    solution_dissatisfaction_1_10: int | None = Field(ge=1, le=10)
    ai_suitability_1_10: int | None = Field(ge=1, le=10)
    software_mentioned: tuple[str, ...] = Field(max_length=20)
    financial_value_mentioned: tuple[FinancialValue, ...] = Field(max_length=10)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)


class CommercialPainOutput(StructuredOutput):
    records: tuple[CommercialPainRecord, ...] = Field(max_length=50)


class EvidencePolarity(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTORY = "contradictory"
    NEUTRAL = "neutral"


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class GeneralEvidenceRecord(StructuredOutput):
    methodology_id: MethodId
    evidence_type: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    polarity: EvidencePolarity
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    strength: EvidenceStrength
    confidence: float = Field(ge=0, le=1)


class GeneralEvidenceOutput(StructuredOutput):
    records: tuple[GeneralEvidenceRecord, ...] = Field(max_length=100)


class CompetitorType(StrEnum):
    DIRECT_AI_VENDOR = "direct_ai_vendor"
    VERTICAL_SAAS = "vertical_saas"
    AGENCY = "agency"
    CONSULTANCY = "consultancy"
    BPO = "bpo"
    INTERNAL_DIY = "internal_diy"


class PricingStatus(StrEnum):
    EXACT = "exact"
    STARTING_AT = "starting_at"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class CompetitorPricing(StructuredOutput):
    status: PricingStatus
    amount: float | None = Field(ge=0)
    currency: str | None = Field(pattern=r"^[A-Z]{3}$")
    period: str | None = Field(max_length=100)
    evidence_span: str | None = Field(max_length=4_000)

    @model_validator(mode="after")
    def unknown_price_has_no_amount(self) -> CompetitorPricing:
        if self.status == PricingStatus.UNKNOWN and any(
            value is not None
            for value in (self.amount, self.currency, self.period, self.evidence_span)
        ):
            raise ValueError("unknown pricing cannot contain proposed values")
        return self


class CompetitorRecord(StructuredOutput):
    competitor_name: str = Field(min_length=1, max_length=300)
    competitor_type: CompetitorType
    target_market: str | None = Field(max_length=1_000)
    target_buyer: str | None = Field(max_length=1_000)
    problem_solved: tuple[str, ...] = Field(max_length=20)
    pricing: CompetitorPricing
    features: tuple[str, ...] = Field(max_length=50)
    integrations: tuple[str, ...] = Field(max_length=50)
    positioning: str | None = Field(max_length=2_000)
    strengths: tuple[str, ...] = Field(max_length=20)
    weaknesses: tuple[str, ...] = Field(max_length=20)
    evidence_spans: tuple[str, ...] = Field(min_length=1, max_length=20)
    confidence: float = Field(ge=0, le=1)


class CompetitorOutput(StructuredOutput):
    records: tuple[CompetitorRecord, ...] = Field(max_length=50)


class SearchIntentRecord(StructuredOutput):
    keyword: str = Field(min_length=1, max_length=200)
    intent_type: KeywordIntent
    alternative_intent: KeywordIntent | None
    confidence: float = Field(ge=0, le=1)


class SearchIntentOutput(StructuredOutput):
    records: tuple[SearchIntentRecord, ...] = Field(max_length=200)


class InterviewFindingType(StrEnum):
    PAIN_CONFIRMED = "pain_confirmed"
    PAIN_REJECTED = "pain_rejected"
    URGENCY = "urgency"
    EXISTING_SPEND = "existing_spend"
    WORKFLOW_DETAIL = "workflow_detail"
    BUYING_AUTHORITY = "buying_authority"
    BUYING_OBJECTION = "buying_objection"
    CURRENT_SOLUTION = "current_solution"
    WILLINGNESS_TO_SOLVE = "willingness_to_solve"
    CONTRADICTION = "contradiction"


class InterviewFinding(StructuredOutput):
    finding_type: InterviewFindingType
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)


class InterviewOutput(StructuredOutput):
    findings: tuple[InterviewFinding, ...] = Field(max_length=100)
    unresolved_questions: tuple[str, ...] = Field(max_length=30)


class ClusterNamingOutput(StructuredOutput):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    out_of_scope_signals: tuple[str, ...] = Field(max_length=20)
    confidence: float = Field(ge=0, le=1)


_OUTPUT_MODELS: dict[AnalysisSchemaId, type[StructuredOutput]] = {
    AnalysisSchemaId.RELEVANCE_V1: RelevanceOutput,
    AnalysisSchemaId.PERSONA_V1: PersonaOutput,
    AnalysisSchemaId.COMMERCIAL_PAIN_V1: CommercialPainOutput,
    AnalysisSchemaId.GENERAL_EVIDENCE_V1: GeneralEvidenceOutput,
    AnalysisSchemaId.COMPETITOR_V1: CompetitorOutput,
    AnalysisSchemaId.SEARCH_INTENT_V1: SearchIntentOutput,
    AnalysisSchemaId.INTERVIEW_V1: InterviewOutput,
    AnalysisSchemaId.CLUSTER_NAMING_V1: ClusterNamingOutput,
}


def output_model_for(schema_id: AnalysisSchemaId) -> type[StructuredOutput]:
    return _OUTPUT_MODELS[schema_id]


def strict_json_schema(schema_id: AnalysisSchemaId) -> dict[str, Any]:
    """Produce the strict JSON Schema subset sent to Structured Outputs."""

    schema = deepcopy(output_model_for(schema_id).model_json_schema(mode="serialization"))
    _make_strict(schema)
    return schema


def _make_strict(node: object) -> None:
    if isinstance(node, dict):
        typed = cast(dict[str, Any], node)
        typed.pop("default", None)
        properties = typed.get("properties")
        if isinstance(properties, dict):
            typed["additionalProperties"] = False
            typed["required"] = list(properties)
        for value in tuple(typed.values()):
            _make_strict(value)
    elif isinstance(node, list):
        for value in node:
            _make_strict(value)
