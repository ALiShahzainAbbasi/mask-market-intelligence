"""Bounded fixed-origin transport for the O*NET database ZIP download."""

from __future__ import annotations

import contextlib
import ssl
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

_ALLOWED_HOST = "www.onetcenter.org"
_ALLOWED_PATH_PREFIX = "/dl_files/database/"


class OnetTransportError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__("O*NET database transport request could not be completed safely")


@dataclass(frozen=True)
class OnetHeadResult:
    status_code: int
    content_length: int | None
    content_type: str | None
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class OnetDownloadResult:
    status_code: int
    content_type: str
    body: bytes


class OnetTransport(Protocol):
    def head(self, url: str, *, timeout_seconds: float) -> OnetHeadResult: ...

    def download(
        self, url: str, *, timeout_seconds: float, max_bytes: int
    ) -> OnetDownloadResult: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class UrllibOnetTransport:
    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def head(self, url: str, *, timeout_seconds: float) -> OnetHeadResult:
        _validate_url(url)
        request = Request(url, method="HEAD", headers={"Accept-Encoding": "identity"})
        try:
            response = cast(Any, self._opener.open(request, timeout=timeout_seconds))
            with contextlib.closing(response):
                headers = response.headers
                return OnetHeadResult(
                    status_code=int(response.status),
                    content_length=_optional_int(headers.get("Content-Length")),
                    content_type=headers.get("Content-Type"),
                    etag=headers.get("ETag"),
                    last_modified=headers.get("Last-Modified"),
                )
        except HTTPError as error:
            return OnetHeadResult(error.code, None, None, None, None)
        except (TimeoutError, URLError, OSError) as error:
            raise OnetTransportError("onet.network_error", retryable=True) from error

    def download(self, url: str, *, timeout_seconds: float, max_bytes: int) -> OnetDownloadResult:
        _validate_url(url)
        request = Request(
            url, method="GET", headers={"Accept-Encoding": "identity", "Accept": "application/zip"}
        )
        try:
            response = cast(Any, self._opener.open(request, timeout=timeout_seconds))
            with contextlib.closing(response):
                content = _read_fully(response, max_bytes)
                return OnetDownloadResult(
                    status_code=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=content,
                )
        except HTTPError as error:
            raise OnetTransportError(
                f"onet.http_{error.code}", retryable=error.code == 429 or error.code >= 500
            ) from error
        except (TimeoutError, URLError, OSError, HTTPException) as error:
            raise OnetTransportError("onet.network_error", retryable=True) from error


def _read_fully(response: Any, max_bytes: int) -> bytes:
    """Read to EOF in chunks rather than trusting one `.read(n)` call.

    A single large `.read(n)` can return fewer bytes than requested well
    before EOF on a slow or unstable connection without raising -- observed
    against O*NET's ~16MB archive. Looping until an empty chunk (true EOF)
    is the only way to reliably detect and reject a short read instead of
    silently caching a truncated archive.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = cast(bytes, response.read(65_536))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise OnetTransportError("onet.response_too_large")
    return b"".join(chunks)


def _validate_url(url: str) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != _ALLOWED_HOST
        or not parts.path.startswith(_ALLOWED_PATH_PREFIX)
        or not parts.path.endswith(".zip")
    ):
        raise OnetTransportError("onet.endpoint_invalid")


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None
