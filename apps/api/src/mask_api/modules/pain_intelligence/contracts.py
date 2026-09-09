"""Immutable contracts for grounded M2 pain processing."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mask_api.modules.evidence.domain import EvidencePersona


class PainValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class GroundedPainContext(PainValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    document_id: str = Field(min_length=1, max_length=200)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    persona: EvidencePersona
    source_date: date | None = None


class PainFinancialValue(PainValue):
    amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    period: str = Field(min_length=1, max_length=100)
    evidence_span: str = Field(min_length=1, max_length=4_000)


class PainMention(PainValue):
    mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    document_id: str = Field(min_length=1, max_length=200)
    normalized_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding_version: str = Field(min_length=1, max_length=100)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    persona: EvidencePersona
    source_date: date | None
    pain_category: str | None = Field(default=None, max_length=100)
    pain_subcategory: str | None = Field(default=None, max_length=100)
    pain_description: str = Field(min_length=1, max_length=1_000)
    normalized_pain_text: str = Field(min_length=1, max_length=1_000)
    normalized_pain_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sentiment: int = Field(ge=-2, le=2)
    severity_1_10: int | None = Field(default=None, ge=1, le=10)
    urgency_1_10: int | None = Field(default=None, ge=1, le=10)
    economic_impact_types: tuple[str, ...] = Field(max_length=10)
    economic_impact_1_10: int | None = Field(default=None, ge=1, le=10)
    purchase_intent_0_4: int | None = Field(default=None, ge=0, le=4)
    existing_workaround: str | None = Field(default=None, max_length=2_000)
    solution_dissatisfaction_1_10: int | None = Field(default=None, ge=1, le=10)
    ai_suitability_1_10: int | None = Field(default=None, ge=1, le=10)
    software_mentioned: tuple[str, ...] = Field(max_length=20)
    financial_values: tuple[PainFinancialValue, ...] = Field(max_length=10)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    extraction_confidence: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def normalized_hash_matches_text(self) -> PainMention:
        digest = hashlib.sha256(self.normalized_pain_text.encode("utf-8")).hexdigest()
        if digest != self.normalized_pain_sha256:
            raise ValueError("normalized pain hash does not match its text")
        return self


class PainContradiction(PainValue):
    contradiction_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str = Field(min_length=1, max_length=200)
    source_family: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_span: str = Field(min_length=1, max_length=4_000)
    linked_mention_ids: tuple[str, ...] = Field(max_length=50)

    @field_validator("linked_mention_ids")
    @classmethod
    def valid_link_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("contradiction mention links must be unique")
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in values):
            raise ValueError("contradiction mention links must be stable hashes")
        return values


class EmbeddingItem(PainValue):
    mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_text: str = Field(min_length=1, max_length=1_000)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def input_hash_matches_text(self) -> EmbeddingItem:
        digest = hashlib.sha256(self.input_text.encode("utf-8")).hexdigest()
        if digest != self.input_sha256:
            raise ValueError("embedding input hash does not match its text")
        return self


class EmbeddingRequest(PainValue):
    provider: str = Field(min_length=1, max_length=100)
    model_reference: str = Field(min_length=1, max_length=200)
    embedding_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    dimensions: int = Field(ge=16, le=4_096)
    max_items: int = Field(ge=1, le=10_000)
    max_total_characters: int = Field(ge=1, le=10_000_000)
    items: tuple[EmbeddingItem, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def batch_fits_limits(self) -> EmbeddingRequest:
        if len(self.items) > self.max_items:
            raise ValueError("embedding batch exceeds its item limit")
        if sum(len(item.input_text) for item in self.items) > self.max_total_characters:
            raise ValueError("embedding batch exceeds its character limit")
        if len({item.mention_id for item in self.items}) != len(self.items):
            raise ValueError("embedding batch mention IDs must be unique")
        return self


class EmbeddingVector(PainValue):
    mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1, max_length=100)
    model_reference: str = Field(min_length=1, max_length=200)
    embedding_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dimensions: int = Field(ge=16, le=4_096)
    values: tuple[float, ...] = Field(min_length=16, max_length=4_096)

    @field_validator("values")
    @classmethod
    def finite_nonzero_vector(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("embedding values must be finite")
        if not any(value != 0 for value in values):
            raise ValueError("embedding vector cannot be all zero")
        return values

    @model_validator(mode="after")
    def dimensions_match(self) -> EmbeddingVector:
        if len(self.values) != self.dimensions:
            raise ValueError("embedding dimensions do not match vector length")
        return self


class EmbeddingCacheRecord(PainValue):
    vector: EmbeddingVector


class DuplicateKind(StrEnum):
    EXACT = "exact"
    NEAR = "near"


class PainDuplicateLink(PainValue):
    duplicate_kind: DuplicateKind
    retained_mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    duplicate_mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    similarity: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def different_mentions(self) -> PainDuplicateLink:
        if self.retained_mention_id == self.duplicate_mention_id:
            raise ValueError("a duplicate link requires two mentions")
        return self


class DeduplicationResult(PainValue):
    retained_mentions: tuple[PainMention, ...]
    links: tuple[PainDuplicateLink, ...]


class ClusteringConfiguration(PainValue):
    clustering_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    algorithm: Literal["complete_linkage_cosine"] = "complete_linkage_cosine"
    algorithm_version: Literal["v1"] = "v1"
    similarity_threshold: Decimal = Field(ge=0, le=1)
    near_duplicate_threshold: Decimal = Field(ge=0, le=1)
    min_cluster_size: int = Field(ge=1, le=100)
    random_seed: Literal[0] = 0
    max_mentions: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def ordered_thresholds(self) -> ClusteringConfiguration:
        if self.near_duplicate_threshold < self.similarity_threshold:
            raise ValueError("near-duplicate threshold must be at least cluster threshold")
        return self


class ClusterMembership(PainValue):
    mention_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    membership_score: Decimal = Field(ge=0, le=1)
    is_outlier: bool


class PainCluster(PainValue):
    cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    persona: EvidencePersona
    display_label: str = Field(min_length=1, max_length=200)
    memberships: tuple[ClusterMembership, ...] = Field(min_length=1)
    is_outlier: bool

    @model_validator(mode="after")
    def consistent_outlier_state(self) -> PainCluster:
        if any(item.is_outlier != self.is_outlier for item in self.memberships):
            raise ValueError("cluster and membership outlier states must match")
        return self


class ClusteringResult(PainValue):
    clustering_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    algorithm: str = Field(min_length=1, max_length=100)
    algorithm_version: str = Field(min_length=1, max_length=100)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clusters: tuple[PainCluster, ...]


class M2ComponentValues(PainValue):
    frequency: Decimal = Field(ge=0, le=1)
    severity: Decimal | None = Field(default=None, ge=0, le=10)
    economic_impact: Decimal | None = Field(default=None, ge=0, le=10)
    purchase_intent: Decimal | None = Field(default=None, ge=0, le=4)
    dissatisfaction: Decimal | None = Field(default=None, ge=0, le=10)


class M2ComponentScores(PainValue):
    frequency: Decimal = Field(ge=0, le=10)
    severity: Decimal | None = Field(default=None, ge=0, le=10)
    economic_impact: Decimal | None = Field(default=None, ge=0, le=10)
    purchase_intent: Decimal | None = Field(default=None, ge=0, le=10)
    dissatisfaction: Decimal | None = Field(default=None, ge=0, le=10)


class PainClusterMetrics(PainValue):
    cluster_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    unique_document_count: int = Field(ge=1)
    source_family_count: int = Field(ge=1)
    mention_count: int = Field(ge=1)
    component_values: M2ComponentValues
    component_scores: M2ComponentScores
    component_sample_counts: dict[str, int]
    opportunity_score: Decimal | None = Field(default=None, ge=0, le=10)
    missing_components: tuple[str, ...]
    representative_mention_ids: tuple[str, ...] = Field(max_length=3)
    contradiction_ids: tuple[str, ...]


class M2Status(StrEnum):
    UNKNOWN = "unknown"
    PROVISIONAL = "provisional"
    COMPLETE = "complete"


class PainReportSection(PainValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    total_input_mentions: int = Field(ge=0)
    unique_mentions: int = Field(ge=0)
    exact_duplicates: int = Field(ge=0)
    near_duplicates: int = Field(ge=0)
    outlier_mentions: int = Field(ge=0)
    source_family_distribution: dict[str, int]
    persona_distribution: dict[EvidencePersona, int]
    earliest_source_date: date | None
    latest_source_date: date | None
    contradiction_count: int = Field(ge=0)
    clusters: tuple[PainClusterMetrics, ...]

    @field_validator("source_family_distribution", "persona_distribution")
    @classmethod
    def nonnegative_distribution(cls, values: dict[object, int]) -> dict[object, int]:
        if any(value < 0 for value in values.values()):
            raise ValueError("report distributions cannot contain negative counts")
        return values


class M2Result(PainValue):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    clustering_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: M2Status
    score: Decimal | None = Field(default=None, ge=0, le=10)
    top_cluster_ids: tuple[str, ...] = Field(max_length=5)
    unknown_reasons: tuple[str, ...]
    provisional_reasons: tuple[str, ...]
    duplicate_links: tuple[PainDuplicateLink, ...]
    clusters: tuple[PainCluster, ...]
    report: PainReportSection

    @model_validator(mode="after")
    def status_matches_score(self) -> M2Result:
        if self.status == M2Status.UNKNOWN and self.score is not None:
            raise ValueError("unknown M2 result cannot have a score")
        if self.status != M2Status.UNKNOWN and self.score is None:
            raise ValueError("known M2 result requires a score")
        return self
