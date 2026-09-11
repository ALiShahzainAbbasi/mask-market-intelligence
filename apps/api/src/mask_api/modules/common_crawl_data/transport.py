"""Bounded transport for the CDX index query and the ranged WARC-record fetch.

Two distinct, fixed, allowlisted origins: `index.commoncrawl.org` for the
CDX lookup (a small JSON query) and `data.commoncrawl.org` for the actual
record bytes, fetched with an HTTP `Range` header for exactly one WARC
record's offset/length -- never a full WARC file download.
"""

from __future__ import annotations

import contextlib
import ssl
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from mask_api.modules.common_crawl_data.cdx import CdxRequest
from mask_api.modules.common_crawl_data.errors import CommonCrawlError

_CDX_HOST = "index.commoncrawl.org"
_WARC_HOST = "data.commoncrawl.org"


@dataclass(frozen=True)
class CdxTransportResponse:
    status_code: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class WarcRangeTransportResponse:
    status_code: int
    body: bytes


class CommonCrawlTransport(Protocol):
    def query_cdx(
        self, request: CdxRequest, *, timeout_seconds: float, max_bytes: int
    ) -> CdxTransportResponse: ...

    def fetch_warc_range(
        self,
        warc_filename: str,
        offset: int,
        length: int,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> WarcRangeTransportResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class UrllibCommonCrawlTransport:
    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def query_cdx(
        self, request: CdxRequest, *, timeout_seconds: float, max_bytes: int
    ) -> CdxTransportResponse:
        parts = urlsplit(request.endpoint)
        if parts.scheme != "https" or parts.hostname != _CDX_HOST:
            raise CommonCrawlError("common_crawl.cdx_endpoint_invalid")
        url = f"{request.endpoint}?{urlencode(request.query)}"
        web_request = Request(
            url,
            method="GET",
            headers={"Accept": "text/x-ndjson, application/json", "Accept-Encoding": "identity"},
        )
        try:
            response = cast(Any, self._opener.open(web_request, timeout=timeout_seconds))
            with contextlib.closing(response):
                body = _read_fully(response, max_bytes)
                return CdxTransportResponse(
                    status_code=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=body,
                )
        except HTTPError as error:
            body = error.read(max_bytes + 1) if error.fp is not None else b""
            return CdxTransportResponse(
                error.code, str(error.headers.get("Content-Type", "")), body[:max_bytes]
            )
        except (TimeoutError, URLError, OSError, HTTPException) as error:
            raise CommonCrawlError("common_crawl.network_error", retryable=True) from error

    def fetch_warc_range(
        self,
        warc_filename: str,
        offset: int,
        length: int,
        *,
        timeout_seconds: float,
        max_bytes: int,
    ) -> WarcRangeTransportResponse:
        if offset < 0 or length <= 0 or length > max_bytes:
            raise CommonCrawlError("common_crawl.warc_range_invalid")
        if "\\" in warc_filename or ".." in warc_filename or warc_filename.startswith("/"):
            raise CommonCrawlError("common_crawl.warc_filename_invalid")
        url = f"https://{_WARC_HOST}/{warc_filename}"
        end = offset + length - 1
        web_request = Request(
            url,
            method="GET",
            headers={
                "Range": f"bytes={offset}-{end}",
                "Accept-Encoding": "identity",
            },
        )
        try:
            response = cast(Any, self._opener.open(web_request, timeout=timeout_seconds))
            with contextlib.closing(response):
                body = _read_fully(response, max_bytes)
                return WarcRangeTransportResponse(status_code=int(response.status), body=body)
        except HTTPError as error:
            raise CommonCrawlError(
                f"common_crawl.warc_http_{error.code}",
                retryable=error.code == 429 or error.code >= 500,
            ) from error
        except (TimeoutError, URLError, OSError, HTTPException) as error:
            raise CommonCrawlError("common_crawl.network_error", retryable=True) from error


def _read_fully(response: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = cast(bytes, response.read(65_536))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise CommonCrawlError("common_crawl.response_too_large")
    return b"".join(chunks)
