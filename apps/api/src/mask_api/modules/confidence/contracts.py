"""Typed contracts for the v1 confidence, completeness, and veto engine."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mask_api.research_runner.contracts import MethodId

_MARKET_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"


class ConfidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ConfidenceDimensions(ConfidenceValue):
    """The five v1 confidence dimensions, each already normalized to 0-10.

    This module does not derive these values from raw evidence: the specific
    per-method normalization rules for source diversity, evidence quality,
    recency, and cross-source agreement are not yet approved (open decision
    D04) or versioned alongside a method rubric, per SCORING.md section 6.
    Only `sample_adequacy` has an approved, generic derivation --
    `sample_adequacy_score()` below -- because v1.yaml's `sample_targets`
    block gives it an exact target per method. A missing dimension keeps the
    whole confidence result UNKNOWN; it is never defaulted or invented.
    """

    source_diversity_0_10: Decimal | None = Field(default=None, ge=0, le=10)
    sample_adequacy_0_10: Decimal | None = Field(default=None, ge=0, le=10)
    evidence_quality_0_10: Decimal | None = Field(default=None, ge=0, le=10)
    recency_0_10: Decimal | None = Field(default=None, ge=0, le=10)
    cross_source_agreement_0_10: Decimal | None = Field(default=None, ge=0, le=10)


class ConfidenceLabel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceResult(ConfidenceValue):
    """The exact, reproducible v1 confidence result for one method or gate."""

    numeric_confidence: Decimal | None = Field(default=None, ge=0, le=100)
    label: ConfidenceLabel | None = None
    unknown_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def label_matches_confidence(self) -> ConfidenceResult:
        known = self.numeric_confidence is not None
        if known != (self.label is not None):
            raise ValueError("a confidence result has a label if and only if it is known")
        if not known and not self.unknown_reasons:
            raise ValueError("an unknown confidence result requires unknown_reasons")
        if known and self.unknown_reasons:
            raise ValueError("a known confidence result cannot carry unknown_reasons")
        return self


class MethodCompletenessState(StrEnum):
    PROVEN = "proven"
    WEAK = "weak"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class MethodStatusSnapshot(ConfidenceValue):
    """One method's computed score, completeness, and confidence for a market."""

    method_id: MethodId
    status: str = Field(min_length=1, max_length=20)
    score: Decimal | None = Field(default=None, ge=0, le=10)
    completeness: MethodCompletenessState
    confidence: ConfidenceResult | None = None


class MarketMethodSummary(ConfidenceValue):
    """A market's method-by-method status snapshot, in fixed M1-M10 order."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    methods: tuple[MethodStatusSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_methods(self) -> MarketMethodSummary:
        ids = [item.method_id for item in self.methods]
        if len(ids) != len(set(ids)):
            raise ValueError("a market method summary cannot repeat a method_id")
        return self


class VetoId(StrEnum):
    NO_REACHABLE_ECONOMIC_BUYER = "no_reachable_economic_buyer"
    NO_MEANINGFUL_BUDGET = "no_meaningful_budget"
    MAJOR_ACCESS_OR_REGULATORY_BARRIER = "major_access_or_regulatory_barrier"
    HIGHLY_BESPOKE_DELIVERY = "highly_bespoke_delivery"
    DOMINANT_PLATFORM_SOLVES_PROBLEM = "dominant_platform_solves_problem"
    NO_QUALIFIED_BUYING_INTENT = "no_qualified_buying_intent"


class VetoStatus(StrEnum):
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"


class VetoFinding(ConfidenceValue):
    """One automatically detected veto signal; never resolved/excepted here.

    `resolved` and `accepted_exception` are human review-workflow states
    (P18) outside this module's automatic-detection scope.
    """

    veto_id: VetoId
    severity: str = Field(pattern=r"^(warning|critical)$")
    status: VetoStatus
    trigger_detail: str = Field(min_length=1, max_length=500)
    evidence_references: tuple[str, ...] = Field(min_length=1)


class VetoAssessmentResult(ConfidenceValue):
    """The deterministic, reproducible set of automatically detected vetoes."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    findings: tuple[VetoFinding, ...] = ()
    not_evaluated: tuple[str, ...] = ()
