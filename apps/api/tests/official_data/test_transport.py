from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.official_data.contracts import OfficialSourceId
from mask_api.modules.official_data.requests import OfficialRequest, census_cbp_request
from mask_api.modules.official_data.transport import (
    OfficialApiAdapter,
    OfficialApiSettings,
    OfficialTransportError,
    OfficialTransportResponse,
    UrllibOfficialTransport,
)
from mask_api.research_runner.budgets import BudgetLedger, BudgetLimitExceeded, RunBudgetLimits
from mask_api.research_runner.configuration import load_source_profile
from mask_api.research_runner.contracts import SourceConfiguration
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
KEY = SecretStr("fixture-not-a-real-key")


@dataclass
class FakeTransport:
    responses: list[OfficialTransportResponse]
    calls: list[dict[str, object]] = field(default_factory=list)

    def execute(self, request: OfficialRequest, **kwargs: object) -> OfficialTransportResponse:
        self.calls.append({"request": request, **kwargs})
        return self.responses.pop(0)


class FakeHttpResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def read(self, _limit: int) -> bytes:
        return (FIXTURES / "census_cbp.json").read_bytes()

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


def source(source_id: str) -> SourceConfiguration:
    configured = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value.sources[
        source_id
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


def request() -> OfficialRequest:
    return census_cbp_request(
        year=2022,
        naics=238220,
        employment_size="242",
        geography="us:*",
        api_key=KEY,
    )


def response(
    *, status: int = 200, content_type: str = "application/json"
) -> OfficialTransportResponse:
    return OfficialTransportResponse(
        status_code=status,
        content_type=content_type,
        body=(FIXTURES / "census_cbp.json").read_bytes(),
    )


def settings(**changes: object) -> OfficialApiSettings:
    values: dict[str, object] = {
        "enabled": True,
        "policy_approved": True,
        "timeout_seconds": 5,
        "max_response_bytes": 1_000_000,
    }
    values.update(changes)
    return OfficialApiSettings(**values)  # type: ignore[arg-type]


def adapter(
    transport: FakeTransport,
    configured: OfficialApiSettings | None = None,
) -> OfficialApiAdapter:
    return OfficialApiAdapter(
        "census_cbp",
        source("census_cbp"),
        configured or settings(),
        transport,
        user_agent="MASK-AI-Market-Research/0.1",
        now=lambda: NOW,
    )


def test_fetch_preserves_request_and_raw_response_provenance() -> None:
    transport = FakeTransport([response()])
    ledger = budget()

    result = adapter(transport).fetch(request(), ledger)

    assert result.retrieved_at == NOW
    assert result.request.endpoint == "https://api.census.gov/data/2022/cbp"
    assert result.request.credential_fields == ("key",)
    assert "fixture-not-a-real-key" not in result.request.model_dump_json()
    assert result.batch.raw_response == (FIXTURES / "census_cbp.json").read_bytes()
    assert result.batch.observations[0].metric == "establishment_count"
    assert ledger.usage.requests == 1
    assert ledger.usage.total_bytes == len(result.batch.raw_response)


def test_standard_transport_validates_endpoint_and_applies_bounded_request() -> None:
    opener = FakeOpener()
    transport = UrllibOfficialTransport()
    transport._opener = opener  # type: ignore[assignment]

    result = transport.execute(
        request(),
        user_agent="MASK-AI-Market-Research/0.1",
        timeout_seconds=5,
        max_bytes=1_000_000,
    )

    assert result.status_code == 200
    assert opener.timeout == 5
    sent = opener.request
    assert sent is not None
    assert sent.full_url.startswith("https://api.census.gov/data/2022/cbp?")  # type: ignore[attr-defined]
    headers = {key.casefold(): value for key, value in sent.header_items()}  # type: ignore[attr-defined]
    assert headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    ("configured", "code"),
    [
        (settings(enabled=False), "official.disabled"),
        (settings(policy_approved=False), "official.policy_not_approved"),
    ],
)
def test_disabled_or_unapproved_source_fails_before_network(
    configured: OfficialApiSettings, code: str
) -> None:
    transport = FakeTransport([])

    with pytest.raises(OfficialTransportError) as captured:
        adapter(transport, configured).fetch(request(), budget())

    assert captured.value.code == code
    assert transport.calls == []


def test_required_credential_and_source_profile_are_checked_before_network() -> None:
    transport = FakeTransport([])
    missing = OfficialRequest(
        source_id=OfficialSourceId.CENSUS_CBP,
        method="GET",
        endpoint="https://api.census.gov/data/2022/cbp",
    )

    with pytest.raises(OfficialTransportError) as captured:
        adapter(transport).fetch(missing, budget())
    assert captured.value.code == "official.credential_missing"

    mismatched = OfficialApiAdapter(
        "bls",
        source("bls"),
        settings(),
        transport,
        user_agent="MASK-AI-Market-Research/0.1",
    )
    with pytest.raises(OfficialTransportError) as captured:
        mismatched.fetch(request(), budget())
    assert captured.value.code == "official.source_profile_invalid"
    assert transport.calls == []


def test_credential_pending_source_is_held_before_network() -> None:
    configured = (
        load_source_profile(ROOT / "configs/sources/default_us_public.yaml")
        .value.sources["census_cbp"]
        .model_copy(update={"operational_status": "credential_pending"})
    )
    transport = FakeTransport([])
    held = OfficialApiAdapter(
        "census_cbp",
        configured,
        settings(),
        transport,
        user_agent="MASK-AI-Market-Research/0.1",
    )

    with pytest.raises(OfficialTransportError) as captured:
        held.fetch(request(), budget())

    assert captured.value.code == "official.operational_hold"
    assert transport.calls == []


def test_maximum_response_reservation_prevents_network_call() -> None:
    transport = FakeTransport([])

    with pytest.raises(BudgetLimitExceeded):
        adapter(transport).fetch(request(), budget(total_bytes=999_999))

    assert transport.calls == []


def test_http_failures_count_the_request_and_preserve_retry_metadata() -> None:
    transport = FakeTransport(
        [OfficialTransportResponse(429, "application/json", b"", retry_after_seconds=3)]
    )
    ledger = budget()

    with pytest.raises(OfficialTransportError) as captured:
        adapter(transport).fetch(request(), ledger)

    assert captured.value.code == "official.http_429"
    assert captured.value.retryable is True
    assert captured.value.retry_after_seconds == 3
    assert ledger.usage.requests == 1


def test_invalid_content_type_fails_without_parsing_response() -> None:
    ledger = budget()

    with pytest.raises(OfficialTransportError) as captured:
        adapter(FakeTransport([response(content_type="text/html")])).fetch(request(), ledger)

    assert captured.value.code == "official.content_type_invalid"
    assert ledger.usage.requests == 1
    assert ledger.usage.total_bytes > 0


def test_sec_requires_contact_identity_in_user_agent() -> None:
    transport = FakeTransport([])
    sec_request = OfficialRequest(
        source_id=OfficialSourceId.SEC_EDGAR,
        method="GET",
        endpoint="https://data.sec.gov/submissions/CIK0000320193.json",
    )
    sec_adapter = OfficialApiAdapter(
        "sec_edgar",
        source("sec_edgar"),
        settings(),
        transport,
        user_agent="MASK-AI-Market-Research/0.1",
    )

    with pytest.raises(OfficialTransportError) as captured:
        sec_adapter.fetch(sec_request, budget())

    assert captured.value.code == "sec.contact_user_agent_required"
    assert transport.calls == []


def test_invalid_origin_is_rejected_by_standard_transport() -> None:
    transport = UrllibOfficialTransport()
    invalid = OfficialRequest(
        source_id=OfficialSourceId.CENSUS_CBP,
        method="GET",
        endpoint="https://example.com/data/2022/cbp",
        secret_query={"key": KEY},
    )

    with pytest.raises(OfficialTransportError) as captured:
        transport.execute(
            invalid,
            user_agent="MASK-AI-Market-Research/0.1",
            timeout_seconds=5,
            max_bytes=10_000,
        )

    assert captured.value.code == "official.endpoint_invalid"
