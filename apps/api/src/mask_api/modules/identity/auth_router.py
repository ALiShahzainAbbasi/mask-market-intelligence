"""Local-auth HTTP adapter. Main does not register it until live acceptance."""

import hmac
import json
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import SecretStr

from mask_api.config import Settings
from mask_api.modules.identity.auth_contracts import LoginRequest
from mask_api.modules.identity.auth_http_contracts import LoginBody, SessionResponse
from mask_api.modules.identity.auth_services import LocalAuthenticationService
from mask_api.modules.identity.errors import (
    AuthenticationRequired,
    IdentityUnavailable,
    InvalidCredentials,
    InvalidCsrfToken,
    LoginRateLimited,
)
from mask_api.modules.identity.wiring import get_local_authentication_service

logger = logging.getLogger("mask")
SESSION_COOKIE = "mask_session"
CSRF_COOKIE = "mask_csrf"
Service = Annotated[LocalAuthenticationService, Depends(get_local_authentication_service)]


def _safe_event(event: str, request: Request) -> None:
    logger.info(
        json.dumps(
            {
                "event": event,
                "correlation_id": request.state.correlation_id,
            }
        )
    )


def _set_session_cookies(
    response: Response,
    *,
    session_token: SecretStr,
    csrf_token: SecretStr,
    max_age: int,
    secure: bool,
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_token.get_secret_value(),
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token.get_secret_value(),
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _session_max_age(created_at: datetime, expires_at: datetime, configured_max: int) -> int:
    duration = expires_at - created_at
    return max(1, min(configured_max, int(duration.total_seconds())))


def _clear_session_cookies(response: Response, *, secure: bool) -> None:
    for name, httponly in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(
            name,
            httponly=httponly,
            secure=secure,
            samesite="strict",
            path="/",
        )


def _require_csrf(cookie_value: str | None, header_value: str | None) -> SecretStr:
    if (
        cookie_value is None
        or header_value is None
        or len(cookie_value) > 4096
        or len(header_value) > 4096
        or not hmac.compare_digest(cookie_value, header_value)
    ):
        raise HTTPException(403, "CSRF validation failed")
    return SecretStr(header_value)


def _require_session(value: str | None) -> SecretStr:
    if value is None or not value or len(value) > 4096:
        raise HTTPException(401, "Authentication required")
    return SecretStr(value)


def _map_auth_error(error: Exception) -> HTTPException:
    if isinstance(error, InvalidCredentials):
        return HTTPException(401, "Invalid credentials")
    if isinstance(error, LoginRateLimited):
        return HTTPException(429, "Login temporarily unavailable")
    if isinstance(error, AuthenticationRequired):
        return HTTPException(401, "Authentication required")
    if isinstance(error, InvalidCsrfToken):
        return HTTPException(403, "CSRF validation failed")
    return HTTPException(503, "Identity service unavailable")


def create_auth_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["authentication"])
    secure = settings.environment not in {"development", "test"}
    max_age = settings.auth_session_hours * 60 * 60

    @router.post("/login", response_model=SessionResponse)
    def login(
        payload: LoginBody,
        request: Request,
        response: Response,
        service: Service,
    ) -> SessionResponse:
        try:
            issued = service.login(
                LoginRequest(
                    organization_id=payload.organization_id,
                    email=payload.email,
                    password=payload.password,
                    correlation_id=UUID(request.state.correlation_id),
                )
            )
        except (InvalidCredentials, LoginRateLimited, IdentityUnavailable) as error:
            _safe_event("login_denied", request)
            raise _map_auth_error(error) from None
        _set_session_cookies(
            response,
            session_token=issued.session_token,
            csrf_token=issued.csrf_token,
            max_age=_session_max_age(issued.record.created_at, issued.record.expires_at, max_age),
            secure=secure,
        )
        _safe_event("login_completed", request)
        return SessionResponse(
            organization_id=issued.record.organization_id,
            user_id=issued.record.user_id,
            expires_at=issued.record.expires_at,
        )

    @router.post("/logout", status_code=204)
    def logout(
        request: Request,
        response: Response,
        service: Service,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        session_token = _require_session(session_cookie)
        csrf_token = _require_csrf(csrf_cookie, csrf_header)
        try:
            service.logout(
                session_token,
                csrf_token,
                correlation_id=UUID(request.state.correlation_id),
            )
        except (AuthenticationRequired, InvalidCsrfToken, IdentityUnavailable) as error:
            _safe_event("logout_denied", request)
            raise _map_auth_error(error) from None
        _clear_session_cookies(response, secure=secure)
        _safe_event("logout_completed", request)

    @router.post("/rotate", response_model=SessionResponse)
    def rotate(
        request: Request,
        response: Response,
        service: Service,
        session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
        csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> SessionResponse:
        session_token = _require_session(session_cookie)
        csrf_token = _require_csrf(csrf_cookie, csrf_header)
        try:
            issued = service.rotate(
                session_token,
                csrf_token,
                correlation_id=UUID(request.state.correlation_id),
            )
        except (AuthenticationRequired, InvalidCsrfToken, IdentityUnavailable) as error:
            _safe_event("session_rotation_denied", request)
            raise _map_auth_error(error) from None
        _set_session_cookies(
            response,
            session_token=issued.session_token,
            csrf_token=issued.csrf_token,
            max_age=_session_max_age(issued.record.created_at, issued.record.expires_at, max_age),
            secure=secure,
        )
        _safe_event("session_rotated", request)
        return SessionResponse(
            organization_id=issued.record.organization_id,
            user_id=issued.record.user_id,
            expires_at=issued.record.expires_at,
        )

    return router
