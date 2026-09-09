from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.search_intent.cache import ArtifactKeywordMetricsCache
from mask_api.modules.search_intent.contracts import (
    HistoricalMetricsRequest,
    KeywordCompetition,
    KeywordIntent,
    KeywordPlanNetwork,
    MonthOfYear,
    YearMonth,
)
from mask_api.modules.search_intent.google_ads import (
    GoogleAdsKeywordPlannerAdapter,
    GoogleAdsKeywordPlannerError,
    GoogleAdsKeywordPlannerSettings,
    GoogleAdsTransportResponse,
    build_google_ads_request_payload,
    parse_google_ads_historical_metrics,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.configuration import load_source_profile
from mask_api.research_runner.local_artifacts import LocalArtifactStore

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = Path(__file__).parent / "fixtures/google_ads_historical.json"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def request() -> HistoricalMetricsRequest:
    return HistoricalMetricsRequest(
        account_scope_sha256="a" * 64,
        keywords=("Field   Service Software Pricing", "dispatch alternatives to spreadsheets"),
        geo_target_constants=("geoTargetConstants/2840",),
        language_constant="languageConstants/1000",
        network=KeywordPlanNetwork.GOOGLE_SEARCH,
        currency_code="USD",
        start_month=YearMonth(year=2025, month=MonthOfYear.JANUARY),
        end_month=YearMonth(year=2026, month=MonthOfYear.JANUARY),
    )


def ledger() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=2,
            max_documents=0,
            max_total_bytes=2_000_000,
            max_duration_seconds=30,
            max_paid_cost_usd=Decimal("0"),
        )
    )


@dataclass
class FakeTransport:
    response: GoogleAdsTransportResponse
    calls: list[dict[str, object]] = field(default_factory=list)

    def generate_historical_metrics(
        self, request_payload: object, **kwargs: object
    ) -> GoogleAdsTransportResponse:
        self.calls.append({"request_payload": request_payload, **kwargs})
        return self.response


def source(*, available: bool):
    configured = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value.sources[
        "google_ads_keyword_planner"
    ]
    if available:
        return configured.model_copy(update={"operational_status": "available"})
    return configured


def settings(**changes: object) -> GoogleAdsKeywordPlannerSettings:
    values: dict[str, object] = {
        "enabled": True,
        "policy_approved": True,
        "timeout_seconds": 5,
        "max_response_bytes": 100_000,
    }
    values.update(changes)
    return GoogleAdsKeywordPlannerSettings(**values)  # type: ignore[arg-type]


def response() -> GoogleAdsTransportResponse:
    return GoogleAdsTransportResponse(200, "application/json", FIXTURE.read_bytes())


def test_request_is_normalized_hashed_and_maps_to_official_fields() -> None:
    requested = request()
    equivalent = HistoricalMetricsRequest(
        **{
            **requested.model_dump(exclude={"cache_key"}),
            "keywords": tuple(reversed(requested.keywords)),
        }
    )

    assert requested.keywords == (
        "dispatch alternatives to spreadsheets",
        "field service software pricing",
    )
    assert len(requested.cache_key) == 64
    assert equivalent.cache_key == requested.cache_key
    payload = build_google_ads_request_payload(requested)
    assert payload["keywordPlanNetwork"] == "GOOGLE_SEARCH"
    assert payload["historicalMetricsOptions"] == {
        "includeAverageCpc": True,
        "yearMonthRange": {
            "start": {"year": 2025, "month": "JANUARY"},
            "end": {"year": 2026, "month": "JANUARY"},
        },
    }
    assert "account_scope_sha256" not in payload


def test_fixture_parser_preserves_cpc_bids_competition_and_unknowns() -> None:
    batch = parse_google_ads_historical_metrics(FIXTURE.read_bytes(), request(), retrieved_at=NOW)

    assert len(batch.metrics) == 3
    first = batch.metrics[0]
    assert first.intent == KeywordIntent.COMMERCIAL_RESEARCH
    assert first.avg_monthly_searches == 1000
    assert first.competition == KeywordCompetition.HIGH
    assert first.competition_index == 82
    assert first.average_cpc_micros == 2_750_000
    assert first.average_cpc_amount == Decimal("2.75")
    assert first.low_top_of_page_bid_amount == Decimal("1.25")
    assert first.high_top_of_page_bid_amount == Decimal("6.5")
    assert [item.month for item in first.monthly_search_volumes] == [
        MonthOfYear.JANUARY,
        MonthOfYear.FEBRUARY,
    ]
    assert batch.metrics[1].intent == KeywordIntent.COMPETITOR_SWITCHING
    assert batch.metrics[1].average_cpc_amount is None
    assert batch.metrics[2].intent == KeywordIntent.UNKNOWN
    assert batch.metrics[2].avg_monthly_searches is None
    assert [(issue.code, issue.keyword) for issue in batch.issues] == [
        ("keyword_metrics_missing", "unclassified niche phrase")
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"results": {}}',
        b'{"results": [{"text": "x", "keywordMetrics": {"competitionIndex": "101"}}]}',
        b'{"results": [{"text": "x", "keywordMetrics": {"averageCpcMicros": "-1"}}]}',
        b'{"results": [{"text": "x", "keywordMetrics": {"competition": "INVALID"}}]}',
    ],
)
def test_parser_rejects_malformed_or_out_of_range_provider_data(payload: bytes) -> None:
    with pytest.raises(GoogleAdsKeywordPlannerError) as captured:
        parse_google_ads_historical_metrics(payload, request(), retrieved_at=NOW)

    assert captured.value.code == "google_ads.response_invalid"


def test_default_profile_hold_stops_before_cache_or_transport(tmp_path: Path) -> None:
    transport = FakeTransport(response())
    adapter = GoogleAdsKeywordPlannerAdapter(
        "google_ads_keyword_planner",
        source(available=False),
        settings(),
        transport,
        ArtifactKeywordMetricsCache(LocalArtifactStore(tmp_path)),
        now=lambda: NOW,
    )

    with pytest.raises(GoogleAdsKeywordPlannerError) as captured:
        adapter.historical_metrics(request(), ledger())

    assert captured.value.code == "google_ads.operational_hold"
    assert transport.calls == []


def test_available_fixture_transport_is_bounded_cached_and_read_through(tmp_path: Path) -> None:
    transport = FakeTransport(response())
    cache = ArtifactKeywordMetricsCache(LocalArtifactStore(tmp_path))
    adapter = GoogleAdsKeywordPlannerAdapter(
        "google_ads_keyword_planner",
        source(available=True),
        settings(),
        transport,
        cache,
        now=lambda: NOW,
    )
    budget = ledger()

    first = adapter.historical_metrics(request(), budget)
    second = adapter.historical_metrics(request(), budget)

    assert second == first
    assert len(transport.calls) == 1
    assert budget.usage.requests == 1
    assert budget.usage.total_bytes == len(FIXTURE.read_bytes())
    assert transport.calls[0]["max_bytes"] == 100_000
    request_payload = transport.calls[0]["request_payload"]
    assert isinstance(request_payload, dict)
    assert "account_scope_sha256" not in request_payload


@pytest.mark.parametrize(
    ("configured", "code"),
    [
        (settings(enabled=False), "google_ads.disabled"),
        (settings(policy_approved=False), "google_ads.policy_not_approved"),
    ],
)
def test_activation_controls_stop_before_transport(
    tmp_path: Path, configured: GoogleAdsKeywordPlannerSettings, code: str
) -> None:
    transport = FakeTransport(response())
    adapter = GoogleAdsKeywordPlannerAdapter(
        "google_ads_keyword_planner",
        source(available=True),
        configured,
        transport,
        ArtifactKeywordMetricsCache(LocalArtifactStore(tmp_path)),
        now=lambda: NOW,
    )

    with pytest.raises(GoogleAdsKeywordPlannerError) as captured:
        adapter.historical_metrics(request(), ledger())

    assert captured.value.code == code
    assert transport.calls == []
