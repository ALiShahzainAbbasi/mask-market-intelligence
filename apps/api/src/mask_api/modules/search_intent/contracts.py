"""Source-neutral contracts for search-demand and buying-intent evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class SearchIntentValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class KeywordIntent(StrEnum):
    INFORMATIONAL = "informational"
    PROBLEM = "problem"
    SOLUTION = "solution"
    COMMERCIAL = "commercial"
    COMPARISON = "comparison"
    TRANSACTIONAL = "transactional"
    COMPETITOR_SWITCHING = "competitor_switching"
    UNKNOWN = "unknown"


class KeywordCompetition(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNSPECIFIED = "unspecified"
    UNKNOWN = "unknown"


class KeywordPlanNetwork(StrEnum):
    GOOGLE_SEARCH = "google_search"
    GOOGLE_SEARCH_AND_PARTNERS = "google_search_and_partners"


class MonthOfYear(IntEnum):
    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12


class YearMonth(SearchIntentValue):
    year: int = Field(ge=2000, le=2100)
    month: MonthOfYear


class MonthlySearchVolume(YearMonth):
    monthly_searches: int = Field(ge=0)


class HistoricalMetricsRequest(SearchIntentValue):
    """Public, credential-free request identity used for caching and provenance."""

    account_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    keywords: tuple[str, ...] = Field(min_length=1, max_length=200)
    geo_target_constants: tuple[str, ...] = Field(min_length=1, max_length=20)
    language_constant: str = Field(pattern=r"^languageConstants/[1-9][0-9]*$")
    network: KeywordPlanNetwork = KeywordPlanNetwork.GOOGLE_SEARCH
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    start_month: YearMonth | None = None
    end_month: YearMonth | None = None
    include_average_cpc: bool = True

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(" ".join(value.split()).casefold() for value in values)
        if any(not value or len(value) > 80 for value in normalized):
            raise ValueError("keywords must be non-blank and at most 80 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("keywords must be unique after normalization")
        return tuple(sorted(normalized))

    @field_validator("geo_target_constants")
    @classmethod
    def validate_geo_targets(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("geo target constants must be unique")
        for value in values:
            prefix, separator, identifier = value.partition("/")
            if prefix != "geoTargetConstants" or separator != "/" or not identifier.isdigit():
                raise ValueError("geo targets must use geoTargetConstants/ID resource names")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_month_range(self) -> HistoricalMetricsRequest:
        if (self.start_month is None) != (self.end_month is None):
            raise ValueError("start_month and end_month must be provided together")
        if self.start_month is not None and self.end_month is not None:
            start = (self.start_month.year, int(self.start_month.month))
            end = (self.end_month.year, int(self.end_month.month))
            if end < start:
                raise ValueError("end_month must not precede start_month")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cache_key(self) -> str:
        payload = self.model_dump(mode="json", exclude={"cache_key"})
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class KeywordHistoricalMetric(SearchIntentValue):
    keyword: str = Field(min_length=1, max_length=200)
    close_variants: tuple[str, ...] = Field(default=(), max_length=200)
    intent: KeywordIntent
    taxonomy_version: str = Field(pattern=r"^keyword-intent-v[1-9][0-9]*$")
    avg_monthly_searches: int | None = Field(default=None, ge=0)
    monthly_search_volumes: tuple[MonthlySearchVolume, ...] = Field(default=(), max_length=48)
    competition: KeywordCompetition = KeywordCompetition.UNSPECIFIED
    competition_index: int | None = Field(default=None, ge=0, le=100)
    average_cpc_micros: int | None = Field(default=None, ge=0)
    average_cpc_amount: Decimal | None = Field(default=None, ge=0)
    low_top_of_page_bid_micros: int | None = Field(default=None, ge=0)
    low_top_of_page_bid_amount: Decimal | None = Field(default=None, ge=0)
    high_top_of_page_bid_micros: int | None = Field(default=None, ge=0)
    high_top_of_page_bid_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("monthly_search_volumes")
    @classmethod
    def unique_ordered_months(
        cls, values: tuple[MonthlySearchVolume, ...]
    ) -> tuple[MonthlySearchVolume, ...]:
        keys = [(value.year, int(value.month)) for value in values]
        if len(keys) != len(set(keys)):
            raise ValueError("monthly search volumes cannot contain duplicate months")
        return tuple(sorted(values, key=lambda value: (value.year, int(value.month))))


class SearchIntentIssue(SearchIntentValue):
    code: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    keyword: str | None = Field(default=None, max_length=200)


class KeywordHistoricalBatch(SearchIntentValue):
    provider: str = "google_ads_keyword_planner"
    parser_version: str = "google-ads-historical-v1"
    request_cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: AwareDatetime
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    metrics: tuple[KeywordHistoricalMetric, ...]
    issues: tuple[SearchIntentIssue, ...] = ()


class KeywordMetricsCacheRecord(SearchIntentValue):
    request: HistoricalMetricsRequest
    batch: KeywordHistoricalBatch
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_record(self) -> KeywordMetricsCacheRecord:
        if self.batch.request_cache_key != self.request.cache_key:
            raise ValueError("cached batch does not match its request")
        if self.expires_at <= self.batch.retrieved_at:
            raise ValueError("cache expiry must follow retrieval")
        return self

    def is_fresh_at(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("cache clock must be timezone-aware")
        return self.expires_at > now
