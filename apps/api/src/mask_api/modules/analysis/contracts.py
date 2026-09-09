"""Provider-neutral contracts for versioned structured analysis."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    computed_field,
    field_validator,
    model_validator,
)


class AnalysisValue(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )


class AnalysisType(StrEnum):
    RELEVANCE = "relevance"
    PERSONA = "persona"
    COMMERCIAL_PAIN = "commercial_pain"
    GENERAL_EVIDENCE = "general_evidence"
    COMPETITOR = "competitor"
    SEARCH_INTENT = "search_intent"
    INTERVIEW = "interview"
    CLUSTER_NAMING = "cluster_naming"
    WORKFLOW_STEP = "workflow_step"


class AnalysisSchemaId(StrEnum):
    RELEVANCE_V1 = "relevance-v1"
    PERSONA_V1 = "persona-v1"
    COMMERCIAL_PAIN_V1 = "commercial-pain-v1"
    GENERAL_EVIDENCE_V1 = "general-evidence-v1"
    COMPETITOR_V1 = "competitor-v1"
    SEARCH_INTENT_V1 = "search-intent-v1"
    INTERVIEW_V1 = "interview-v1"
    CLUSTER_NAMING_V1 = "cluster-naming-v1"
    WORKFLOW_STEP_V1 = "workflow-step-v1"


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"


class ModelExecutionPolicy(AnalysisValue):
    """Caller-selected model, finite token ceiling, pricing, and call cost cap."""

    model_reference: str = Field(min_length=1, max_length=200)
    input_token_budget: int = Field(ge=1, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=16_384)
    input_usd_per_million_tokens: Decimal = Field(gt=0)
    output_usd_per_million_tokens: Decimal = Field(gt=0)
    max_call_cost_usd: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def cost_cap_covers_reserved_tokens(self) -> ModelExecutionPolicy:
        maximum = (
            Decimal(self.input_token_budget) * self.input_usd_per_million_tokens
            + Decimal(self.max_output_tokens) * self.output_usd_per_million_tokens
        ) / Decimal(1_000_000)
        if maximum > self.max_call_cost_usd:
            raise ValueError("model cost cap does not cover the reserved token ceilings")
        return self


class AnalysisRequest(AnalysisValue):
    analysis_type: AnalysisType
    schema_id: AnalysisSchemaId
    analysis_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    prompt_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    schema_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    taxonomy_version: str = Field(min_length=1, max_length=100)
    normalization_version: str = Field(min_length=1, max_length=100)
    normalized_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    market_definition: str = Field(min_length=1, max_length=4_000)
    task_instructions: str = Field(min_length=1, max_length=8_000)
    source_text: str = Field(min_length=1, max_length=40_000)
    model_policy: ModelExecutionPolicy

    @field_validator("market_definition", "task_instructions", "source_text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("analysis text cannot be blank")
        return stripped

    @model_validator(mode="after")
    def matching_schema(self) -> AnalysisRequest:
        expected = {
            AnalysisType.RELEVANCE: AnalysisSchemaId.RELEVANCE_V1,
            AnalysisType.PERSONA: AnalysisSchemaId.PERSONA_V1,
            AnalysisType.COMMERCIAL_PAIN: AnalysisSchemaId.COMMERCIAL_PAIN_V1,
            AnalysisType.GENERAL_EVIDENCE: AnalysisSchemaId.GENERAL_EVIDENCE_V1,
            AnalysisType.COMPETITOR: AnalysisSchemaId.COMPETITOR_V1,
            AnalysisType.SEARCH_INTENT: AnalysisSchemaId.SEARCH_INTENT_V1,
            AnalysisType.INTERVIEW: AnalysisSchemaId.INTERVIEW_V1,
            AnalysisType.CLUSTER_NAMING: AnalysisSchemaId.CLUSTER_NAMING_V1,
            AnalysisType.WORKFLOW_STEP: AnalysisSchemaId.WORKFLOW_STEP_V1,
        }[self.analysis_type]
        if self.schema_id != expected:
            raise ValueError("analysis type and schema ID do not match")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cache_key(self) -> str:
        payload = self.model_dump(mode="json", exclude={"cache_key", "model_policy"})
        payload["model_reference"] = self.model_policy.model_reference
        payload["max_output_tokens"] = self.model_policy.max_output_tokens
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class AnalysisUsage(AnalysisValue):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def total_is_consistent(self) -> AnalysisUsage:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total token count must equal input plus output tokens")
        return self


class AnalysisResult(AnalysisValue):
    provider: str = "openai_responses"
    provider_response_id: str = Field(min_length=1, max_length=200)
    requested_model_reference: str = Field(min_length=1, max_length=200)
    response_model_reference: str = Field(min_length=1, max_length=200)
    request_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: AnalysisStatus
    structured_output: dict[str, JsonValue] | None = None
    refusal: str | None = Field(default=None, max_length=2_000)
    incomplete_reason: str | None = Field(default=None, max_length=500)
    usage: AnalysisUsage
    created_at: AwareDatetime
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response: bytes = Field(repr=False)

    @model_validator(mode="after")
    def status_payload_is_consistent(self) -> AnalysisResult:
        if self.status == AnalysisStatus.COMPLETED:
            if self.structured_output is None or self.refusal is not None:
                raise ValueError("completed analysis requires structured output only")
        elif self.status == AnalysisStatus.REFUSED:
            if not self.refusal or self.structured_output is not None:
                raise ValueError("refused analysis requires a refusal only")
        elif self.structured_output is not None:
            raise ValueError("incomplete analysis cannot contain structured output")
        return self


class AnalysisCacheRecord(AnalysisValue):
    request: AnalysisRequest
    result: AnalysisResult

    @model_validator(mode="after")
    def matching_key(self) -> AnalysisCacheRecord:
        if self.result.request_cache_key != self.request.cache_key:
            raise ValueError("cached analysis does not match its request")
        if self.result.status != AnalysisStatus.COMPLETED:
            raise ValueError("only completed validated analysis can be cached")
        return self
