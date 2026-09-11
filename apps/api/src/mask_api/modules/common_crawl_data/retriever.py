"""Disabled-by-default targeted Common Crawl retrieval: CDX lookup, then
exactly one ranged WARC-record fetch. Never downloads a full WARC file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message

from mask_api.modules.common_crawl_data.cdx import build_cdx_request, parse_cdx_response
from mask_api.modules.common_crawl_data.contracts import CommonCrawlCapture, CommonCrawlProvenance
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.transport import CommonCrawlTransport
from mask_api.modules.common_crawl_data.warc import parse_warc_gzip_member
from mask_api.modules.evidence.contracts import FetchedResource, SourcePolicy
from mask_api.modules.evidence.policy import require_allowed_fetch_url
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger

_CDX_CONTENT_TYPES = {"text/x-ndjson", "application/json", "application/x-ndjson"}


@dataclass(frozen=True)
class CommonCrawlSettings:
    enabled: bool = False
    policy_approved: bool = False
    timeout_seconds: float = 20.0
    max_cdx_response_bytes: int = 200_000
    max_warc_record_bytes: int = 5_000_000
    cdx_lookup_limit: int = 5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("Common Crawl timeout must be in the interval (0, 120]")
        if self.max_cdx_response_bytes < 1024 or self.max_cdx_response_bytes > 2_000_000:
            raise ValueError("Common Crawl CDX response limit is outside the safe range")
        if self.max_warc_record_bytes < 1024 or self.max_warc_record_bytes > 20_000_000:
            raise ValueError("Common Crawl WARC record limit is outside the safe range")
        if self.cdx_lookup_limit < 1 or self.cdx_lookup_limit > 20:
            raise ValueError("Common Crawl CDX lookup limit must be 1-20")


class CommonCrawlRetriever:
    def __init__(
        self,
        settings: CommonCrawlSettings,
        transport: CommonCrawlTransport,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._now = now or (lambda: datetime.now(UTC))

    def find_capture(
        self,
        url: str,
        collection_id: str,
        policy: SourcePolicy,
        ledger: BudgetLedger,
    ) -> CommonCrawlCapture | None:
        """Look up the most recent archived capture of `url`, or None if never crawled."""
        self._require_enabled()
        require_allowed_fetch_url(url, policy)
        request = build_cdx_request(url, collection_id, limit=self._settings.cdx_lookup_limit)
        ledger.ensure_capacity(
            BudgetCharge(requests=1, total_bytes=self._settings.max_cdx_response_bytes)
        )
        response = self._transport.query_cdx(
            request,
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=self._settings.max_cdx_response_bytes,
        )
        ledger.consume(BudgetCharge(requests=1, total_bytes=len(response.body)))
        if response.status_code == 404:
            return None
        if response.status_code < 200 or response.status_code > 299:
            raise CommonCrawlError(f"common_crawl.cdx_http_{response.status_code}")
        if _bare_content_type(response.content_type) not in _CDX_CONTENT_TYPES:
            raise CommonCrawlError("common_crawl.cdx_content_type_invalid")
        captures = parse_cdx_response(response.body, collection_id)
        if not captures:
            return None
        return max(captures, key=lambda capture: capture.timestamp)

    def fetch_resource(
        self,
        capture: CommonCrawlCapture,
        policy: SourcePolicy,
        ledger: BudgetLedger,
    ) -> tuple[FetchedResource, CommonCrawlProvenance]:
        """Fetch and decode exactly the one WARC record this capture names."""
        self._require_enabled()
        max_bytes = min(self._settings.max_warc_record_bytes, policy.max_response_bytes)
        if capture.warc_length > max_bytes:
            raise CommonCrawlError("common_crawl.warc_record_too_large")
        ledger.ensure_capacity(BudgetCharge(requests=1, total_bytes=capture.warc_length))
        response = self._transport.fetch_warc_range(
            capture.warc_filename,
            capture.warc_offset,
            capture.warc_length,
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=max_bytes,
        )
        ledger.consume(BudgetCharge(requests=1, total_bytes=len(response.body)))
        if response.status_code != 206:
            raise CommonCrawlError(f"common_crawl.warc_fetch_status_{response.status_code}")
        if len(response.body) != capture.warc_length:
            raise CommonCrawlError("common_crawl.warc_range_incomplete", retryable=True)
        record = parse_warc_gzip_member(response.body)
        if record.http_status < 200 or record.http_status > 299:
            raise CommonCrawlError(f"common_crawl.archived_http_{record.http_status}")
        if _bare_content_type(record.http_content_type) not in policy.allowed_content_types:
            raise CommonCrawlError("common_crawl.content_type_denied")
        retrieved_at = self._timestamp()
        resource = FetchedResource(
            requested_url=capture.url,
            final_url=record.target_uri,
            status_code=record.http_status,
            content_type=record.http_content_type,
            body=record.body,
            fetched_at=retrieved_at,
        )
        provenance = CommonCrawlProvenance(
            collection_id=capture.collection_id,
            original_url=capture.url,
            capture_timestamp=capture.timestamp,
            warc_filename=capture.warc_filename,
            warc_offset=capture.warc_offset,
            warc_length=capture.warc_length,
            retrieved_at=retrieved_at,
        )
        return resource, provenance

    def _require_enabled(self) -> None:
        if not self._settings.enabled:
            raise CommonCrawlError("common_crawl.disabled")
        if not self._settings.policy_approved:
            raise CommonCrawlError("common_crawl.policy_not_approved")

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise CommonCrawlError("common_crawl.clock_not_timezone_aware")
        return value


def _bare_content_type(value: str) -> str:
    message = Message()
    message["content-type"] = value
    return message.get_content_type().lower()
