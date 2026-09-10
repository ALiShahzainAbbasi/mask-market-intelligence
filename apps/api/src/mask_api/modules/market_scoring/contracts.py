"""Typed contracts for the v1 overall score, gate, and snapshot engine."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from mask_api.modules.confidence.contracts import (
    ConfidenceResult,
    MethodStatusSnapshot,
    VetoAssessmentResult,
)
from mask_api.research_runner.contracts import MethodId

_MARKET_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"


class MarketScoringValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AutomatedResearchScore(MarketScoringValue):
    """The provisional, fully-automatic weighted sum of available method scores.

    Never the market's final/approved score. SCORING.md: "The UI may show a
    provisional contribution (sum of available weighted contributions) but
    must not label it the final score or rank it as though complete." The
    sum is over each contributing method's *configured* overall weight, not
    renormalized across only the available methods, so it is naturally lower
    when methods are missing rather than inflated to look complete.
    """

    score: Decimal | None = Field(default=None, ge=0, le=10)
    observed_weight: Decimal = Field(ge=0, le=1)
    contributing_methods: tuple[MethodId, ...]
    missing_methods: tuple[MethodId, ...]

    @model_validator(mode="after")
    def score_matches_contributions(self) -> AutomatedResearchScore:
        if not self.contributing_methods and self.score is not None:
            raise ValueError(
                "an automated research score with no contributing methods must be null"
            )
        if self.contributing_methods and self.score is None:
            raise ValueError(
                "an automated research score with contributing methods requires a value"
            )
        return self


class FinalValidatedScoreStatus(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"


class FinalValidatedScore(MarketScoringValue):
    """SCORING.md's strict overall score: null until all ten REVIEWED scores are approved.

    No human-review workflow exists yet (P12's reviewed-score approval UI),
    so this is always `not_ready` in the current offline pipeline. The
    contract exists so downstream reporting has a stable shape once a
    reviewed-score workflow is built, instead of guessing at one later.
    """

    status: FinalValidatedScoreStatus
    score: Decimal | None = Field(default=None, ge=0, le=10)

    @model_validator(mode="after")
    def score_requires_ready(self) -> FinalValidatedScore:
        if self.status == FinalValidatedScoreStatus.NOT_READY and self.score is not None:
            raise ValueError("a not-ready final validated score cannot carry a score")
        if self.status == FinalValidatedScoreStatus.READY and self.score is None:
            raise ValueError("a ready final validated score requires a score")
        return self


class GateId(StrEnum):
    GATE_1 = "gate_1"
    GATE_2 = "gate_2"
    GATE_3 = "gate_3"
    GATE_4 = "gate_4"


class GateResultStatus(StrEnum):
    NOT_READY = "not_ready"
    BLOCKED = "blocked"
    ELIGIBLE_TO_ADVANCE = "eligible_to_advance"
    DOES_NOT_MEET_GATE = "does_not_meet_gate"
    FOUNDER_REVIEW_REQUIRED = "founder_review_required"


class GateEvaluation(MarketScoringValue):
    """One gate's deterministic readiness result; never a stage transition.

    SCORING.md: "Humans record the actual decision: advance, hold, reject,
    or, at Gate 4, select. Eligibility never changes a market stage
    automatically." This contract stops at eligibility.
    """

    gate_id: GateId
    status: GateResultStatus
    gate_score: Decimal | None = Field(default=None, ge=0, le=10)
    gate_confidence: ConfidenceResult | None = None
    missing_methods: tuple[MethodId, ...] = ()
    unresolved_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def eligible_has_no_unresolved_reasons(self) -> GateEvaluation:
        if self.status == GateResultStatus.ELIGIBLE_TO_ADVANCE and self.unresolved_reasons:
            raise ValueError("an eligible-to-advance gate cannot carry unresolved reasons")
        if self.status != GateResultStatus.ELIGIBLE_TO_ADVANCE and not self.unresolved_reasons:
            raise ValueError("a non-eligible gate result requires unresolved_reasons")
        return self


class SnapshotCompatibilityKey(MarketScoringValue):
    """The exact fields two snapshots must share to be ranked together.

    SCORING.md section 10: "Markets may be ranked together only when
    snapshots use the same market-definition rules, research profile,
    scoring configuration, and comparable evidence cutoff policy."
    """

    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    market_definition_version: str = Field(min_length=1, max_length=100)
    research_profile: str = Field(min_length=1, max_length=100)


def snapshots_are_comparable(
    left: SnapshotCompatibilityKey,
    right: SnapshotCompatibilityKey,
) -> bool:
    return left == right


class MarketScoreSnapshot(MarketScoringValue):
    """The immutable, reproducible v1 snapshot of one market scoring run.

    A new recalculation always produces a new snapshot; nothing here is
    mutated in place. `inputs_sha256` lets a caller verify that identical
    eligible inputs and configuration reproduce bit-for-bit identical
    computed values (score/gate/veto fields), independent of `snapshot_id`
    and `generated_at`, which are unique per run by design.
    """

    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    compatibility: SnapshotCompatibilityKey
    generated_at: AwareDatetime
    methods: tuple[MethodStatusSnapshot, ...] = Field(min_length=1)
    automated_research_score: AutomatedResearchScore
    final_validated_score: FinalValidatedScore
    overall_confidence: ConfidenceResult
    gates: tuple[GateEvaluation, ...] = Field(min_length=1)
    vetoes: VetoAssessmentResult
    inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def unique_methods_and_gates(self) -> MarketScoreSnapshot:
        method_ids = [item.method_id for item in self.methods]
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("a market score snapshot cannot repeat a method_id")
        gate_ids = [item.gate_id for item in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("a market score snapshot cannot repeat a gate_id")
        return self
