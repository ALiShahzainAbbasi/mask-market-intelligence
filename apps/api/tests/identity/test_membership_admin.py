from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.modules.identity.auth_ports import SessionMutationGuard
from mask_api.modules.identity.contracts import AccessGrant, AuthenticatedActor
from mask_api.modules.identity.domain import Permission, Role
from mask_api.modules.identity.errors import IdentityUnavailable, InvalidCsrfToken
from mask_api.modules.identity.membership_contracts import MemberRolesChanged, ReplaceMemberRoles
from mask_api.modules.identity.membership_ports import MembershipRoleStore
from mask_api.modules.identity.membership_services import MembershipAdministrationService
from mask_api.modules.identity.services import IdentityService
from pydantic import SecretStr, ValidationError

NOW = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
SESSION_TOKEN = SecretStr("opaque-session")
CSRF_TOKEN = SecretStr("opaque-csrf")


def request(**changes: object) -> ReplaceMemberRoles:
    values: dict[str, object] = {
        "session_token": SESSION_TOKEN,
        "csrf_token": CSRF_TOKEN,
        "target_user_id": uuid4(),
        "roles": frozenset({Role.RESEARCHER, Role.REVIEWER}),
        "reason": "Assign research review responsibilities",
        "correlation_id": uuid4(),
    }
    values.update(changes)
    return ReplaceMemberRoles(**values)


def context() -> tuple[MembershipAdministrationService, Mock, Mock, Mock]:
    actor = AuthenticatedActor(
        organization_id=uuid4(),
        user_id=uuid4(),
        session_id=uuid4(),
        authenticated_at=NOW - timedelta(minutes=1),
        roles=frozenset({Role.ADMIN}),
    )
    identity = Mock(spec=IdentityService)
    identity.authorize_current_tenant.return_value = AccessGrant(
        actor=actor,
        permission=Permission.MEMBERSHIP_MANAGE,
        acting_role=Role.ADMIN,
    )
    csrf = Mock(spec=SessionMutationGuard)
    store = Mock(spec=MembershipRoleStore)
    clock = Mock(return_value=NOW)
    service = MembershipAdministrationService(identity, csrf, store, clock)
    return service, identity, csrf, store


def test_role_change_uses_trusted_session_tenant_and_is_auditable() -> None:
    service, identity, csrf, store = context()
    command = request()
    store.replace_roles.return_value = MemberRolesChanged(
        organization_id=identity.authorize_current_tenant.return_value.actor.organization_id,
        target_user_id=command.target_user_id,
        previous_roles=frozenset({Role.RESEARCHER}),
        roles=command.roles,
    )
    assert service.replace_roles(command).roles == command.roles
    csrf.validate_csrf.assert_called_once_with(SESSION_TOKEN, CSRF_TOKEN)
    identity.authorize_current_tenant.assert_called_once_with(
        SESSION_TOKEN,
        permission=Permission.MEMBERSHIP_MANAGE,
        acting_role=Role.ADMIN,
    )
    arguments = store.replace_roles.call_args.kwargs
    actor = identity.authorize_current_tenant.return_value.actor
    assert arguments["organization_id"] == actor.organization_id
    assert arguments["actor_user_id"] == actor.user_id
    assert arguments["reason"] == command.reason
    assert arguments["occurred_at"] == NOW


def test_csrf_denial_stops_authorization_and_storage() -> None:
    service, identity, csrf, store = context()
    csrf.validate_csrf.side_effect = InvalidCsrfToken("private csrf")
    with pytest.raises(InvalidCsrfToken):
        service.replace_roles(request())
    identity.authorize_current_tenant.assert_not_called()
    store.replace_roles.assert_not_called()


def test_naive_or_failed_clock_denies_without_writing() -> None:
    service, _, _, store = context()
    service = MembershipAdministrationService(
        service.identity, service.csrf, service.store, lambda: NOW.replace(tzinfo=None)
    )
    with pytest.raises(IdentityUnavailable):
        service.replace_roles(request())
    store.replace_roles.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"roles": frozenset()},
        {"reason": "no"},
        {"reason": " not trimmed "},
    ],
)
def test_role_change_contract_rejects_unsafe_input(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        request(**change)
