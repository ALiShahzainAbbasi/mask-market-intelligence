"""Credential- and budget-gated Brave Web Search discovery adapter."""

from __future__ import annotations

import contextlib
import hashlib
import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, ValidationError

from mask_api.modules.discovery.contracts import (
    DiscoveryBatch,
    DiscoveryPlan,
    DiscoveryQuery,
    SearchPage,
    SearchResult,
)
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger
from mask_api.research_runner.contracts import SourceAccess, SourceConfiguration

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_API_VERSION = "2023-01-01"


class DiscoveryError(RuntimeError):
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
        super().__init__("search discovery could not be completed safely")


@dataclass(frozen=True)
class BraveSearchSettings:
    enabled: bool = False
    policy_approved: bool = False
    api_key: SecretStr | None = None
    count: int = 10
    max_pages_per_query: int = 1
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    cost_per_request_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.count < 1 or self.count > 20:
            raise ValueError("Brave result count must be between 1 and 20")
        if self.max_pages_per_query < 1 or self.max_pages_per_query > 10:
            raise ValueError("Brave page count must be between 1 and 10")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Brave timeout must be in the interval (0, 60]")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 10_000_000:
            raise ValueError("Brave response byte limit is outside the safe range")
        if self.cost_per_request_usd < 0:
            raise ValueError("Brave request cost cannot be negative")


@dataclass(frozen=True)
class BraveTransportResponse:
    status_code: int
    content_type: str
    body: bytes
    retry_after_seconds: float | None = None


class BraveTransport(Protocol):
    def search(
        self,
        *,
        query: str,
        country: str,
        language: str,
        count: int,
        offset: int,
        api_key: SecretStr,
        timeout_seconds: float,
        max_bytes: int,
    ) -> BraveTransportResponse: ...


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


class UrllibBraveTransport:
    """Fixed-origin TLS transport with no ambient proxies, cookies, or redirects."""

    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def search(
        self,
        *,
        query: str,
        country: str,
        language: str,
        count: int,
        offset: int,
        api_key: SecretStr,
        timeout_seconds: float,
        max_bytes: int,
    ) -> BraveTransportResponse:
        parameters = urlencode(
            {
                "q": query,
                "country": country,
                "search_lang": language,
                "count": count,
                "offset": offset,
                "safesearch": "strict",
            }
        )
        request = Request(
            f"{BRAVE_ENDPOINT}?{parameters}",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Api-Version": BRAVE_API_VERSION,
                "User-Agent": "MASK-AI-Market-Research/0.1",
                "X-Subscription-Token": api_key.get_secret_value(),
            },
            method="GET",
        )
        try:
            response = cast(Any, self._opener.open(request, timeout=timeout_seconds))
            with contextlib.closing(response):
                body = cast(bytes, response.read(max_bytes + 1))
                if len(body) > max_bytes:
                    raise DiscoveryError("brave.response_too_large")
                return BraveTransportResponse(
                    status_code=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=body,
                )
        except HTTPError as error:
            return BraveTransportResponse(
                status_code=error.code,
                content_type=str(error.headers.get("Content-Type", "")),
                body=b"",
                retry_after_seconds=_retry_after(error.headers.get("Retry-After")),
            )
        except (TimeoutError, URLError, OSError) as error:
            raise DiscoveryError("brave.network_error", retryable=True) from error


class _BraveResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    url: str
    description: str | None = None
    age: str | None = None
    page_fetched: AwareDatetime | None = None


class _BraveWeb(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: tuple[_BraveResult, ...] = ()


class _BraveQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original: str | None = None
    more_results_available: bool = False


class _BravePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: _BraveQuery = Field(default_factory=_BraveQuery)
    web: _BraveWeb = Field(default_factory=_BraveWeb)


class BraveSearchAdapter:
    def __init__(
        self,
        source_id: str,
        source: SourceConfiguration,
        settings: BraveSearchSettings,
        transport: BraveTransport,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_id = source_id
        self._source = source
        self._settings = settings
        self._transport = transport
        self._now = now or (lambda: datetime.now(UTC))

    def discover(
        self,
        plan: DiscoveryPlan,
        ledger: BudgetLedger,
        *,
        country: str,
        language: str,
    ) -> DiscoveryBatch:
        self._require_enabled(ledger)
        retrieved_at = self._timestamp()
        pages: list[SearchPage] = []
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for query in plan.queries:
            for offset in range(self._settings.max_pages_per_query):
                page = self._search_page(query, ledger, country, language, offset)
                pages.append(page)
                for result in page.results:
                    canonical = _canonical_result_url(result.url)
                    if canonical in seen_urls:
                        continue
                    seen_urls.add(canonical)
                    results.append(result)
                if not page.more_results_available:
                    break
        return DiscoveryBatch(
            provider="brave_search",
            plan_version=plan.version,
            retrieved_at=retrieved_at,
            pages=tuple(pages),
            results=tuple(results),
        )

    def _search_page(
        self,
        query: DiscoveryQuery,
        ledger: BudgetLedger,
        country: str,
        language: str,
        offset: int,
    ) -> SearchPage:
        api_key = self._settings.api_key
        assert api_key is not None
        maximum = BudgetCharge(
            requests=1,
            total_bytes=self._settings.max_response_bytes,
            paid_cost_usd=self._settings.cost_per_request_usd,
        )
        ledger.ensure_capacity(maximum)
        response = self._transport.search(
            query=query.query,
            country=country,
            language=language,
            count=self._settings.count,
            offset=offset,
            api_key=api_key,
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=self._settings.max_response_bytes,
        )
        if response.status_code < 200 or response.status_code > 299:
            raise DiscoveryError(
                f"brave.http_{response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
                retry_after_seconds=response.retry_after_seconds,
            )
        if len(response.body) > self._settings.max_response_bytes:
            raise DiscoveryError("brave.response_too_large")
        if response.content_type.split(";", maxsplit=1)[0].strip().casefold() != "application/json":
            raise DiscoveryError("brave.content_type_invalid")
        ledger.consume(
            BudgetCharge(
                requests=1,
                total_bytes=len(response.body),
                paid_cost_usd=self._settings.cost_per_request_usd,
            )
        )
        payload = self._parse(response.body)
        results: list[SearchResult] = []
        for index, item in enumerate(payload.web.results, start=1):
            if not _safe_result_url(item.url) or not item.title.strip():
                continue
            results.append(
                SearchResult(
                    provider="brave_search",
                    query_id=query.query_id,
                    rank=offset * self._settings.count + index,
                    url=item.url,
                    title=item.title.strip(),
                    description=item.description,
                    page_age=item.age,
                    page_fetched=item.page_fetched,
                )
            )
        return SearchPage(
            provider="brave_search",
            endpoint=BRAVE_ENDPOINT,
            query_id=query.query_id,
            query=query.query,
            offset=offset,
            retrieved_at=self._timestamp(),
            response_sha256=hashlib.sha256(response.body).hexdigest(),
            raw_response=response.body,
            results=tuple(results),
            more_results_available=payload.query.more_results_available,
        )

    def _require_enabled(self, ledger: BudgetLedger) -> None:
        if self._source_id != "brave_search" or self._source.access != SourceAccess.COMMERCIAL_API:
            raise DiscoveryError("brave.source_profile_invalid")
        if self._source.operational_status != "available":
            raise DiscoveryError("brave.operational_hold")
        if not self._settings.enabled:
            raise DiscoveryError("brave.disabled")
        if not self._settings.policy_approved:
            raise DiscoveryError("brave.policy_not_approved")
        if self._settings.api_key is None or not self._settings.api_key.get_secret_value():
            raise DiscoveryError("brave.credential_missing")
        if self._settings.cost_per_request_usd <= 0:
            raise DiscoveryError("brave.request_cost_missing")
        if ledger.limits.max_paid_cost_usd <= 0:
            raise DiscoveryError("brave.paid_budget_disabled")

    @staticmethod
    def _parse(body: bytes) -> _BravePayload:
        try:
            raw = json.loads(body)
            return _BravePayload.model_validate(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
            raise DiscoveryError("brave.response_invalid") from error

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise DiscoveryError("brave.clock_invalid")
        return value.astimezone(UTC)


def _safe_result_url(value: str) -> bool:
    parts = urlsplit(value)
    return (
        parts.scheme in {"http", "https"}
        and parts.hostname is not None
        and parts.username is None
        and parts.password is None
        and not parts.fragment
    )


def _canonical_result_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path or "/",
            parts.query,
            "",
        )
    )


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
