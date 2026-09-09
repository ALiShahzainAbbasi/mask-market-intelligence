"""Strict, versioned configuration contracts for autonomous research runs."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MethodId(StrEnum):
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"
    M6 = "M6"
    M7 = "M7"
    M8 = "M8"
    M9 = "M9"
    M10 = "M10"


class Geography(StrictConfiguration):
    country: str = Field(pattern=r"^[A-Z]{2}$")
    regions: tuple[str, ...] = ()


class IndustryCodes(StrictConfiguration):
    naics: tuple[int, ...] = Field(min_length=1)

    @field_validator("naics")
    @classmethod
    def valid_naics_codes(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if len(values) != len(set(values)):
            raise ValueError("NAICS codes must be unique")
        if any(value < 11 or value > 999_999 for value in values):
            raise ValueError("NAICS codes must contain two to six digits")
        return values


class CompanyBand(StrictConfiguration):
    employees_min: int = Field(ge=1)
    employees_max: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered_band(self) -> CompanyBand:
        if self.employees_max < self.employees_min:
            raise ValueError("employees_max must be greater than or equal to employees_min")
        return self


class ValidationBudget(StrictConfiguration):
    enabled: bool = False
    max_budget_usd: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def enabled_budget_is_positive(self) -> ValidationBudget:
        if self.enabled and self.max_budget_usd <= 0:
            raise ValueError("enabled validation requires a positive max_budget_usd")
        return self


class RunBudgetConfiguration(StrictConfiguration):
    max_requests: int = Field(default=100, ge=0, le=100_000)
    max_documents: int = Field(default=500, ge=0, le=1_000_000)
    max_total_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=10 * 1024 * 1024 * 1024)
    max_duration_seconds: int = Field(default=3_600, ge=1, le=604_800)
    max_paid_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)


class MarketConfiguration(StrictConfiguration):
    market_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=200)
    geography: Geography
    industry_codes: IndustryCodes
    company_band: CompanyBand
    buyer_titles: tuple[str, ...] = Field(min_length=1)
    seed_terms: tuple[str, ...] = Field(min_length=1)
    seed_problems: tuple[str, ...] = Field(min_length=1)
    research_window_days: int = Field(ge=1, le=3_650)
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    run_budget: RunBudgetConfiguration = Field(default_factory=RunBudgetConfiguration)
    validation: ValidationBudget = Field(default_factory=ValidationBudget)
    source_policy_profile: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name cannot be blank")
        return stripped

    @field_validator("buyer_titles", "seed_terms", "seed_problems")
    @classmethod
    def unique_non_blank_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(value.strip() for value in values)
        if any(not value for value in cleaned):
            raise ValueError("configuration lists cannot contain blank values")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("configuration lists cannot contain duplicates")
        return cleaned


class TransformKind(StrEnum):
    IDENTITY = "identity"
    LINEAR = "linear"
    REVERSE_LINEAR = "reverse_linear"
    LOG_SCALE = "log_scale"
    MULTIPLY = "multiply"
    COMPLEMENT = "complement"
    WEIGHTED_MEAN_SQRT = "weighted_mean_sqrt"
    WEIGHTED_COVERAGE = "weighted_coverage"
    COMPOSITE = "composite"


class TransformConfiguration(StrictConfiguration):
    kind: TransformKind
    low: Decimal | None = None
    high: Decimal | None = None
    multiplier: Decimal | None = None
    expression: str | None = None
    special_case: str | None = None

    @model_validator(mode="after")
    def required_parameters_are_present(self) -> TransformConfiguration:
        if self.kind in {
            TransformKind.LINEAR,
            TransformKind.REVERSE_LINEAR,
            TransformKind.LOG_SCALE,
        }:
            if self.low is None or self.high is None or self.high <= self.low:
                raise ValueError(f"{self.kind} requires ordered low/high values")
        if self.kind in {TransformKind.MULTIPLY, TransformKind.COMPLEMENT}:
            if self.multiplier is None or self.multiplier <= 0:
                raise ValueError(f"{self.kind} requires a positive multiplier")
        if (
            self.kind
            in {
                TransformKind.COMPOSITE,
                TransformKind.WEIGHTED_COVERAGE,
                TransformKind.WEIGHTED_MEAN_SQRT,
            }
            and not self.expression
        ):
            raise ValueError(f"{self.kind} requires an audit expression")
        return self


class FormulaComponent(StrictConfiguration):
    raw_input: str = Field(min_length=1)
    weight: Decimal = Field(gt=0, le=1)
    transform: TransformConfiguration


class AggregationConfiguration(StrictConfiguration):
    kind: Literal["weighted_sum", "max_and_weighted_top"]
    expression: str
    max_weight: Decimal | None = Field(default=None, gt=0, le=1)
    mean_weight: Decimal | None = Field(default=None, gt=0, le=1)
    top_n: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_aggregation(self) -> AggregationConfiguration:
        if self.kind == "max_and_weighted_top":
            if self.max_weight is None or self.mean_weight is None or self.top_n is None:
                raise ValueError("max_and_weighted_top requires weights and top_n")
            if self.max_weight + self.mean_weight != Decimal("1"):
                raise ValueError("aggregation weights must total exactly 1")
        return self


class CompletenessRule(StrictConfiguration):
    required_all: tuple[str, ...] = ()
    required_at_least_count: int | None = Field(default=None, ge=1)
    required_at_least_from: tuple[str, ...] = ()
    unknown_rule: str
    incomplete_rule: str | None = None

    @model_validator(mode="after")
    def valid_partial_requirement(self) -> CompletenessRule:
        if (self.required_at_least_count is None) != (not self.required_at_least_from):
            raise ValueError("partial completeness requires count and field list together")
        if self.required_at_least_count is not None and self.required_at_least_count > len(
            self.required_at_least_from
        ):
            raise ValueError("partial completeness count exceeds available fields")
        return self


class SampleRule(StrictConfiguration):
    unknown_below: int | None = Field(default=None, ge=0)
    provisional_below: int | None = Field(default=None, ge=1)
    full_target: int | None = Field(default=None, ge=1)
    full_target_any_of: dict[str, int] = Field(default_factory=dict)
    unit: str


class MethodFormula(StrictConfiguration):
    name: str
    overall_weight: Decimal = Field(gt=0, le=1)
    components: dict[str, FormulaComponent]
    aggregation: AggregationConfiguration
    completeness: CompletenessRule
    sample: SampleRule | None = None

    @model_validator(mode="after")
    def component_weights_total_one(self) -> MethodFormula:
        if sum((item.weight for item in self.components.values()), Decimal("0")) != Decimal("1"):
            raise ValueError("method component weights must total exactly 1")
        return self


class ConfidenceConfiguration(StrictConfiguration):
    weights: dict[str, Decimal]
    evidence_quality_levels: dict[str, Decimal]
    low_below: Decimal
    high_at_least: Decimal
    expression: str
    sample_targets: dict[MethodId, int | dict[str, int]]

    @model_validator(mode="after")
    def valid_confidence(self) -> ConfidenceConfiguration:
        if sum(self.weights.values(), Decimal("0")) != Decimal("1"):
            raise ValueError("confidence weights must total exactly 1")
        if self.low_below >= self.high_at_least:
            raise ValueError("confidence label boundaries are invalid")
        if set(self.evidence_quality_levels) != {"L1", "L2", "L3", "L4", "L5"}:
            raise ValueError("confidence requires L1-L5 evidence mappings")
        return self


class GateConfiguration(StrictConfiguration):
    name: str
    methods: tuple[MethodId, ...]
    minimum_score: Decimal | None = Field(default=None, ge=0, le=10)
    preferred_score: Decimal | None = Field(default=None, ge=0, le=10)
    minimum_confidence: Decimal | None = Field(default=None, ge=0, le=100)
    rules: tuple[str, ...]


class VetoConfiguration(StrictConfiguration):
    name: str
    trigger: str


class FormulaConfiguration(StrictConfiguration):
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    overall_weights: dict[MethodId, Decimal]
    method_formulas: dict[MethodId, MethodFormula]
    confidence: ConfidenceConfiguration
    gates: dict[str, GateConfiguration]
    vetoes: dict[str, VetoConfiguration]

    @model_validator(mode="after")
    def complete_method_set(self) -> FormulaConfiguration:
        expected = set(MethodId)
        if set(self.overall_weights) != expected or set(self.method_formulas) != expected:
            raise ValueError("formula configuration must define M1 through M10 exactly once")
        if sum(self.overall_weights.values(), Decimal("0")) != Decimal("1"):
            raise ValueError("overall method weights must total exactly 1")
        for method, formula in self.method_formulas.items():
            if formula.overall_weight != self.overall_weights[method]:
                raise ValueError(f"{method} overall weight differs from the approved weight")
        return self


class SourceAccess(StrEnum):
    OFFICIAL_API = "official_api"
    COMMERCIAL_API = "commercial_api"
    APPROVED_API = "approved_api"
    PERMITTED_COLLECTOR = "permitted_collector"
    OFFICIAL_ACCOUNT_API = "official_account_api"


class SourceConfiguration(StrictConfiguration):
    source_family: str
    name: str
    methods: tuple[MethodId, ...]
    access: SourceAccess
    evidence_use: str
    reference: str
    policy_status: Literal["allowed", "conditional"]
    default_enabled: bool = False
    credential_required: bool
    cost_class: Literal["free", "paid", "mixed"]
    operational_status: Literal[
        "available", "credential_pending", "approval_pending", "paid_hold"
    ] = "available"

    @field_validator("methods")
    @classmethod
    def source_has_methods(cls, values: tuple[MethodId, ...]) -> tuple[MethodId, ...]:
        if not values:
            raise ValueError("a source must support at least one method")
        if len(values) != len(set(values)):
            raise ValueError("source methods must be unique")
        return values

    @model_validator(mode="after")
    def unavailable_sources_stay_disabled(self) -> SourceConfiguration:
        if self.operational_status != "available" and self.default_enabled:
            raise ValueError("an unavailable source cannot be enabled by default")
        return self


class SignalRoute(StrictConfiguration):
    primary: tuple[str, ...]
    fallback: tuple[str, ...]
    failure_rule: str

    @model_validator(mode="after")
    def route_has_sources(self) -> SignalRoute:
        if not self.primary:
            raise ValueError("a signal route must define at least one primary source")
        if set(self.primary) & set(self.fallback):
            raise ValueError("primary and fallback sources must not overlap")
        return self


class SourceProfile(StrictConfiguration):
    profile_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    profile_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    sources: dict[str, SourceConfiguration]
    signal_routes: dict[str, SignalRoute]

    @model_validator(mode="after")
    def routes_reference_known_sources(self) -> SourceProfile:
        known = set(self.sources)
        referenced = {
            source
            for route in self.signal_routes.values()
            for source in (*route.primary, *route.fallback)
        }
        missing = referenced - known
        if missing:
            raise ValueError(f"signal routes reference unknown sources: {sorted(missing)}")
        return self
