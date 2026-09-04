from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.modules.identity.contracts import Membership, SessionRecord
from mask_api.modules.identity.domain import OrganizationStatus, Permission, Role, UserStatus
from mask_api.modules.identity.errors import (
    AccessDenied,
    AuthenticationRequired,
    IdentityUnavailable,
    RecentAuthenticationRequired,
)
from mask_api.modules.identity.ports import MembershipReader, SessionReader
from mask_api.modules.identity.services import IdentityService
from pydantic import SecretStr, ValidationError

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)
TOKEN = SecretStr("synthetic-opaque-session-not-a-real-credential")


def context() -> tuple[IdentityService, Mock, Mock, Mock]:
    session = SessionRecord(
        session_id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        authenticated_at=NOW - timedelta(minutes=1),
        created_at=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(minutes=30),
    )
    sessions = Mock(spec=SessionReader)
    sessions.resolve.return_value = session
    memberships = Mock(spec=MembershipReader)
    memberships.get.return_value = Membership(
        organization_id=session.organization_id,
        user_id=session.user_id,
        organization_status=OrganizationStatus.ACTIVE,
        user_status=UserStatus.ACTIVE,
        roles=frozenset({Role.RESEARCHER}),
    )
    clock = Mock(return_value=NOW)
    return (
        IdentityService(sessions, memberships, clock, timedelta(minutes=5)),
        sessions,
        memberships,
        clock,
    )


def test_resolves_membership_only_from_stored_session_and_returns_no_token() -> None:
    service, sessions, memberships, _ = context()
    actor = service.authenticate(TOKEN)
    stored = sessions.resolve.return_value
    sessions.resolve.assert_called_once_with(TOKEN)
    memberships.get.assert_called_once_with(stored.organization_id, stored.user_id)
    assert actor.organization_id == stored.organization_id
    assert actor.user_id == stored.user_id
    assert actor.roles == frozenset({Role.RESEARCHER})
    assert TOKEN.get_secret_value() not in actor.model_dump_json()


@pytest.mark.parametrize("token", [None, SecretStr(""), SecretStr("x" * 4097)])
def test_missing_or_oversized_token_never_reaches_adapters(token: SecretStr | None) -> None:
    service, sessions, memberships, _ = context()
    with pytest.raises(AuthenticationRequired):
        service.authenticate(token)
    sessions.resolve.assert_not_called()
    memberships.get.assert_not_called()


def test_unknown_session_has_no_membership_fallback() -> None:
    service, sessions, memberships, _ = context()
    sessions.resolve.return_value = None
    with pytest.raises(AuthenticationRequired):
        service.authenticate(TOKEN)
    memberships.get.assert_not_called()


@pytest.mark.parametrize("state", ["expired", "revoked", "future"])
def test_session_lifetime_is_enforced_before_membership_lookup(state: str) -> None:
    service, sessions, memberships, clock = context()
    record = sessions.resolve.return_value
    if state == "expired":
        clock.return_value = record.expires_at
    elif state == "future":
        clock.return_value = record.created_at - timedelta(microseconds=1)
    else:
        sessions.resolve.return_value = record.model_copy(update={"revoked_at": NOW})
    with pytest.raises(AuthenticationRequired):
        service.authenticate(TOKEN)
    memberships.get.assert_not_called()


def test_expiry_during_membership_lookup_is_rejected() -> None:
    service, sessions, memberships, clock = context()
    clock.side_effect = [NOW, sessions.resolve.return_value.expires_at]
    with pytest.raises(AuthenticationRequired):
        service.authenticate(TOKEN)
    memberships.get.assert_called_once()


@pytest.mark.parametrize(
    "change",
    [
        {"organization_id": uuid4()},
        {"user_id": uuid4()},
        {"organization_status": OrganizationStatus.SUSPENDED},
        {"user_status": UserStatus.INVITED},
        {"user_status": UserStatus.SUSPENDED},
        {"roles": frozenset()},
    ],
)
def test_inactive_or_mismatched_membership_is_denied(change: dict[str, object]) -> None:
    service, _, memberships, _ = context()
    memberships.get.return_value = memberships.get.return_value.model_copy(update=change)
    with pytest.raises(AccessDenied):
        service.authenticate(TOKEN)


def test_missing_membership_is_denied() -> None:
    service, _, memberships, _ = context()
    memberships.get.return_value = None
    with pytest.raises(AccessDenied):
        service.authenticate(TOKEN)


def test_cross_tenant_request_is_denied_even_to_admin() -> None:
    service, _, memberships, _ = context()
    memberships.get.return_value = memberships.get.return_value.model_copy(
        update={"roles": frozenset({Role.ADMIN})}
    )
    with pytest.raises(AccessDenied):
        service.authorize(
            TOKEN,
            organization_id=uuid4(),
            permission=Permission.MARKET_READ,
            acting_role=Role.ADMIN,
        )


def test_role_changes_are_read_on_every_authorization() -> None:
    service, sessions, memberships, _ = context()
    organization = sessions.resolve.return_value.organization_id
    grant = service.authorize(
        TOKEN,
        organization_id=organization,
        permission=Permission.MARKET_CREATE,
        acting_role=Role.RESEARCHER,
    )
    assert grant.acting_role == Role.RESEARCHER
    memberships.get.return_value = memberships.get.return_value.model_copy(
        update={"roles": frozenset({Role.SALES})}
    )
    with pytest.raises(AccessDenied):
        service.authorize(
            TOKEN,
            organization_id=organization,
            permission=Permission.MARKET_CREATE,
            acting_role=Role.RESEARCHER,
        )
    assert memberships.get.call_count == 2
    assert sessions.resolve.call_count == 2


@pytest.mark.parametrize("age", [timedelta(minutes=1), timedelta(minutes=5)])
def test_admin_actions_require_recent_authentication_at_exact_boundary(age: timedelta) -> None:
    service, sessions, memberships, _ = context()
    sessions.resolve.return_value = sessions.resolve.return_value.model_copy(
        update={"authenticated_at": NOW - age}
    )
    memberships.get.return_value = memberships.get.return_value.model_copy(
        update={"roles": frozenset({Role.ADMIN})}
    )
    kwargs = dict(
        organization_id=sessions.resolve.return_value.organization_id,
        permission=Permission.MEMBERSHIP_MANAGE,
        acting_role=Role.ADMIN,
    )
    if age == timedelta(minutes=5):
        with pytest.raises(RecentAuthenticationRequired):
            service.authorize(TOKEN, **kwargs)
    else:
        assert service.authorize(TOKEN, **kwargs).acting_role == Role.ADMIN


@pytest.mark.parametrize("dependency", ["sessions", "memberships", "clock"])
def test_dependency_failures_are_safe_and_never_allow_access(dependency: str) -> None:
    service, sessions, memberships, clock = context()
    mock = {"sessions": sessions.resolve, "memberships": memberships.get, "clock": clock}[
        dependency
    ]
    mock.side_effect = RuntimeError("private-driver-data-and-token")
    with pytest.raises(IdentityUnavailable) as failure:
        service.authenticate(TOKEN)
    assert str(failure.value) == "Identity service unavailable"
    assert failure.value.__suppress_context__


def test_naive_clock_and_invalid_recent_auth_window_fail_closed() -> None:
    service, sessions, memberships, clock = context()
    clock.return_value = NOW.replace(tzinfo=None)
    with pytest.raises(IdentityUnavailable):
        service.authenticate(TOKEN)
    with pytest.raises(ValueError):
        IdentityService(sessions, memberships, clock, timedelta(0))


def test_contracts_reject_cached_roles_naive_times_and_bad_timeline() -> None:
    _, sessions, _, _ = context()
    data = sessions.resolve.return_value.model_dump()
    for change in (
        {"roles": ["admin"]},
        {"email": "not-proof@example.invalid"},
        {"created_at": NOW.replace(tzinfo=None)},
        {"expires_at": data["created_at"]},
        {"authenticated_at": data["expires_at"]},
    ):
        with pytest.raises(ValidationError):
            SessionRecord.model_validate({**data, **change})
