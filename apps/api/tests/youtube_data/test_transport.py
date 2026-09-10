from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.youtube_data.quota import (
    YouTubeQuotaExceeded,
    YouTubeQuotaLedger,
    YouTubeQuotaLimits,
)
from mask_api.modules.youtube_data.requests import YouTubeRequest, youtube_search_request
from mask_api.modules.youtube_data.transport import (
    UrllibYouTubeTransport,
    YouTubeApiAdapter,
    YouTubeApiSettings,
    YouTubeQuotaExceededTransportError,
    YouTubeTransportError,
    YouTubeTransportResponse,
)
from mask_api.research_runner.budgets import BudgetLedger, BudgetLimitExceeded, RunBudgetLimits
from mask_api.research_runner.configuration import load_source_profile
from mask_api.research_runner.contracts import SourceConfiguration
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
KEY = SecretStr("fixture-not-a-real-key")


@dataclass
class FakeTransport:
    responses: list[YouTubeTransportResponse]
    calls: list[dict[str, object]] = field(default_factory=list)

    def execute(self, request: YouTubeRequest, **kwargs: object) -> YouTubeTransportResponse:
        self.calls.append({"request": request, **kwargs})
        return self.responses.pop(0)


class FakeHttpResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def read(self, _limit: int) -> bytes:
        return (FIXTURES / "search.json").read_bytes()

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


def source() -> SourceConfiguration:
    configured = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value.sources[
        "youtube"
    ]
    return configured.model_copy(update={"operational_status": "available"})


def budget(*, requests: int = 2, total_bytes: int = 2_000_000) -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=requests,
            max_documents=10,
            max_total_bytes=total_bytes,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0"),
        )
    )


def quota(*, max_quota_units: int = 10_000) -> YouTubeQuotaLedger:
    return YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=max_quota_units))


def request() -> YouTubeRequest:
    return youtube_search_request(query="HVAC dispatch pain", api_key=KEY)


def response(
    *, status: int = 200, content_type: str = "application/json", body: bytes | None = None
) -> YouTubeTransportResponse:
    return YouTubeTransportResponse(
        status_code=status,
        content_type=content_type,
        body=body if body is not None else (FIXTURES / "search.json").read_bytes(),
    )


def settings(**changes: object) -> YouTubeApiSettings:
    values: dict[str, object] = {
        "enabled": True,
        "policy_approved": True,
        "timeout_seconds": 5,
        "max_response_bytes": 1_000_000,
    }
    values.update(changes)
    return YouTubeApiSettings(**values)  # type: ignore[arg-type]


def adapter(
    transport: FakeTransport,
    configured: YouTubeApiSettings | None = None,
    profile: SourceConfiguration | None = None,
) -> YouTubeApiAdapter:
    return YouTubeApiAdapter(
        profile or source(),
        configured or settings(),
        transport,
        user_agent="MASK-AI-Market-Research/0.1",
        now=lambda: NOW,
    )


def test_fetch_preserves_request_and_raw_response_provenance_and_quota_cost() -> None:
    transport = FakeTransport([response()])
    ledger = budget()
    quota_ledger = quota()

    result = adapter(transport).fetch(request(), ledger, quota_ledger)

    assert result.retrieved_at == NOW
    assert result.request.endpoint.value == "search"
    assert result.request.credential_fields == ("key",)
    assert "fixture-not-a-real-key" not in result.request.model_dump_json()
    assert result.quota_cost == 100
    assert result.batch.raw_response == (FIXTURES / "search.json").read_bytes()
    assert result.batch.videos[0].video_id == "dQw4w9WgXcQ"
    assert ledger.usage.requests == 1
    assert quota_ledger.units_used == 100


def test_standard_transport_validates_endpoint_and_applies_bounded_request() -> None:
    opener = FakeOpener()
    transport = UrllibYouTubeTransport()
    transport._opener = opener  # type: ignore[assignment]

    result = transport.execute(
        request(), user_agent="MASK-AI-Market-Research/0.1", timeout_seconds=5, max_bytes=1_000_000
    )

    assert result.status_code == 200
    assert opener.timeout == 5
    sent = opener.request
    assert sent is not None
    assert sent.full_url.startswith(  # type: ignore[attr-defined]
        "https://www.googleapis.com/youtube/v3/search?"
    )
    headers = {key.casefold(): value for key, value in sent.header_items()}  # type: ignore[attr-defined]
    assert headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    ("configured", "code"),
    [
        (settings(enabled=False), "youtube.disabled"),
        (settings(policy_approved=False), "youtube.policy_not_approved"),
    ],
)
def test_disabled_or_unapproved_source_fails_before_network(
    configured: YouTubeApiSettings, code: str
) -> None:
    transport = FakeTransport([])

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(transport, configured).fetch(request(), budget(), quota())

    assert captured.value.code == code
    assert transport.calls == []


def test_required_credential_is_checked_before_network() -> None:
    transport = FakeTransport([])
    missing = YouTubeRequest(
        endpoint_id=request().endpoint_id,
        url=request().url,
        query=dict(request().query),
    )

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(transport).fetch(missing, budget(), quota())

    assert captured.value.code == "youtube.credential_missing"
    assert transport.calls == []


def test_credential_pending_source_is_held_before_network() -> None:
    configured = (
        load_source_profile(ROOT / "configs/sources/default_us_public.yaml")
        .value.sources["youtube"]
        .model_copy(update={"operational_status": "credential_pending"})
    )
    transport = FakeTransport([])

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(transport, profile=configured).fetch(request(), budget(), quota())

    assert captured.value.code == "youtube.operational_hold"
    assert transport.calls == []


def test_maximum_response_reservation_prevents_network_call() -> None:
    transport = FakeTransport([])

    with pytest.raises(BudgetLimitExceeded):
        adapter(transport).fetch(request(), budget(total_bytes=999_999), quota())

    assert transport.calls == []


def test_quota_exhaustion_prevents_network_call() -> None:
    transport = FakeTransport([])

    with pytest.raises(YouTubeQuotaExceeded):
        adapter(transport).fetch(request(), budget(), quota(max_quota_units=50))

    assert transport.calls == []


def test_provider_quota_exceeded_response_raises_the_distinct_error_type() -> None:
    transport = FakeTransport(
        [response(status=403, body=(FIXTURES / "quota_exceeded.json").read_bytes())]
    )
    ledger = budget()
    quota_ledger = quota()

    with pytest.raises(YouTubeQuotaExceededTransportError) as captured:
        adapter(transport).fetch(request(), ledger, quota_ledger)

    assert captured.value.code == "youtube.quota_exceeded_by_provider"
    assert ledger.usage.requests == 1
    assert quota_ledger.units_used == 100


def test_generic_forbidden_response_without_quota_reason_is_a_plain_http_error() -> None:
    transport = FakeTransport([response(status=403, body=b'{"error": {"errors": []}}')])

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(transport).fetch(request(), budget(), quota())

    assert captured.value.code == "youtube.http_403"
    assert not isinstance(captured.value, YouTubeQuotaExceededTransportError)


def test_http_failures_count_the_request_and_preserve_retry_metadata() -> None:
    transport = FakeTransport(
        [YouTubeTransportResponse(429, "application/json", b"", retry_after_seconds=3)]
    )
    ledger = budget()

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(transport).fetch(request(), ledger, quota())

    assert captured.value.code == "youtube.http_429"
    assert captured.value.retryable is True
    assert captured.value.retry_after_seconds == 3
    assert ledger.usage.requests == 1


def test_invalid_content_type_fails_without_parsing_response() -> None:
    ledger = budget()

    with pytest.raises(YouTubeTransportError) as captured:
        adapter(FakeTransport([response(content_type="text/html")])).fetch(
            request(), ledger, quota()
        )

    assert captured.value.code == "youtube.content_type_invalid"
    assert ledger.usage.requests == 1
    assert ledger.usage.total_bytes > 0


def test_invalid_origin_is_rejected_by_standard_transport() -> None:
    transport = UrllibYouTubeTransport()
    invalid = YouTubeRequest(
        endpoint_id=request().endpoint_id,
        url="https://example.com/youtube/v3/search",
        query=dict(request().query),
        secret_query={"key": KEY},
    )

    with pytest.raises(YouTubeTransportError) as captured:
        transport.execute(
            invalid, user_agent="MASK-AI-Market-Research/0.1", timeout_seconds=5, max_bytes=10_000
        )

    assert captured.value.code == "youtube.endpoint_invalid"
