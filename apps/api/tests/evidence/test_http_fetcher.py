from datetime import UTC, datetime

import pytest
from mask_api.modules.evidence.errors import FetchFailure, SourcePolicyDenied
from mask_api.modules.evidence.http_fetcher import SafeHttpFetcher, TransportResponse


class Resolver:
    def __init__(self, addresses=("93.184.216.34",)) -> None:
        self.addresses = addresses
        self.calls = []

    def resolve(self, hostname: str, port: int):
        self.calls.append((hostname, port))
        return self.addresses


class Transport:
    def __init__(self, response: TransportResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def response(**updates) -> TransportResponse:
    values = {
        "status_code": 200,
        "final_url": "https://research.example.test/feeds/rss",
        "content_type": "application/rss+xml; charset=utf-8",
        "body": b"<rss />",
        "etag": '"fixture"',
    }
    values.update(updates)
    return TransportResponse(**values)


def test_safe_fetcher_applies_dns_mime_size_and_request_controls(source_policy) -> None:
    resolver = Resolver()
    transport = Transport(response())
    fetched_at = datetime(2026, 9, 4, tzinfo=UTC)
    result = SafeHttpFetcher(resolver, transport).fetch(
        "https://research.example.test/feeds/rss", source_policy, fetched_at, 4096
    )

    assert result.body == b"<rss />"
    assert result.etag == '"fixture"'
    assert resolver.calls == [("research.example.test", 443)]
    _, options = transport.calls[0]
    assert options["user_agent"] == source_policy.user_agent
    assert options["timeout_seconds"] == source_policy.request_timeout_seconds
    assert options["max_bytes"] == 4096


@pytest.mark.parametrize(
    "addresses",
    [
        (),
        ("127.0.0.1",),
        ("10.0.0.2",),
        ("169.254.169.254",),
        ("::1",),
        ("93.184.216.34", "10.0.0.2"),
    ],
)
def test_safe_fetcher_blocks_non_public_or_mixed_dns_results(source_policy, addresses) -> None:
    transport = Transport(response())
    with pytest.raises(SourcePolicyDenied) as failure:
        SafeHttpFetcher(Resolver(addresses), transport).fetch(
            "https://research.example.test/feeds/rss",
            source_policy,
            datetime(2026, 9, 4, tzinfo=UTC),
            4096,
        )
    assert failure.value.code == "source_policy.non_public_address"
    assert transport.calls == []


def test_safe_fetcher_blocks_redirected_origin_mime_and_oversize(source_policy) -> None:
    cases = (
        (
            response(final_url="https://other.example.test/feeds/rss"),
            SourcePolicyDenied,
        ),
        (response(content_type="application/octet-stream"), FetchFailure),
        (response(body=b"x" * 4097), FetchFailure),
        (response(status_code=503), FetchFailure),
    )
    for transport_response, error in cases:
        with pytest.raises(error):
            SafeHttpFetcher(Resolver(), Transport(transport_response)).fetch(
                "https://research.example.test/feeds/rss",
                source_policy,
                datetime(2026, 9, 4, tzinfo=UTC),
                4096,
            )
