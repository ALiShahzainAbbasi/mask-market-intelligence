"""Bounded fixed-origin transport and parser composition for the YouTube Data API."""

from __future__ import annotations

import contextlib
import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from mask_api.modules.youtube_data.contracts import YouTubeEndpoint, YouTubeFetchResult
from mask_api.modules.youtube_data.parsers import (
    parse_youtube_comment_threads,
    parse_youtube_search,
)
from mask_api.modules.youtube_data.quota import YouTubeQuotaLedger
from mask_api.modules.youtube_data.requests import YouTubeRequest
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger
from mask_api.research_runner.contracts import SourceAccess, SourceConfiguration

_ALLOWED_HOST = "www.googleapis.com"
_ALLOWED_PATHS = {
    YouTubeEndpoint.SEARCH: "/youtube/v3/search",
    YouTubeEndpoint.COMMENT_THREADS: "/youtube/v3/commentThreads",
}


class YouTubeTransportError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__("YouTube Data API request could not be completed safely")


class YouTubeQuotaExceededTransportError(YouTubeTransportError):
    """The provider itself reported quota exhaustion (HTTP 403, reason quotaExceeded).

    Distinct from the generic HTTP error path so callers can record
    SOURCE_UNAVAILABLE_QUOTA and continue the run with other providers
    instead of treating this as a hard failure.
    """

    def __init__(self) -> None:
        super().__init__("youtube.quota_exceeded_by_provider", retryable=False)


@dataclass(frozen=True)
class YouTubeTransportResponse:
    status_code: int
    content_type: str
    body: bytes
    retry_after_seconds: float | None = None


@dataclass(frozen=True)
class YouTubeApiSettings:
    enabled: bool = False
    policy_approved: bool = False
    timeout_seconds: float = 10
    max_response_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("YouTube timeout must be in the interval (0, 60]")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 10_000_000:
            raise ValueError("YouTube response byte limit is outside the safe range")


class YouTubeTransport(Protocol):
    def execute(
        self,
        request: YouTubeRequest,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> YouTubeTransportResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class UrllibYouTubeTransport:
    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def execute(
        self,
        request: YouTubeRequest,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> YouTubeTransportResponse:
        _validate_endpoint(request)
        query = dict(request.query)
        query.update(
            {name: value.get_secret_value() for name, value in request.secret_query.items()}
        )
        url = f"{request.url}?{urlencode(query)}"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": user_agent,
        }
        web_request = Request(url, headers=headers, method="GET")
        try:
            response = cast(Any, self._opener.open(web_request, timeout=timeout_seconds))
            with contextlib.closing(response):
                content = cast(bytes, response.read(max_bytes + 1))
                if len(content) > max_bytes:
                    raise YouTubeTransportError("youtube.response_too_large")
                return YouTubeTransportResponse(
                    status_code=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=content,
                )
        except HTTPError as error:
            with contextlib.closing(error):
                body = error.read(max_bytes + 1)
            return YouTubeTransportResponse(
                error.code,
                str(error.headers.get("Content-Type", "")),
                body[:max_bytes],
                _retry_after(error.headers.get("Retry-After")),
            )
        except (TimeoutError, URLError, OSError) as error:
            raise YouTubeTransportError("youtube.network_error", retryable=True) from error


class YouTubeApiAdapter:
    def __init__(
        self,
        source: SourceConfiguration,
        settings: YouTubeApiSettings,
        transport: YouTubeTransport,
        *,
        user_agent: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if len(user_agent) < 8 or len(user_agent) > 300:
            raise ValueError("YouTube API user agent must be explicit and bounded")
        self._source = source
        self._settings = settings
        self._transport = transport
        self._user_agent = user_agent
        self._now = now or (lambda: datetime.now(UTC))

    def fetch(
        self,
        request: YouTubeRequest,
        ledger: BudgetLedger,
        quota: YouTubeQuotaLedger,
    ) -> YouTubeFetchResult:
        self._require_enabled(request)
        quota.ensure_capacity(request.endpoint_id)
        ledger.ensure_capacity(
            BudgetCharge(requests=1, total_bytes=self._settings.max_response_bytes)
        )
        response = self._transport.execute(
            request,
            user_agent=self._user_agent,
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=self._settings.max_response_bytes,
        )
        ledger.consume(BudgetCharge(requests=1))
        quota_cost = quota.consume(request.endpoint_id)
        if response.status_code == 403 and _is_quota_exceeded(response.body):
            raise YouTubeQuotaExceededTransportError()
        if response.status_code < 200 or response.status_code > 299:
            raise YouTubeTransportError(
                f"youtube.http_{response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
                retry_after_seconds=response.retry_after_seconds,
            )
        if len(response.body) > self._settings.max_response_bytes:
            raise YouTubeTransportError("youtube.response_too_large")
        ledger.consume(BudgetCharge(total_bytes=len(response.body)))
        if response.content_type.split(";", maxsplit=1)[0].strip().casefold() != "application/json":
            raise YouTubeTransportError("youtube.content_type_invalid")
        parser = {
            YouTubeEndpoint.SEARCH: parse_youtube_search,
            YouTubeEndpoint.COMMENT_THREADS: parse_youtube_comment_threads,
        }[request.endpoint_id]
        return YouTubeFetchResult(
            retrieved_at=self._timestamp(),
            request=request.provenance(),
            quota_cost=quota_cost,
            batch=parser(response.body),
        )

    def _require_enabled(self, request: YouTubeRequest) -> None:
        if self._source.access != SourceAccess.OFFICIAL_API:
            raise YouTubeTransportError("youtube.source_profile_invalid")
        if self._source.operational_status != "available":
            raise YouTubeTransportError("youtube.operational_hold")
        if not self._settings.enabled:
            raise YouTubeTransportError("youtube.disabled")
        if not self._settings.policy_approved:
            raise YouTubeTransportError("youtube.policy_not_approved")
        if self._source.credential_required and not request.secret_query:
            raise YouTubeTransportError("youtube.credential_missing")

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise YouTubeTransportError("youtube.clock_not_timezone_aware")
        return value


def _validate_endpoint(request: YouTubeRequest) -> None:
    parts = urlsplit(request.url)
    if (
        parts.scheme != "https"
        or parts.hostname != _ALLOWED_HOST
        or parts.path != _ALLOWED_PATHS[request.endpoint_id]
    ):
        raise YouTubeTransportError("youtube.endpoint_invalid")


def _is_quota_exceeded(body: bytes) -> bool:
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(parsed, dict):
        return False
    error = parsed.get("error")
    if not isinstance(error, dict):
        return False
    errors = error.get("errors")
    if not isinstance(errors, list):
        return False
    return any(isinstance(item, dict) and item.get("reason") == "quotaExceeded" for item in errors)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if 0 <= seconds <= 3600 else None
