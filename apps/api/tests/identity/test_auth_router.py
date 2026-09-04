from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mask_api.config import Settings
from mask_api.modules.identity.auth_contracts import IssuedSession
from mask_api.modules.identity.auth_router import create_auth_router
from mask_api.modules.identity.contracts import SessionRecord
from mask_api.modules.identity.errors import (
    AuthenticationRequired,
    IdentityUnavailable,
    InvalidCredentials,
    InvalidCsrfToken,
    LoginRateLimited,
)
from mask_api.modules.identity.wiring import get_local_authentication_service
from mask_api.transport.errors import install_error_handlers
from mask_api.transport.middleware import install_http_middleware
from pydantic import SecretStr

NOW = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)
ORG_ID = UUID("10000000-0000-0000-0000-000000000001")
USER_ID = UUID("20000000-0000-0000-0000-000000000002")
SESSION_ID = UUID("30000000-0000-0000-0000-000000000003")


def settings(environment: str = "test") -> Settings:
    return Settings(
        _env_file=None,
        environment=environment,
        database_url="postgresql+psycopg://localhost/test",
    )


def issued() -> IssuedSession:
    return IssuedSession(
        record=SessionRecord(
            session_id=SESSION_ID,
            organization_id=ORG_ID,
            user_id=USER_ID,
            authenticated_at=NOW,
            created_at=NOW,
            expires_at=NOW + timedelta(hours=8),
        ),
        session_token=SecretStr("opaque-session-token"),
        csrf_token=SecretStr("opaque-csrf-token"),
    )


def client(
    service: Mock,
    *,
    environment: str = "test",
) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)
    install_http_middleware(app)
    app.include_router(create_auth_router(settings(environment)))
    app.dependency_overrides[get_local_authentication_service] = lambda: service
    return TestClient(app)


def login_payload() -> dict[str, str]:
    return {
        "organization_id": str(ORG_ID),
        "email": "owner@example.com",
        "password": "correct horse battery staple",
    }


def test_login_sets_strict_cookies_and_never_returns_secrets() -> None:
    service = Mock()
    service.login.return_value = issued()
    with client(service) as browser:
        response = browser.post("/auth/login", json=login_payload())

    assert response.status_code == 200
    assert response.json() == {
        "organization_id": str(ORG_ID),
        "user_id": str(USER_ID),
        "expires_at": "2026-09-04T04:00:00Z",
    }
    assert "opaque-session-token" not in response.text
    assert "opaque-csrf-token" not in response.text
    cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookie_headers if value.startswith("mask_session="))
    csrf_cookie = next(value for value in cookie_headers if value.startswith("mask_csrf="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    assert "HttpOnly" not in csrf_cookie and "SameSite=strict" in csrf_cookie
    assert "Secure" not in session_cookie


def test_production_login_marks_both_cookies_secure() -> None:
    service = Mock()
    service.login.return_value = issued()
    with client(service, environment="production") as browser:
        response = browser.post("/auth/login", json=login_payload())
    assert response.status_code == 200
    assert all("Secure" in value for value in response.headers.get_list("set-cookie"))


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InvalidCredentials("private account"), 401),
        (LoginRateLimited("private account"), 429),
        (IdentityUnavailable("private database"), 503),
    ],
)
def test_login_errors_are_sanitized(error: Exception, status: int) -> None:
    service = Mock()
    service.login.side_effect = error
    with client(service) as browser:
        response = browser.post("/auth/login", json=login_payload())
    assert response.status_code == status
    assert "private" not in response.text
    assert "password" not in response.text


def test_logout_requires_double_submit_csrf_before_calling_service() -> None:
    service = Mock()
    with client(service) as browser:
        browser.cookies.set("mask_session", "opaque-session-token")
        browser.cookies.set("mask_csrf", "opaque-csrf-token")
        response = browser.post("/auth/logout", headers={"X-CSRF-Token": "wrong-token"})
    assert response.status_code == 403
    service.logout.assert_not_called()


def test_logout_revokes_and_clears_both_cookies() -> None:
    service = Mock()
    with client(service) as browser:
        browser.cookies.set("mask_session", "opaque-session-token")
        browser.cookies.set("mask_csrf", "opaque-csrf-token")
        response = browser.post(
            "/auth/logout",
            headers={"X-CSRF-Token": "opaque-csrf-token"},
        )
    assert response.status_code == 204
    service.logout.assert_called_once()
    cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        value.startswith("mask_session=") and "Max-Age=0" in value for value in cookie_headers
    )
    assert any(value.startswith("mask_csrf=") and "Max-Age=0" in value for value in cookie_headers)


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AuthenticationRequired("private token"), 401),
        (InvalidCsrfToken("private csrf"), 403),
        (IdentityUnavailable("private database"), 503),
    ],
)
def test_rotation_errors_are_sanitized(error: Exception, status: int) -> None:
    service = Mock()
    service.rotate.side_effect = error
    with client(service) as browser:
        browser.cookies.set("mask_session", "opaque-session-token")
        browser.cookies.set("mask_csrf", "opaque-csrf-token")
        response = browser.post(
            "/auth/rotate",
            headers={"X-CSRF-Token": "opaque-csrf-token"},
        )
    assert response.status_code == status
    assert "private" not in response.text


def test_validation_errors_do_not_echo_passwords() -> None:
    service = Mock()
    with client(service) as browser:
        response = browser.post(
            "/auth/login",
            json={**login_payload(), "password": "private", "unexpected": "private"},
        )
    assert response.status_code == 422
    assert "private" not in response.text
    service.login.assert_not_called()
