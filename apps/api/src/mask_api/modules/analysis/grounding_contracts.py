"""Provider-neutral contracts for grounded analysis and second-pass review."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from mask_api.modules.analysis.contracts import AnalysisValue


class GroundingDisposition(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class GroundingIssueSeverity(StrEnum):
    REVIEW = "review"
    BLOCKING = "blocking"


class GroundingIssueCode(StrEnum):
    ANALYSIS_NOT_COMPLETED = "analysis_not_completed"
    ANALYSIS_REQUEST_MISMATCH = "analysis_request_mismatch"
    STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
    EVIDENCE_SPAN_MISSING = "evidence_span_missing"
    EVIDENCE_SPAN_NOT_EXACT = "evidence_span_not_exact"
    NUMERIC_CLAIM_UNGROUNDED = "numeric_claim_ungrounded"
    PROMPT_INJECTION_SIGNAL = "prompt_injection_signal"
    HIGH_IMPACT_UNVERIFIED = "high_impact_unverified"
    HIGH_IMPACT_AMBIGUOUS = "high_impact_ambiguous"
    HIGH_IMPACT_UNSUPPORTED = "high_impact_unsupported"
    VERIFICATION_UNEXPECTED = "verification_unexpected"


class GroundingIssue(AnalysisValue):
    code: GroundingIssueCode
    severity: GroundingIssueSeverity
    json_path: str = Field(min_length=1, max_length=500)
    detail: str = Field(min_length=1, max_length=500)


class InjectionSignal(AnalysisValue):
    rule_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> InjectionSignal:
        if self.end <= self.start:
            raise ValueError("injection signal end must follow start")
        return self


class HighImpactKind(StrEnum):
    FINANCIAL_VALUE = "financial_value"
    HIGH_PURCHASE_INTENT = "high_purchase_intent"
    SEVERE_PAIN = "severe_pain"
    COMPETITOR_PRICING = "competitor_pricing"
    WORKFLOW_ECONOMICS = "workflow_economics"
    INTERVIEW_CONTRADICTION = "interview_contradiction"


class HighImpactClaim(AnalysisValue):
    claim_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: HighImpactKind
    json_path: str = Field(min_length=1, max_length=500)
    proposed_value: JsonValue
    evidence_spans: tuple[str, ...] = Field(max_length=20)


class VerificationDecision(StrEnum):
    SUPPORTED = "supported"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class HighImpactVerification(AnalysisValue):
    claim_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: VerificationDecision
    verifier_reference: str = Field(min_length=1, max_length=200)
    verification_version: str = Field(min_length=1, max_length=100)
    checked_at: AwareDatetime
    note: str | None = Field(default=None, max_length=1_000)


class HighImpactVerificationRequest(AnalysisValue):
    analysis_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_text: str = Field(min_length=1, max_length=40_000)
    claims: tuple[HighImpactClaim, ...] = Field(min_length=1, max_length=200)


class GroundingReport(AnalysisValue):
    grounding_version: str = "grounding-v1"
    analysis_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: GroundingDisposition
    eligible_for_scoring_input: bool
    preserved_output: dict[str, JsonValue] | None
    scoring_input: dict[str, JsonValue] | None
    issues: tuple[GroundingIssue, ...] = Field(max_length=500)
    high_impact_claims: tuple[HighImpactClaim, ...] = Field(max_length=200)
    verifications: tuple[HighImpactVerification, ...] = Field(max_length=200)
    contradiction_paths: tuple[str, ...] = Field(max_length=200)
    injection_signals: tuple[InjectionSignal, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def scoring_input_requires_acceptance(self) -> GroundingReport:
        accepted = self.disposition == GroundingDisposition.ACCEPTED
        if accepted != self.eligible_for_scoring_input:
            raise ValueError("only accepted grounding can be scoring eligible")
        if accepted:
            if self.preserved_output is None or self.scoring_input != self.preserved_output:
                raise ValueError("accepted grounding requires its preserved output")
        elif self.scoring_input is not None:
            raise ValueError("reviewed or rejected output must remain quarantined")
        return self
