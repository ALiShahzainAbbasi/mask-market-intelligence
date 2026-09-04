import contextlib
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from mask_api.modules.evidence.contracts import FetchedResource, SourcePolicy
from mask_api.modules.evidence.errors import FetchFailure, SourcePolicyDenied
from mask_api.modules.evidence.policy import require_allowed_fetch_url


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    final_url: str
    content_type: str
    body: bytes
    etag: str | None = None
    last_modified: str | None = None


class HostResolver(Protocol):
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class HttpTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> TransportResponse: ...


class SystemHostResolver:
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise FetchFailure(
                "collection.dns_failed",
                "The source hostname could not be resolved.",
                retryable=True,
            ) from exc
        return tuple(sorted({str(record[4][0]) for record in records}))


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class UrllibHttpTransport:
    """Minimal GET transport with TLS verification, no cookies, proxy, or redirects."""

    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def get(
        self,
        url: str,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> TransportResponse:
        request = Request(
            url,
            headers={
                "Accept": (
                    "text/html, application/rss+xml, application/atom+xml, "
                    "application/xml, text/xml"
                ),
                "Accept-Encoding": "identity",
                "User-Agent": user_agent,
            },
            method="GET",
        )
        try:
            response = cast(Any, self._opener.open(request, timeout=timeout_seconds))
            with contextlib.closing(response):
                body = cast(bytes, response.read(max_bytes + 1))
                if len(body) > max_bytes:
                    raise FetchFailure(
                        "collection.response_too_large",
                        "The source response exceeded the approved byte limit.",
                    )
                return TransportResponse(
                    status_code=int(response.status),
                    final_url=str(response.geturl()),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=body,
                    etag=_bounded_header(response.headers.get("ETag")),
                    last_modified=_bounded_header(response.headers.get("Last-Modified")),
                )
        except HTTPError as exc:
            retry_after = _retry_after_seconds(exc.headers.get("Retry-After"))
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            code = (
                "collection.redirect_blocked" if 300 <= exc.code <= 399 else "collection.http_error"
            )
            raise FetchFailure(
                code,
                "The source returned a response that cannot be collected.",
                retryable=retryable,
                retry_after_seconds=retry_after,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise FetchFailure(
                "collection.network_error",
                "The source could not be reached within the approved request limits.",
                retryable=True,
            ) from exc


class SafeHttpFetcher:
    def __init__(self, resolver: HostResolver, transport: HttpTransport) -> None:
        self._resolver = resolver
        self._transport = transport

    def fetch(
        self, url: str, policy: SourcePolicy, fetched_at: datetime, max_bytes: int
    ) -> FetchedResource:
        require_allowed_fetch_url(url, policy)
        parts = urlsplit(url)
        hostname = parts.hostname
        if hostname is None:
            raise SourcePolicyDenied(
                "source_policy.url_malformed",
                "The requested URL is outside the approved source scope.",
            )
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = self._resolver.resolve(hostname, port)
        if not addresses or any(not _is_public_address(address) for address in addresses):
            raise SourcePolicyDenied(
                "source_policy.non_public_address",
                "The source hostname does not resolve exclusively to public addresses.",
            )
        byte_limit = min(max_bytes, policy.max_response_bytes)
        response = self._transport.get(
            url,
            user_agent=policy.user_agent,
            timeout_seconds=policy.request_timeout_seconds,
            max_bytes=byte_limit,
        )
        require_allowed_fetch_url(response.final_url, policy)
        if response.status_code < 200 or response.status_code > 299:
            raise FetchFailure(
                "collection.http_error",
                "The source returned a response that cannot be collected.",
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        if len(response.body) > byte_limit:
            raise FetchFailure(
                "collection.response_too_large",
                "The source response exceeded the approved byte limit.",
            )
        content_type = _bare_content_type(response.content_type)
        if content_type not in policy.allowed_content_types:
            raise FetchFailure(
                "collection.content_type_denied",
                "The source returned a content type outside the approved policy.",
            )
        return FetchedResource(
            requested_url=url,
            final_url=response.final_url,
            status_code=response.status_code,
            content_type=response.content_type,
            body=response.body,
            fetched_at=fetched_at,
            etag=response.etag,
            last_modified=response.last_modified,
        )


def _is_public_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _bare_content_type(value: str) -> str:
    message = Message()
    message["content-type"] = value
    return message.get_content_type().lower()


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return max(0.0, parsed)


def _bounded_header(value: str | None) -> str | None:
    return None if value is None else value[:500]
