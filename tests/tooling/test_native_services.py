from unittest.mock import Mock

import pytest
from mask_api.config import Settings
from mask_api.modules.health.contracts import Readiness
from pydantic import SecretStr

from scripts import check_services as checks


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        enable_dev_routes=True,
        dev_token="synthetic-test-value-" * 3,
        database_url="postgresql+psycopg://mask_app@127.0.0.1:5433/mask",
        migration_database_url="postgresql+psycopg://mask_migrator@127.0.0.1:5433/mask",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid",
        "file:///tmp/api",
        "http://user:private@localhost",
        "http://localhost/private",
        "http://localhost?token=private",
        "http://localhost#fragment",
    ],
)
def test_preflight_rejects_remote_or_credentialed_api(url: str) -> None:
    with pytest.raises(ValueError, match="local development"):
        checks.require_local_test_config(settings(), url)


@pytest.mark.parametrize(
    "change",
    [
        {"environment": "production"},
        {"enable_dev_routes": False},
        {"dev_token": None},
        {"migration_database_url": None},
        {"database_url": SecretStr("postgresql+psycopg://example.invalid/mask")},
        {"migration_database_url": SecretStr("postgresql+psycopg://example.invalid/mask")},
    ],
)
def test_preflight_rejects_unsafe_service_targets(change: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="local development"):
        checks.require_local_test_config(
            settings().model_copy(update=change), "http://127.0.0.1:8000"
        )


def configure(monkeypatch: pytest.MonkeyPatch, ready: bool) -> Mock:
    monkeypatch.setattr(checks, "get_settings", settings)
    monkeypatch.setenv("MASK_TEST_API_URL", "http://127.0.0.1:8000")
    report = Readiness(
        status="ready" if ready else "not_ready",
        dependencies={"postgres": "up" if ready else "down"},
    )
    monkeypatch.setattr(checks, "check_readiness", lambda: report)
    monkeypatch.setattr(checks, "api_ready", lambda _: ready)
    worker = Mock(return_value=ready)
    monkeypatch.setattr(checks, "worker_ready", worker)
    return worker


def test_preflight_missing_database_never_claims_pass_or_attempts_worker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worker = configure(monkeypatch, False)
    assert checks.main() == 1
    worker.assert_not_called()
    assert "NOT run" in capsys.readouterr().out


def test_preflight_checks_worker_when_dependencies_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = configure(monkeypatch, True)
    assert checks.main() == 0
    worker.assert_called_once_with(15)


def test_preflight_masks_configuration_and_connection_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(monkeypatch, True)
    fail = Mock(side_effect=RuntimeError("private-connection-secret"))
    monkeypatch.setattr(checks, "api_ready", fail)
    assert checks.main() == 1
    assert "private" not in capsys.readouterr().out
    monkeypatch.setattr(checks, "get_settings", fail)
    assert checks.main() == 1
    assert "private" not in capsys.readouterr().out


def test_api_preflight_does_not_follow_redirects_or_use_ambient_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get.return_value.status_code = 200
    client.get.return_value.json.return_value = {"status": "ready"}
    context = Mock(__enter__=Mock(return_value=client), __exit__=Mock(return_value=False))
    factory = Mock(return_value=context)
    monkeypatch.setattr(checks.httpx, "Client", factory)
    assert checks.api_ready("http://127.0.0.1:8000/")
    factory.assert_called_once_with(timeout=6, trust_env=False, follow_redirects=False)
    client.get.assert_called_once_with("http://127.0.0.1:8000/health/ready")
    client.get.return_value.status_code = 302
    assert not checks.api_ready("http://127.0.0.1:8000")
