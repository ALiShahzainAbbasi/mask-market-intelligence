from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from mask_api.config import Settings
from mask_api.contracts import Readiness
from mask_api.health import check_readiness, readiness_report
from mask_api.main import create_app
from pydantic import ValidationError


def test_liveness_no_dependencies(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live", headers={"X-Correlation-ID": str(uuid4())})
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "mask-api"}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-correlation-id"]


@pytest.mark.parametrize("status,code", [("ready", 200), ("not_ready", 503)])
def test_readiness(settings: Settings, status: str, code: int) -> None:
    app = create_app(settings)
    app.dependency_overrides[readiness_report] = lambda: Readiness.model_validate(
        {
            "status": status,
            "dependencies": {"postgres": "up" if code == 200 else "down"},
        }
    )
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == code


def test_probe_failure_is_sanitized() -> None:
    def broken() -> None:
        raise RuntimeError("secret-database-password")

    report = check_readiness(postgres=broken)
    assert report.status == "not_ready"
    assert report.dependencies == {"postgres": "down"}
    assert "secret" not in report.model_dump_json()


def test_development_routes_absent_by_default(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.post("/dev/jobs/smoke", json={}).status_code == 404


def test_development_routes_require_secret(settings: Settings) -> None:
    enabled = Settings(
        **{**settings.model_dump(), "enable_dev_routes": True, "dev_token": "x" * 40},
        _env_file=None,
    )
    with TestClient(create_app(enabled)) as client:
        assert (
            client.post("/dev/jobs/smoke", json={"idempotency_key": str(uuid4())}).status_code
            == 401
        )
        response = client.post(
            "/dev/jobs/smoke",
            json={"idempotency_key": "private bad input"},
            headers={"X-Dev-Token": "x" * 40},
        )
        assert response.status_code == 422
        assert "private" not in response.text


def test_production_cannot_enable_dev_routes() -> None:
    with pytest.raises(ValidationError, match="cannot be enabled"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://localhost/test",
            enable_dev_routes=True,
            dev_token="x" * 40,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_url", "sqlite://"),
        ("dependency_timeout_seconds", 30),
        ("queue_poll_seconds", 0),
        ("job_lease_seconds", 5),
        ("auth_session_hours", 0),
        ("auth_failure_limit", 2),
        ("auth_lockout_seconds", 10),
        ("auth_recent_minutes", 0),
    ],
)
def test_invalid_settings(settings: Settings, field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), field: value}, _env_file=None)


def test_settings_redact_secrets(settings: Settings) -> None:
    assert "postgresql" not in repr(settings)


def test_settings_validation_does_not_log_input_secrets() -> None:
    with pytest.raises(ValidationError) as captured:
        Settings(
            _env_file=None,
            database_url="invalid://private-password",
        )
    assert "private-password" not in str(captured.value)


def test_unexpected_error_is_not_reraised_or_logged(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)

    @app.get("/test-error")
    def fail() -> None:
        raise RuntimeError("private-unexpected-payload")

    # Default TestClient re-raises unhandled server errors: it must not do so.
    with TestClient(app) as client:
        response = client.get("/test-error")
    assert response.status_code == 500
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-correlation-id"]
    assert "private-unexpected-payload" not in response.text
    assert "private-unexpected-payload" not in caplog.text
