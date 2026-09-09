from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.discovery.brave import (
    BRAVE_API_VERSION,
    BRAVE_ENDPOINT,
    BraveSearchAdapter,
    BraveSearchSettings,
    BraveTransportResponse,
    DiscoveryError,
    UrllibBraveTransport,
)
from mask_api.modules.discovery.contracts import DiscoveryPlan, DiscoveryQuery
from mask_api.research_runner.budgets import BudgetLedger, BudgetLimitExceeded, RunBudgetLimits
from mask_api.research_runner.configuration import load_source_profile
from mask_api.research_runner.contracts import MethodId
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@dataclass
class FakeTransport:
    responses: list[BraveTransportResponse]
    calls: list[dict[str, object]] = field(default_factory=list)

    def search(self, **kwargs: object) -> BraveTransportResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeHttpResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def read(self, _limit: int) -> bytes:
        return b'{"query": {}, "web": {"results": []}}'

    def close(self) -> None:
        return None


@dataclass
class FakeOpener:
    request: object | None = None
    timeout: float | None = None

    def open(self, request: object, timeout: float) -> FakeHttpResponse:
        self.request = request
        self.timeout = timeout
        return FakeHttpResponse()


def source():
    configured = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value.sources[
        "brave_search"
    ]
    return configured.model_copy(update={"operational_status": "available"})


def query() -> DiscoveryQuery:
    return DiscoveryQuery(
        query_id="a" * 64,
        method_id=MethodId.M5,
        intent="pricing",
        query="HVAC field service software pricing",
        source_terms=("HVAC field service",),
    )


def plan() -> DiscoveryPlan:
    return DiscoveryPlan(market_id="us_hvac_10_99", queries=(query(),))


def ledger(*, cost: str = "1", total_bytes: int = 5_000_000) -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=10,
            max_documents=100,
            max_total_bytes=total_bytes,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal(cost),
        )
    )


def settings(**changes: object) -> BraveSearchSettings:
    values: dict[str, object] = {
        "enabled": True,
        "policy_approved": True,
        "api_key": SecretStr("fixture-not-a-real-key"),
        "count": 10,
        "max_pages_per_query": 2,
        "timeout_seconds": 5,
        "max_response_bytes": 100_000,
        "cost_per_request_usd": Decimal("0.01"),
    }
    values.update(changes)
    return BraveSearchSettings(**values)  # type: ignore[arg-type]


def response(
    name: str, status: int = 200, content_type: str = "application/json"
) -> BraveTransportResponse:
    return BraveTransportResponse(
        status_code=status,
        content_type=content_type,
        body=(FIXTURES / name).read_bytes(),
    )


def adapter(
    transport: FakeTransport, configured: BraveSearchSettings | None = None
) -> BraveSearchAdapter:
    return BraveSearchAdapter(
        "brave_search",
        source(),
        configured or settings(),
        transport,
        now=lambda: NOW,
    )


def test_search_pages_are_bounded_deduplicated_and_provenance_rich() -> None:
    transport = FakeTransport([response("brave_page_1.json"), response("brave_page_2.json")])
    budget = ledger()

    result = adapter(transport).discover(plan(), budget, country="US", language="en")

    assert len(transport.calls) == 2
    assert [call["offset"] for call in transport.calls] == [0, 1]
    assert len(result.pages) == 2
    assert len(result.results) == 2
    assert result.results[0].url == "https://example.com/hvac/operations"
    assert result.results[1].url == "https://example.org/research/hvac-pricing"
    assert result.results[1].rank == 12
    assert result.pages[0].raw_response == (FIXTURES / "brave_page_1.json").read_bytes()
    assert len(result.pages[0].response_sha256) == 64
    assert budget.usage.requests == 2
    assert budget.usage.total_bytes == sum(len(page.raw_response) for page in result.pages)
    assert budget.usage.paid_cost_usd == Decimal("0.02")
    assert isinstance(transport.calls[0]["api_key"], SecretStr)


def test_standard_transport_uses_fixed_endpoint_version_and_secret_header() -> None:
    opener = FakeOpener()
    transport = UrllibBraveTransport()
    transport._opener = opener  # type: ignore[assignment]

    result = transport.search(
        query="HVAC software pricing",
        country="US",
        language="en",
        count=10,
        offset=0,
        api_key=SecretStr("fixture-not-a-real-key"),
        timeout_seconds=5,
        max_bytes=10_000,
    )

    assert result.status_code == 200
    assert opener.timeout == 5
    request = opener.request
    assert request is not None
    request_url = request.full_url  # type: ignore[attr-defined]
    headers = {key.casefold(): value for key, value in request.header_items()}  # type: ignore[attr-defined]
    assert request_url.startswith(f"{BRAVE_ENDPOINT}?")
    assert "fixture-not-a-real-key" not in request_url
    assert headers["x-subscription-token"] == "fixture-not-a-real-key"
    assert headers["api-version"] == BRAVE_API_VERSION
    assert headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    ("configured", "code"),
    [
        (settings(enabled=False), "brave.disabled"),
        (settings(policy_approved=False), "brave.policy_not_approved"),
        (settings(api_key=None), "brave.credential_missing"),
        (settings(cost_per_request_usd=Decimal("0")), "brave.request_cost_missing"),
    ],
)
def test_disabled_policy_credential_and_cost_fail_before_transport(
    configured: BraveSearchSettings, code: str
) -> None:
    transport = FakeTransport([])

    with pytest.raises(DiscoveryError) as captured:
        adapter(transport, configured).discover(plan(), ledger(), country="US", language="en")

    assert captured.value.code == code
    assert transport.calls == []


def test_zero_paid_budget_fails_before_transport() -> None:
    transport = FakeTransport([])

    with pytest.raises(DiscoveryError) as captured:
        adapter(transport).discover(plan(), ledger(cost="0"), country="US", language="en")

    assert captured.value.code == "brave.paid_budget_disabled"
    assert transport.calls == []


def test_default_lean_profile_keeps_paid_search_on_hold() -> None:
    configured = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value.sources[
        "brave_search"
    ]
    transport = FakeTransport([])
    held = BraveSearchAdapter(
        "brave_search",
        configured,
        settings(),
        transport,
        now=lambda: NOW,
    )

    with pytest.raises(DiscoveryError) as captured:
        held.discover(plan(), ledger(), country="US", language="en")

    assert captured.value.code == "brave.operational_hold"
    assert transport.calls == []


def test_maximum_response_reservation_stops_before_transport() -> None:
    transport = FakeTransport([])

    with pytest.raises(BudgetLimitExceeded):
        adapter(transport).discover(plan(), ledger(total_bytes=99_999), country="US", language="en")

    assert transport.calls == []


def test_http_content_type_and_malformed_payload_fail_safely() -> None:
    cases = [
        (
            BraveTransportResponse(429, "application/json", b"", retry_after_seconds=3),
            "brave.http_429",
            True,
        ),
        (
            response("brave_page_1.json", content_type="text/html"),
            "brave.content_type_invalid",
            False,
        ),
        (
            BraveTransportResponse(200, "application/json", b"not-json"),
            "brave.response_invalid",
            False,
        ),
    ]
    for transport_response, code, retryable in cases:
        with pytest.raises(DiscoveryError) as captured:
            adapter(FakeTransport([transport_response])).discover(
                plan(), ledger(), country="US", language="en"
            )
        assert captured.value.code == code
        assert captured.value.retryable is retryable
        if code == "brave.http_429":
            assert captured.value.retry_after_seconds == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"count": 0},
        {"count": 21},
        {"max_pages_per_query": 11},
        {"timeout_seconds": 0},
        {"max_response_bytes": 100},
        {"cost_per_request_usd": Decimal("-0.01")},
    ],
)
def test_invalid_settings_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        settings(**changes)
