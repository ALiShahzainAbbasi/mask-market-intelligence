"""Bounded fixed-origin transport and parser composition for official APIs."""

from __future__ import annotations

import contextlib
import json
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from mask_api.modules.official_data.contracts import OfficialFetchResult, OfficialSourceId
from mask_api.modules.official_data.parsers import (
    parse_bea,
    parse_bls,
    parse_census_cbp,
    parse_sam_opportunities,
    parse_sec_submissions,
)
from mask_api.modules.official_data.requests import OfficialRequest
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger
from mask_api.research_runner.contracts import SourceAccess, SourceConfiguration


class OfficialTransportError(RuntimeError):
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
        super().__init__("official API request could not be completed safely")


@dataclass(frozen=True)
class OfficialTransportResponse:
    status_code: int
    content_type: str
    body: bytes
    retry_after_seconds: float | None = None


@dataclass(frozen=True)
class OfficialApiSettings:
    enabled: bool = False
    policy_approved: bool = False
    timeout_seconds: float = 10
    max_response_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("official API timeout must be in the interval (0, 60]")
        if self.max_response_bytes < 1024 or self.max_response_bytes > 10_000_000:
            raise ValueError("official API response limit is outside the safe range")


class OfficialTransport(Protocol):
    def execute(
        self,
        request: OfficialRequest,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> OfficialTransportResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class UrllibOfficialTransport:
    def __init__(self) -> None:
        self._opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )

    def execute(
        self,
        request: OfficialRequest,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> OfficialTransportResponse:
        _validate_endpoint(request)
        query = dict(request.query)
        query.update(
            {name: value.get_secret_value() for name, value in request.secret_query.items()}
        )
        url = request.endpoint + (f"?{urlencode(query)}" if query else "")
        body = None
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": user_agent,
        }
        if request.method == "POST":
            payload = dict(request.json_body or {})
            payload.update(
                {name: value.get_secret_value() for name, value in request.secret_body.items()}
            )
            body = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        web_request = Request(url, data=body, headers=headers, method=request.method)
        try:
            response = cast(Any, self._opener.open(web_request, timeout=timeout_seconds))
            with contextlib.closing(response):
                content = cast(bytes, response.read(max_bytes + 1))
                if len(content) > max_bytes:
                    raise OfficialTransportError("official.response_too_large")
                return OfficialTransportResponse(
                    status_code=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    body=content,
                )
        except HTTPError as error:
            return OfficialTransportResponse(
                error.code,
                str(error.headers.get("Content-Type", "")),
                b"",
                _retry_after(error.headers.get("Retry-After")),
            )
        except (TimeoutError, URLError, OSError) as error:
            raise OfficialTransportError("official.network_error", retryable=True) from error


class OfficialApiAdapter:
    def __init__(
        self,
        source_id: str,
        source: SourceConfiguration,
        settings: OfficialApiSettings,
        transport: OfficialTransport,
        *,
        user_agent: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if len(user_agent) < 8 or len(user_agent) > 300:
            raise ValueError("official API user agent must be explicit and bounded")
        self._source_id = source_id
        self._source = source
        self._settings = settings
        self._transport = transport
        self._user_agent = user_agent
        self._now = now or (lambda: datetime.now(UTC))

    def fetch(self, request: OfficialRequest, ledger: BudgetLedger) -> OfficialFetchResult:
        self._require_enabled(request)
        if request.source_id == OfficialSourceId.SEC_EDGAR and not re.search(
            r"\S+@\S+\.\S+", self._user_agent
        ):
            raise OfficialTransportError("sec.contact_user_agent_required")
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
        if response.status_code < 200 or response.status_code > 299:
            raise OfficialTransportError(
                f"official.http_{response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
                retry_after_seconds=response.retry_after_seconds,
            )
        if len(response.body) > self._settings.max_response_bytes:
            raise OfficialTransportError("official.response_too_large")
        ledger.consume(BudgetCharge(total_bytes=len(response.body)))
        if response.content_type.split(";", maxsplit=1)[0].strip().casefold() != "application/json":
            raise OfficialTransportError("official.content_type_invalid")
        parser = {
            OfficialSourceId.CENSUS_CBP: parse_census_cbp,
            OfficialSourceId.BLS: parse_bls,
            OfficialSourceId.BEA: parse_bea,
            OfficialSourceId.SEC_EDGAR: parse_sec_submissions,
            OfficialSourceId.SAM_GOV: parse_sam_opportunities,
        }[request.source_id]
        return OfficialFetchResult(
            retrieved_at=self._timestamp(),
            request=request.provenance(),
            batch=parser(response.body),
        )

    def _require_enabled(self, request: OfficialRequest) -> None:
        if (
            self._source_id != request.source_id.value
            or self._source.access != SourceAccess.OFFICIAL_API
        ):
            raise OfficialTransportError("official.source_profile_invalid")
        if self._source.operational_status != "available":
            raise OfficialTransportError("official.operational_hold")
        if not self._settings.enabled:
            raise OfficialTransportError("official.disabled")
        if not self._settings.policy_approved:
            raise OfficialTransportError("official.policy_not_approved")
        if self._source.credential_required and not (request.secret_query or request.secret_body):
            raise OfficialTransportError("official.credential_missing")

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise OfficialTransportError("official.clock_not_timezone_aware")
        return value


def _validate_endpoint(request: OfficialRequest) -> None:
    parts = urlsplit(request.endpoint)
    valid = {
        OfficialSourceId.CENSUS_CBP: parts.hostname == "api.census.gov"
        and bool(re.fullmatch(r"/data/[0-9]{4}/cbp", parts.path)),
        OfficialSourceId.BLS: request.endpoint
        == "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        OfficialSourceId.BEA: request.endpoint == "https://apps.bea.gov/api/data/",
        OfficialSourceId.SEC_EDGAR: parts.hostname == "data.sec.gov"
        and bool(re.fullmatch(r"/submissions/CIK[0-9]{10}\.json", parts.path)),
        OfficialSourceId.SAM_GOV: request.endpoint == "https://api.sam.gov/opportunities/v2/search",
    }
    if parts.scheme != "https" or not valid[request.source_id]:
        raise OfficialTransportError("official.endpoint_invalid")


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if 0 <= seconds <= 3600 else None
