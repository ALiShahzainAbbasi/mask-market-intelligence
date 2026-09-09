"""Fail-closed Google Ads historical-metrics edge and pure response parser."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, cast

from pydantic import JsonValue, ValidationError

from mask_api.modules.search_intent.cache import KeywordMetricsCache
from mask_api.modules.search_intent.contracts import (
    HistoricalMetricsRequest,
    KeywordCompetition,
    KeywordHistoricalBatch,
    KeywordHistoricalMetric,
    KeywordPlanNetwork,
    MonthlySearchVolume,
    MonthOfYear,
    SearchIntentIssue,
)
from mask_api.modules.search_intent.taxonomy import (
    KEYWORD_INTENT_TAXONOMY_VERSION,
    classify_keyword_intent,
)
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger
from mask_api.research_runner.contracts import MethodId, SourceAccess, SourceConfiguration

GOOGLE_ADS_PROVIDER = "google_ads_keyword_planner"
GOOGLE_ADS_PARSER_VERSION = "google-ads-historical-v1"
_MICROS_PER_UNIT = Decimal("1000000")


class GoogleAdsKeywordPlannerError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__("Google Ads keyword metrics could not be completed safely")


@dataclass(frozen=True)
class GoogleAdsKeywordPlannerSettings:
    enabled: bool = False
    policy_approved: bool = False
    timeout_seconds: float = 10.0
    max_response_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Google Ads timeout must be in the interval (0, 60]")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 10_000_000:
            raise ValueError("Google Ads response byte limit is outside the safe range")


@dataclass(frozen=True)
class GoogleAdsTransportResponse:
    status_code: int
    content_type: str
    body: bytes


class GoogleAdsHistoricalMetricsTransport(Protocol):
    """Credential-bearing transport implemented only after explicit activation."""

    def generate_historical_metrics(
        self,
        request_payload: Mapping[str, JsonValue],
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> GoogleAdsTransportResponse: ...


def build_google_ads_request_payload(
    request: HistoricalMetricsRequest,
) -> dict[str, JsonValue]:
    """Map the credential-free contract to the official request field names."""

    network = {
        KeywordPlanNetwork.GOOGLE_SEARCH: "GOOGLE_SEARCH",
        KeywordPlanNetwork.GOOGLE_SEARCH_AND_PARTNERS: "GOOGLE_SEARCH_AND_PARTNERS",
    }[request.network]
    options: dict[str, JsonValue] = {"includeAverageCpc": request.include_average_cpc}
    if request.start_month is not None and request.end_month is not None:
        options["yearMonthRange"] = {
            "start": {
                "year": request.start_month.year,
                "month": request.start_month.month.name,
            },
            "end": {
                "year": request.end_month.year,
                "month": request.end_month.month.name,
            },
        }
    return {
        "keywords": list(request.keywords),
        "geoTargetConstants": list(request.geo_target_constants),
        "language": request.language_constant,
        "keywordPlanNetwork": network,
        "historicalMetricsOptions": options,
    }


def parse_google_ads_historical_metrics(
    body: bytes,
    request: HistoricalMetricsRequest,
    *,
    retrieved_at: datetime,
) -> KeywordHistoricalBatch:
    """Normalize a Google Ads REST response without network or persistence I/O."""

    if retrieved_at.tzinfo is None:
        raise GoogleAdsKeywordPlannerError("google_ads.clock_invalid")
    try:
        root = _as_mapping(cast(object, json.loads(body)), "response")
        raw_results = _as_sequence(root.get("results", []), "results")
        metrics: list[KeywordHistoricalMetric] = []
        issues: list[SearchIntentIssue] = []
        for raw_result in raw_results:
            result = _as_mapping(raw_result, "result")
            keyword = _required_text(result.get("text"), "text")
            close_variants = tuple(
                _required_text(value, "closeVariants")
                for value in _as_sequence(result.get("closeVariants", []), "closeVariants")
            )
            raw_metric = result.get("keywordMetrics")
            if raw_metric is None:
                issues.append(SearchIntentIssue(code="keyword_metrics_missing", keyword=keyword))
                metrics.append(_empty_metric(keyword, close_variants, request.currency_code))
                continue
            metric = _as_mapping(raw_metric, "keywordMetrics")
            average_cpc_micros = _optional_nonnegative_int(
                metric.get("averageCpcMicros"), "averageCpcMicros"
            )
            low_bid_micros = _optional_nonnegative_int(
                metric.get("lowTopOfPageBidMicros"), "lowTopOfPageBidMicros"
            )
            high_bid_micros = _optional_nonnegative_int(
                metric.get("highTopOfPageBidMicros"), "highTopOfPageBidMicros"
            )
            metrics.append(
                KeywordHistoricalMetric(
                    keyword=keyword,
                    close_variants=close_variants,
                    intent=classify_keyword_intent(keyword),
                    taxonomy_version=KEYWORD_INTENT_TAXONOMY_VERSION,
                    avg_monthly_searches=_optional_nonnegative_int(
                        metric.get("avgMonthlySearches"), "avgMonthlySearches"
                    ),
                    monthly_search_volumes=tuple(
                        _parse_month(value)
                        for value in _as_sequence(
                            metric.get("monthlySearchVolumes", []), "monthlySearchVolumes"
                        )
                    ),
                    competition=_competition(metric.get("competition")),
                    competition_index=_optional_bounded_int(
                        metric.get("competitionIndex"), "competitionIndex", maximum=100
                    ),
                    average_cpc_micros=average_cpc_micros,
                    average_cpc_amount=_micros_to_amount(average_cpc_micros),
                    low_top_of_page_bid_micros=low_bid_micros,
                    low_top_of_page_bid_amount=_micros_to_amount(low_bid_micros),
                    high_top_of_page_bid_micros=high_bid_micros,
                    high_top_of_page_bid_amount=_micros_to_amount(high_bid_micros),
                    currency_code=request.currency_code,
                )
            )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        ValidationError,
    ) as error:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid") from error
    return KeywordHistoricalBatch(
        request_cache_key=request.cache_key,
        retrieved_at=retrieved_at.astimezone(UTC),
        response_sha256=hashlib.sha256(body).hexdigest(),
        currency_code=request.currency_code,
        metrics=tuple(metrics),
        issues=tuple(issues),
    )


class GoogleAdsKeywordPlannerAdapter:
    """Bounded read-through adapter; no concrete credential transport is bundled."""

    def __init__(
        self,
        source_id: str,
        source: SourceConfiguration,
        settings: GoogleAdsKeywordPlannerSettings,
        transport: GoogleAdsHistoricalMetricsTransport,
        cache: KeywordMetricsCache,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_id = source_id
        self._source = source
        self._settings = settings
        self._transport = transport
        self._cache = cache
        self._now = now or (lambda: datetime.now(UTC))

    def historical_metrics(
        self, request: HistoricalMetricsRequest, ledger: BudgetLedger
    ) -> KeywordHistoricalBatch:
        self._require_enabled()
        now = self._timestamp()
        cached = self._cache.get(request, now=now)
        if cached is not None:
            return cached
        maximum = BudgetCharge(requests=1, total_bytes=self._settings.max_response_bytes)
        ledger.ensure_capacity(maximum)
        response = self._transport.generate_historical_metrics(
            build_google_ads_request_payload(request),
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=self._settings.max_response_bytes,
        )
        if response.status_code < 200 or response.status_code > 299:
            raise GoogleAdsKeywordPlannerError(
                f"google_ads.http_{response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        if len(response.body) > self._settings.max_response_bytes:
            raise GoogleAdsKeywordPlannerError("google_ads.response_too_large")
        content_type = response.content_type.split(";", maxsplit=1)[0].strip().casefold()
        if content_type != "application/json":
            raise GoogleAdsKeywordPlannerError("google_ads.content_type_invalid")
        ledger.consume(BudgetCharge(requests=1, total_bytes=len(response.body)))
        batch = parse_google_ads_historical_metrics(response.body, request, retrieved_at=now)
        self._cache.put(request, batch)
        return batch

    def _require_enabled(self) -> None:
        if (
            self._source_id != GOOGLE_ADS_PROVIDER
            or self._source.access != SourceAccess.OFFICIAL_ACCOUNT_API
            or MethodId.M6 not in self._source.methods
        ):
            raise GoogleAdsKeywordPlannerError("google_ads.source_profile_invalid")
        if self._source.operational_status != "available":
            raise GoogleAdsKeywordPlannerError("google_ads.operational_hold")
        if not self._settings.enabled:
            raise GoogleAdsKeywordPlannerError("google_ads.disabled")
        if not self._settings.policy_approved:
            raise GoogleAdsKeywordPlannerError("google_ads.policy_not_approved")

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise GoogleAdsKeywordPlannerError("google_ads.clock_invalid")
        return value.astimezone(UTC)


def _empty_metric(
    keyword: str, close_variants: tuple[str, ...], currency_code: str
) -> KeywordHistoricalMetric:
    return KeywordHistoricalMetric(
        keyword=keyword,
        close_variants=close_variants,
        intent=classify_keyword_intent(keyword),
        taxonomy_version=KEYWORD_INTENT_TAXONOMY_VERSION,
        currency_code=currency_code,
    )


def _as_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return cast(dict[str, object], value)


def _as_sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return cast(list[object], value)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return value.strip()


def _optional_nonnegative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    try:
        parsed = int(value) if isinstance(value, (int, str)) else -1
    except ValueError as error:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid") from error
    if parsed < 0 or (isinstance(value, str) and str(parsed) != value):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return parsed


def _optional_bounded_int(value: object, field: str, *, maximum: int) -> int | None:
    parsed = _optional_nonnegative_int(value, field)
    if parsed is not None and parsed > maximum:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return parsed


def _competition(value: object) -> KeywordCompetition:
    if value is None:
        return KeywordCompetition.UNSPECIFIED
    if not isinstance(value, str):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    mapping = {
        "LOW": KeywordCompetition.LOW,
        "MEDIUM": KeywordCompetition.MEDIUM,
        "HIGH": KeywordCompetition.HIGH,
        "UNSPECIFIED": KeywordCompetition.UNSPECIFIED,
        "UNKNOWN": KeywordCompetition.UNKNOWN,
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid") from error


def _parse_month(value: object) -> MonthlySearchVolume:
    record = _as_mapping(value, "monthlySearchVolumes")
    month = record.get("month")
    if not isinstance(month, str):
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    try:
        month_value = MonthOfYear[month]
    except KeyError as error:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid") from error
    year = _optional_bounded_int(record.get("year"), "year", maximum=2100)
    searches = _optional_nonnegative_int(record.get("monthlySearches"), "monthlySearches")
    if year is None or year < 2000 or searches is None:
        raise GoogleAdsKeywordPlannerError("google_ads.response_invalid")
    return MonthlySearchVolume(year=year, month=month_value, monthly_searches=searches)


def _micros_to_amount(value: int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value) / _MICROS_PER_UNIT
