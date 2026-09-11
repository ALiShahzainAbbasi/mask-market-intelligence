"""Build a CDX index query and parse its newline-delimited JSON response.

Verified against a real query to `index.commoncrawl.org`: a match returns
`Content-Type: text/x-ndjson` with one JSON object per line (`urlkey`,
`timestamp`, `url`, `mime`, `status`, `digest`, `length`, `offset`,
`filename`, ...); no match returns HTTP 404 with a JSON `{"message": ...}`
body, handled as a normal empty result by the caller, not an error.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from mask_api.modules.common_crawl_data.contracts import CommonCrawlCapture
from mask_api.modules.common_crawl_data.errors import CommonCrawlError

_CDX_BASE = "https://index.commoncrawl.org"
_MAX_URL_LENGTH = 2048


@dataclass(frozen=True)
class CdxRequest:
    collection_id: str
    endpoint: str
    query: dict[str, str] = field(default_factory=dict)


def build_cdx_request(url: str, collection_id: str, *, limit: int = 5) -> CdxRequest:
    if not re.fullmatch(r"CC-MAIN-[0-9]{4}-[0-9]{2}", collection_id):
        raise ValueError("Common Crawl collection ID is invalid")
    stripped = url.strip()
    if not stripped or len(stripped) > _MAX_URL_LENGTH:
        raise ValueError("Common Crawl lookup URL must be 1-2048 characters")
    if not re.match(r"^https?://", stripped):
        raise ValueError("Common Crawl lookup URL must be absolute http(s)")
    if limit < 1 or limit > 100:
        raise ValueError("Common Crawl CDX limit must be 1-100")
    return CdxRequest(
        collection_id=collection_id,
        endpoint=f"{_CDX_BASE}/{collection_id}-index",
        query={
            "url": stripped,
            "output": "json",
            "matchType": "exact",
            "limit": str(limit),
        },
    )


def parse_cdx_response(body: bytes, collection_id: str) -> tuple[CommonCrawlCapture, ...]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CommonCrawlError("common_crawl.cdx_response_invalid") from error
    captures: list[CommonCrawlCapture] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise CommonCrawlError("common_crawl.cdx_response_invalid") from error
        if not isinstance(row, dict):
            raise CommonCrawlError("common_crawl.cdx_response_invalid")
        captures.append(_capture(row, collection_id))
    return tuple(captures)


def _capture(row: dict[str, object], collection_id: str) -> CommonCrawlCapture:
    try:
        return CommonCrawlCapture(
            collection_id=collection_id,
            url=_require_str(row, "url"),
            timestamp=_require_str(row, "timestamp"),
            status=_optional_int(row.get("status")),
            mime=_optional_str(row.get("mime")),
            warc_filename=_require_str(row, "filename"),
            warc_offset=_require_int(row, "offset"),
            warc_length=_require_int(row, "length"),
        )
    except (ValueError, TypeError) as error:
        raise CommonCrawlError("common_crawl.cdx_row_invalid") from error


def _require_str(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise CommonCrawlError("common_crawl.cdx_row_invalid")
    return value


def _require_int(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, str) or not value.isdigit():
        raise CommonCrawlError("common_crawl.cdx_row_invalid")
    return int(value)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
