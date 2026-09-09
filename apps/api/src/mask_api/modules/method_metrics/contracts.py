"""Typed metric inputs, breakdowns, and results for the v1 M1/M4/M5/M6/M7/M9 calculators."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from mask_api.modules.method_metrics.provenance import MethodMetricsValue, SourcedMetric
from mask_api.research_runner.contracts import MethodId

_MARKET_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"


class MethodMetricStatus(StrEnum):
    UNKNOWN = "unknown"
    PROVISIONAL = "provisional"
    COMPLETE = "complete"


class ComponentStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"


class ComponentBreakdown(MethodMetricsValue):
    """One formula component's raw input, transform output, weight, and lineage."""

    component: str = Field(min_length=1, max_length=100)
    status: ComponentStatus
    raw_value: Decimal | None = None
    transformed_score: Decimal | None = Field(default=None, ge=0, le=10)
    weight: Decimal = Field(gt=0, le=1)
    weighted_contribution: Decimal | None = None
    evidence_references: tuple[str, ...] = ()
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def status_matches_values(self) -> ComponentBreakdown:
        if self.status == ComponentStatus.MISSING:
            if self.transformed_score is not None or self.weighted_contribution is not None:
                raise ValueError("a missing component cannot carry a computed score")
            if not self.reason:
                raise ValueError("a missing component requires a reason")
        else:
            if self.transformed_score is None or self.weighted_contribution is None:
                raise ValueError("an available component requires a computed score")
            if not self.evidence_references:
                raise ValueError("an available component requires at least one evidence reference")
        return self


class MethodMetricResult(MethodMetricsValue):
    """The exact, reproducible v1 result of one M1/M4/M5/M6/M7/M9 calculation."""

    method_id: MethodId
    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    formula_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: MethodMetricStatus
    score: Decimal | None = Field(default=None, ge=0, le=10)
    breakdown: tuple[ComponentBreakdown, ...] = Field(min_length=1)
    unknown_reasons: tuple[str, ...] = ()
    provisional_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def status_matches_score(self) -> MethodMetricResult:
        if self.status == MethodMetricStatus.UNKNOWN:
            if self.score is not None:
                raise ValueError("an unknown method metric result cannot have a score")
            if not self.unknown_reasons:
                raise ValueError("an unknown method metric result requires unknown_reasons")
        else:
            if self.score is None:
                raise ValueError("a known method metric result requires a score")
        if self.status == MethodMetricStatus.PROVISIONAL and not self.provisional_reasons:
            raise ValueError("a provisional method metric result requires provisional_reasons")
        if self.status == MethodMetricStatus.COMPLETE and self.provisional_reasons:
            raise ValueError("a complete method metric result cannot carry provisional_reasons")
        return self


class M1Inputs(MethodMetricsValue):
    """Explicitly available normalized M1 quantitative-market source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    serviceable_businesses: SourcedMetric | None = None
    growth_cagr: SourcedMetric | None = None
    fragmentation_share: SourcedMetric | None = None
    annual_payroll_per_serviceable_establishment_usd: SourcedMetric | None = None
    target_band_share: SourcedMetric | None = None


class M4Inputs(MethodMetricsValue):
    """Explicitly available normalized M4 economic-pain source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    annual_problem_cost_usd: SourcedMetric | None = None
    annual_existing_paid_spend_usd: SourcedMetric | None = None
    verified_paid_workaround_share: SourcedMetric | None = None
    mean_m2_purchase_intent_0_4: SourcedMetric | None = None


class M5CompetitorGap(MethodMetricsValue):
    """One competitor/alternative's evidenced capability-gap finding."""

    competitor_id: str = Field(min_length=1, max_length=200)
    gap_score_0_10: Decimal = Field(ge=0, le=10)
    evidence_count: int = Field(ge=1)
    evidence_references: tuple[str, ...] = Field(min_length=1)


class M5Inputs(MethodMetricsValue):
    """Explicitly available normalized M5 competitive-intelligence source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    active_relevant_competitor_count: SourcedMetric | None = None
    median_annualized_customer_price_usd: SourcedMetric | None = None
    competitor_gaps: tuple[M5CompetitorGap, ...] = ()
    median_offer_similarity_0_1: SourcedMetric | None = None
    verified_reference_count: SourcedMetric | None = None

    @model_validator(mode="after")
    def unique_competitor_gaps(self) -> M5Inputs:
        ids = [item.competitor_id for item in self.competitor_gaps]
        if len(ids) != len(set(ids)):
            raise ValueError("competitor gap findings must have unique competitor ids")
        return self


class M6Inputs(MethodMetricsValue):
    """Explicitly available normalized M6 search-and-buying-intent source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    weighted_monthly_volume: SourcedMetric | None = None
    weighted_avg_cpc_usd: SourcedMetric | None = None
    high_intent_share: SourcedMetric | None = None
    growth: SourcedMetric | None = None
    switching_share: SourcedMetric | None = None
    qualified_keyword_count: SourcedMetric | None = None


class M7Inputs(MethodMetricsValue):
    """Explicitly available normalized M7 buyer-accessibility source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    accounts_with_economic_buyer: SourcedMetric | None = None
    target_accounts: SourcedMetric | None = None
    accounts_with_valid_reachable_channel: SourcedMetric | None = None
    viable_channel_count: SourcedMetric | None = None
    median_days_to_decision: SourcedMetric | None = None
    procurement_complexity_index_0_10: SourcedMetric | None = None
    active_relevant_advertisers: SourcedMetric | None = None
    account_social_presence_rate: SourcedMetric | None = None


class CapabilityRequirement(MethodMetricsValue):
    """One capability the target market/segment requires, from the registry."""

    capability_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=1, max_length=500)
    required_weight: Decimal = Field(gt=0)
    evidence_reference: str = Field(min_length=1, max_length=500)


class CapabilityCoverage(MethodMetricsValue):
    """A technical/business reviewer's coverage assessment for one capability."""

    capability_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    covered: bool
    evidence_reference: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=100)


class IntegrationRecord(MethodMetricsValue):
    """One target-market platform's integration-discovery and support status."""

    platform_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    platform_name: str = Field(min_length=1, max_length=200)
    target_market_prevalence_0_1: Decimal = Field(ge=0, le=1)
    supported: bool
    evidence_reference: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=100)


class M9Inputs(MethodMetricsValue):
    """Explicitly available normalized M9 capability-registry/integration source values."""

    market_id: str = Field(pattern=_MARKET_ID_PATTERN)
    capability_requirements: tuple[CapabilityRequirement, ...] = ()
    capability_coverage: tuple[CapabilityCoverage, ...] = ()
    integrations: tuple[IntegrationRecord, ...] = ()
    workflow_template_similarity_0_1: SourcedMetric | None = None
    recurring_solution_value_share: SourcedMetric | None = None
    comparable_internal_project_count: SourcedMetric | None = None
    delivery_complexity_index_0_10: SourcedMetric | None = None
    adjacent_high_value_workflow_count: SourcedMetric | None = None

    @model_validator(mode="after")
    def unique_capability_ids(self) -> M9Inputs:
        requirement_ids = [item.capability_id for item in self.capability_requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("capability requirements must have unique capability ids")
        coverage_ids = [item.capability_id for item in self.capability_coverage]
        if len(coverage_ids) != len(set(coverage_ids)):
            raise ValueError("capability coverage records must have unique capability ids")
        return self

    @model_validator(mode="after")
    def consistent_integration_prevalence(self) -> M9Inputs:
        platform_ids = [item.platform_id for item in self.integrations]
        if len(platform_ids) != len(set(platform_ids)):
            raise ValueError("integration records must have unique platform ids")
        total_prevalence = sum(
            (item.target_market_prevalence_0_1 for item in self.integrations), Decimal("0")
        )
        if total_prevalence > Decimal("1"):
            raise ValueError(
                "integration platform prevalence cannot exceed the total target market"
            )
        return self
