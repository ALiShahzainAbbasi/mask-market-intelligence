"""Immutable contracts for grounded M3 workflow-bottleneck processing."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mask_api.modules.evidence.domain import EvidencePersona


class WorkflowValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class GroundedWorkflowContext(WorkflowValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    document_id: str = Field(min_length=1, max_length=200)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    persona: EvidencePersona
    source_date: date | None = None


class WorkflowStepEvidence(WorkflowValue):
    evidence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    document_id: str = Field(min_length=1, max_length=200)
    normalized_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding_version: str = Field(min_length=1, max_length=100)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    persona: EvidencePersona
    source_date: date | None
    step_name: str = Field(min_length=1, max_length=200)
    normalized_step_name: str = Field(min_length=1, max_length=200)
    normalized_step_name_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: str = Field(min_length=1, max_length=200)
    system: str | None = Field(default=None, max_length=200)
    input_description: str | None = Field(default=None, max_length=1_000)
    output_description: str | None = Field(default=None, max_length=1_000)
    events_per_month: Decimal | None = Field(default=None, ge=0)
    labor_hours_per_month: Decimal | None = Field(default=None, ge=0)
    waiting_time_minutes: Decimal | None = Field(default=None, ge=0)
    failure_rate: Decimal | None = Field(default=None, ge=0, le=1)
    consequence_description: str | None = Field(default=None, max_length=1_000)
    consequence_score: Decimal | None = Field(default=None, ge=0, le=10)
    workaround: str | None = Field(default=None, max_length=1_000)
    automation_potential: Decimal | None = Field(default=None, ge=0, le=10)
    manual_share: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    extraction_confidence: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def normalized_hash_matches_text(self) -> WorkflowStepEvidence:
        digest = hashlib.sha256(self.normalized_step_name.encode("utf-8")).hexdigest()
        if digest != self.normalized_step_name_sha256:
            raise ValueError("normalized step-name hash does not match its text")
        return self


class WorkflowContradiction(WorkflowValue):
    contradiction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str = Field(min_length=1, max_length=200)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    linked_evidence_ids: tuple[str, ...] = Field(max_length=50)

    @field_validator("linked_evidence_ids")
    @classmethod
    def valid_link_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("contradiction evidence links must be unique")
        return values


class M3ComponentValues(WorkflowValue):
    volume: Decimal | None = Field(default=None, ge=0)
    labor_burden: Decimal | None = Field(default=None, ge=0)
    failure_rate: Decimal | None = Field(default=None, ge=0, le=1)
    business_consequence: Decimal | None = Field(default=None, ge=0, le=10)
    automation_potential: Decimal | None = Field(default=None, ge=0, le=10)
    manuality: Decimal | None = Field(default=None, ge=0, le=1)


class M3ComponentScores(WorkflowValue):
    volume: Decimal | None = Field(default=None, ge=0, le=10)
    labor_burden: Decimal | None = Field(default=None, ge=0, le=10)
    failure_rate: Decimal | None = Field(default=None, ge=0, le=10)
    business_consequence: Decimal | None = Field(default=None, ge=0, le=10)
    automation_potential: Decimal | None = Field(default=None, ge=0, le=10)
    manuality: Decimal | None = Field(default=None, ge=0, le=10)


class WorkflowBottleneckMetrics(WorkflowValue):
    step_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    step_name: str = Field(min_length=1, max_length=200)
    evidence_count: int = Field(ge=1)
    source_family_count: int = Field(ge=1)
    component_values: M3ComponentValues
    component_scores: M3ComponentScores
    component_sample_counts: dict[str, int]
    bottleneck_score: Decimal | None = Field(default=None, ge=0, le=10)
    missing_components: tuple[str, ...]
    representative_evidence_ids: tuple[str, ...] = Field(max_length=3)
    contradiction_ids: tuple[str, ...]


class M3Status(StrEnum):
    UNKNOWN = "unknown"
    COMPLETE = "complete"


class WorkflowReportSection(WorkflowValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    total_input_evidence: int = Field(ge=0)
    unique_steps: int = Field(ge=0)
    source_family_distribution: dict[str, int]
    persona_distribution: dict[EvidencePersona, int]
    earliest_source_date: date | None
    latest_source_date: date | None
    contradiction_count: int = Field(ge=0)
    bottlenecks: tuple[WorkflowBottleneckMetrics, ...]

    @field_validator("source_family_distribution", "persona_distribution")
    @classmethod
    def nonnegative_distribution(cls, values: dict[object, int]) -> dict[object, int]:
        if any(value < 0 for value in values.values()):
            raise ValueError("report distributions cannot contain negative counts")
        return values


class M3Result(WorkflowValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: M3Status
    score: Decimal | None = Field(default=None, ge=0, le=10)
    top_bottleneck_ids: tuple[str, ...] = Field(max_length=5)
    unknown_reasons: tuple[str, ...]
    bottlenecks: tuple[WorkflowBottleneckMetrics, ...]
    report: WorkflowReportSection

    @model_validator(mode="after")
    def status_matches_score(self) -> M3Result:
        if self.status == M3Status.UNKNOWN and self.score is not None:
            raise ValueError("unknown M3 result cannot have a score")
        if self.status != M3Status.UNKNOWN and self.score is None:
            raise ValueError("known M3 result requires a score")
        return self
