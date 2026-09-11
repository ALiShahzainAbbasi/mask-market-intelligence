from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from mask_api.modules.common_crawl_data.cdx import CdxRequest
from mask_api.modules.common_crawl_data.contracts import CommonCrawlCapture
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.retriever import CommonCrawlRetriever, CommonCrawlSettings
from mask_api.modules.common_crawl_data.transport import (
    CdxTransportResponse,
    WarcRangeTransportResponse,
)
from mask_api.modules.evidence.contracts import SourcePolicy
from mask_api.modules.evidence.errors import SourcePolicyDenied
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits

COLLECTION = "CC-MAIN-2026-34"
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
URL = "https://research.example.test/articles/example"


@dataclass
class FakeTransport:
    cdx_response: CdxTransportResponse | None = None
    warc_response: WarcRangeTransportResponse | None = None
    cdx_calls: list[CdxRequest] = field(default_factory=list)
    warc_calls: list[tuple[str, int, int]] = field(default_factory=list)

    def query_cdx(
        self, request: CdxRequest, *, timeout_seconds: float, max_bytes: int
    ) -> CdxTransportResponse:
        self.cdx_calls.append(request)
        assert self.cdx_response is not None
        return self.cdx_response

    def fetch_warc_range(
        self,
        warc_filename: str,
        offset: int,
        length: int,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> WarcRangeTransportResponse:
        self.warc_calls.append((warc_filename, offset, length))
        assert self.warc_response is not None
        return self.warc_response


def settings(**changes: object) -> CommonCrawlSettings:
    values: dict[str, object] = {"enabled": True, "policy_approved": True}
    values.update(changes)
    return CommonCrawlSettings(**values)  # type: ignore[arg-type]


def ledger() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=5,
            max_documents=5,
            max_total_bytes=5_000_000,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0"),
        )
    )


def cdx_success(*rows: dict[str, object]) -> CdxTransportResponse:
    body = "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")
    return CdxTransportResponse(status_code=200, content_type="text/x-ndjson", body=body)


def cdx_row(timestamp: str = "20260115100000", **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "url": URL,
        "timestamp": timestamp,
        "filename": "crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00001.warc.gz",
        "offset": "1000",
        "length": "500",
        "status": "200",
        "mime": "text/html",
    }
    values.update(changes)
    return values


def capture(**changes: object) -> CommonCrawlCapture:
    values: dict[str, object] = {
        "collection_id": COLLECTION,
        "url": URL,
        "timestamp": "20260115100000",
        "status": 200,
        "mime": "text/html",
        "warc_filename": "crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00001.warc.gz",
        "warc_offset": 1000,
        "warc_length": 500,
    }
    values.update(changes)
    return CommonCrawlCapture(**values)  # type: ignore[arg-type]


def retriever(
    transport: FakeTransport, configured: CommonCrawlSettings | None = None
) -> CommonCrawlRetriever:
    return CommonCrawlRetriever(configured or settings(), transport, now=lambda: NOW)


def test_find_capture_returns_none_when_cdx_reports_404(source_policy: SourcePolicy) -> None:
    transport = FakeTransport(cdx_response=CdxTransportResponse(404, "application/json", b"{}"))
    budget = ledger()

    result = retriever(transport).find_capture(URL, COLLECTION, source_policy, budget)

    assert result is None
    assert budget.usage.requests == 1


def test_find_capture_returns_none_when_no_captures_in_body(source_policy: SourcePolicy) -> None:
    transport = FakeTransport(cdx_response=cdx_success())

    result = retriever(transport).find_capture(URL, COLLECTION, source_policy, ledger())

    assert result is None


def test_find_capture_picks_the_most_recent_timestamp(source_policy: SourcePolicy) -> None:
    transport = FakeTransport(
        cdx_response=cdx_success(
            cdx_row(timestamp="20260101000000"),
            cdx_row(timestamp="20260601000000"),
            cdx_row(timestamp="20260315000000"),
        )
    )

    result = retriever(transport).find_capture(URL, COLLECTION, source_policy, ledger())

    assert result is not None
    assert result.timestamp == "20260601000000"


def test_find_capture_rejects_a_url_outside_the_source_policy_scope(
    source_policy: SourcePolicy,
) -> None:
    transport = FakeTransport(cdx_response=cdx_success())

    with pytest.raises(SourcePolicyDenied):
        retriever(transport).find_capture(
            "https://not-the-approved-origin.test/x", COLLECTION, source_policy, ledger()
        )

    assert transport.cdx_calls == []


def test_find_capture_requires_enabled_and_policy_approval(source_policy: SourcePolicy) -> None:
    transport = FakeTransport()

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport, settings(enabled=False)).find_capture(
            URL, COLLECTION, source_policy, ledger()
        )

    assert captured.value.code == "common_crawl.disabled"
    assert transport.cdx_calls == []


def test_fetch_resource_returns_a_fetched_resource_and_provenance(
    source_policy: SourcePolicy, warc_gzip_member: Callable[..., bytes]
) -> None:
    warc_bytes = warc_gzip_member()
    transport = FakeTransport(
        warc_response=WarcRangeTransportResponse(status_code=206, body=warc_bytes)
    )
    a_capture = capture(warc_length=len(warc_bytes))
    budget = ledger()

    resource, provenance = retriever(transport).fetch_resource(a_capture, source_policy, budget)

    assert resource.requested_url == URL
    assert resource.final_url == "https://research.example.test/articles/example"
    assert resource.status_code == 200
    assert resource.content_type == "text/html"
    assert b"dispatch" in resource.body
    assert provenance.collection_id == COLLECTION
    assert provenance.warc_filename == a_capture.warc_filename
    assert provenance.retrieved_at == NOW
    assert budget.usage.requests == 1


def test_fetch_resource_rejects_a_short_range_response(
    source_policy: SourcePolicy, warc_gzip_member: Callable[..., bytes]
) -> None:
    warc_bytes = warc_gzip_member()
    transport = FakeTransport(
        warc_response=WarcRangeTransportResponse(status_code=206, body=warc_bytes[:-1])
    )
    a_capture = capture(warc_length=len(warc_bytes))

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport).fetch_resource(a_capture, source_policy, ledger())

    assert captured.value.code == "common_crawl.warc_range_incomplete"
    assert captured.value.retryable is True


def test_fetch_resource_rejects_a_non_206_response(
    source_policy: SourcePolicy, warc_gzip_member: Callable[..., bytes]
) -> None:
    warc_bytes = warc_gzip_member()
    transport = FakeTransport(warc_response=WarcRangeTransportResponse(200, warc_bytes))
    a_capture = capture(warc_length=len(warc_bytes))

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport).fetch_resource(a_capture, source_policy, ledger())

    assert captured.value.code == "common_crawl.warc_fetch_status_200"


def test_fetch_resource_rejects_a_disallowed_archived_content_type(
    source_policy: SourcePolicy, warc_gzip_member: Callable[..., bytes]
) -> None:
    warc_bytes = warc_gzip_member(content_type="application/pdf")
    transport = FakeTransport(
        warc_response=WarcRangeTransportResponse(status_code=206, body=warc_bytes)
    )
    a_capture = capture(warc_length=len(warc_bytes))

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport).fetch_resource(a_capture, source_policy, ledger())

    assert captured.value.code == "common_crawl.content_type_denied"


def test_fetch_resource_rejects_an_archived_non_2xx_status(
    source_policy: SourcePolicy, warc_gzip_member: Callable[..., bytes]
) -> None:
    warc_bytes = warc_gzip_member(http_status=404)
    transport = FakeTransport(
        warc_response=WarcRangeTransportResponse(status_code=206, body=warc_bytes)
    )
    a_capture = capture(warc_length=len(warc_bytes))

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport).fetch_resource(a_capture, source_policy, ledger())

    assert captured.value.code == "common_crawl.archived_http_404"


def test_fetch_resource_rejects_a_record_larger_than_the_configured_cap(
    source_policy: SourcePolicy,
) -> None:
    transport = FakeTransport()
    a_capture = capture(warc_length=10_000_000)

    with pytest.raises(CommonCrawlError) as captured:
        retriever(transport, settings(max_warc_record_bytes=2_000)).fetch_resource(
            a_capture, source_policy, ledger()
        )

    assert captured.value.code == "common_crawl.warc_record_too_large"
    assert transport.warc_calls == []
