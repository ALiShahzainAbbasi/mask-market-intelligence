"""Typed contracts for the v1 machine-readable market research report."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from mask_api.modules.confidence.contracts import ConfidenceResult, MethodCompletenessState
from mask_api.modules.market_scoring.contracts import MarketScoreSnapshot
from mask_api.research_runner.contracts import MethodId

_MARKET_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"


class ReportingValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SourceInventoryEntry(ReportingValue):
    """One registered source's identity and current operational status.

    Attempted/successful/unavailable counts for an actual run are a separate,
    optional `SourceAttemptSummary` -- this entry alone only says what the
    source *is*, not what happened when a specific run used it.
    """

    source_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    access: str = Field(min_length=1, max_length=50)
    cost_class: Literal["free", "paid", "mixed"]
    operational_status: str = Field(min_length=1, max_length=50)
    methods: tuple[MethodId, ...]


class SourceAttemptOutcome(ReportingValue):
    """What happened when one run actually tried to use one source.

    A5-family sources it never tried stay entirely absent from a run's
    attempt list -- this is never backfilled with an invented "not
    attempted" placeholder; absence itself is the signal.
    """

    source_id: str = Field(min_length=1, max_length=100)
    outcome: Literal[
        "successful",
        "unavailable",
        "source_unavailable_quota",
        "not_relevant",
    ]
    detail: str | None = Field(default=None, max_length=500)
    requests_used: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)


class MethodReportEntry(ReportingValue):
    """One method's report-facing summary, wrapping its own full result.

    `detail` is the method's own already-validated result contract, dumped
    to JSON by the caller (`M2Result`/`M3Result`/`MethodMetricResult`) --
    this module never re-derives or reshapes method internals, only
    presents them.
    """

    method_id: MethodId
    raw_score: Decimal | None = Field(default=None, ge=0, le=10)
    confidence: ConfidenceResult | None = None
    risk_adjusted_score: Decimal | None = Field(default=None, ge=0, le=10)
    completeness: MethodCompletenessState
    detail: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def risk_adjusted_requires_raw_and_confidence(self) -> MethodReportEntry:
        if self.risk_adjusted_score is not None and (
            self.raw_score is None
            or self.confidence is None
            or self.confidence.numeric_confidence is None
        ):
            raise ValueError("a risk-adjusted score requires both a raw score and known confidence")
        return self


class ReportPackage(ReportingValue):
    """The full v1 machine-readable market research report."""

    schema_version: Literal["report-v1"] = "report-v1"
    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    market_name: str = Field(min_length=1, max_length=200)
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    generated_at: AwareDatetime
    snapshot: MarketScoreSnapshot
    methods: tuple[MethodReportEntry, ...] = Field(min_length=1)
    source_inventory: tuple[SourceInventoryEntry, ...]
    source_attempts: tuple[SourceAttemptOutcome, ...] = ()
    executive_summary: str = Field(min_length=1, max_length=4_000)
    next_recommended_action: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def unique_methods_and_sources(self) -> ReportPackage:
        method_ids = [item.method_id for item in self.methods]
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("a report cannot repeat a method_id")
        source_ids = [item.source_id for item in self.source_inventory]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("a report cannot repeat a source_id in its inventory")
        return self
