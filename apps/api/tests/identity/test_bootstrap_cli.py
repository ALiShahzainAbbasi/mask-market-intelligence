from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from mask_api.modules.identity.auth_contracts import BootstrapResult
from mask_api.modules.identity.errors import (
    BootstrapAlreadyCompleted,
    IdentityUnavailable,
    PasswordPolicyViolation,
)

from scripts import bootstrap_owner

ORG_ID = UUID("10000000-0000-0000-0000-000000000001")
USER_ID = UUID("20000000-0000-0000-0000-000000000002")


def arguments() -> list[str]:
    return [
        "--organization",
        "MASK AI",
        "--name",
        "Owner",
        "--email",
        "owner@example.com",
    ]


def configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    passwords: tuple[str, str] = ("correct horse battery staple",) * 2,
    error: Exception | None = None,
) -> Mock:
    entered = iter(passwords)
    monkeypatch.setattr(bootstrap_owner.getpass, "getpass", lambda _: next(entered))
    service = Mock()
    if error is not None:
        service.create_owner.side_effect = error
    else:
        service.create_owner.return_value = BootstrapResult(
            organization_id=ORG_ID,
            user_id=USER_ID,
            created_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
    monkeypatch.setattr(bootstrap_owner, "get_owner_bootstrap_service", lambda: service)
    return service


def test_bootstrap_cli_is_interactive_and_never_prints_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = configure(monkeypatch)
    assert bootstrap_owner.main(arguments()) == 0
    output = capsys.readouterr().out
    assert "correct horse" not in output
    assert str(ORG_ID) in output and str(USER_ID) in output
    request = service.create_owner.call_args.args[0]
    assert request.password.get_secret_value() == "correct horse battery staple"


def test_bootstrap_cli_rejects_mismatched_confirmation_without_storage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = configure(monkeypatch, passwords=("first-password-value", "second-password-value"))
    assert bootstrap_owner.main(arguments()) == 2
    service.create_owner.assert_not_called()
    assert "did not match" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error", "exit_code", "message"),
    [
        (PasswordPolicyViolation("private input"), 2, "check the supplied"),
        (BootstrapAlreadyCompleted("private state"), 2, "already exists"),
        (IdentityUnavailable("private database"), 1, "failed safely"),
    ],
)
def test_bootstrap_cli_maps_failures_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    message: str,
) -> None:
    configure(monkeypatch, error=error)
    assert bootstrap_owner.main(arguments()) == exit_code
    output = capsys.readouterr().out
    assert message in output
    assert "private" not in output
