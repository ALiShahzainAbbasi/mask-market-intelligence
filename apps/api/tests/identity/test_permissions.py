from typing import cast

import pytest
from mask_api.modules.identity.domain import PERMISSION_ROLES, Permission, Role, role_permits

EXPECTED = {
    Role.RESEARCHER: {
        Permission.MARKET_READ,
        Permission.MARKET_CREATE,
        Permission.MARKET_UPDATE,
        Permission.MARKET_ARCHIVE,
        Permission.RESEARCH_PLAN_DRAFT,
    },
    Role.REVIEWER: {Permission.MARKET_READ, Permission.RESEARCH_PLAN_APPROVE},
    Role.SALES: {Permission.MARKET_READ},
    Role.TECHNICAL: {Permission.MARKET_READ},
    Role.FOUNDER: {Permission.MARKET_READ},
    Role.ADMIN: {Permission.MARKET_READ, Permission.MEMBERSHIP_MANAGE},
}


@pytest.mark.parametrize("role", list(Role))
def test_explicit_role_matrix(role: Role) -> None:
    for permission in Permission:
        assert role_permits(frozenset({role}), permission, role) == (permission in EXPECTED[role])


def test_every_permission_is_explicit_and_map_is_immutable() -> None:
    assert set(PERMISSION_ROLES) == set(Permission)
    with pytest.raises(TypeError):
        PERMISSION_ROLES[Permission.MARKET_CREATE] = frozenset(Role)  # type: ignore[index]


def test_unknown_permission_and_unassigned_acting_role_are_denied() -> None:
    assert not role_permits(frozenset(Role), cast(Permission, "*"), Role.ADMIN)
    assert not role_permits(frozenset(), Permission.MARKET_READ, Role.RESEARCHER)
    assert not role_permits(
        frozenset({Role.RESEARCHER}), Permission.RESEARCH_PLAN_APPROVE, Role.REVIEWER
    )


def test_multiple_roles_do_not_silently_select_an_approval_role() -> None:
    roles = frozenset({Role.RESEARCHER, Role.REVIEWER})
    assert role_permits(roles, Permission.RESEARCH_PLAN_APPROVE, Role.REVIEWER)
    assert not role_permits(roles, Permission.RESEARCH_PLAN_APPROVE, Role.RESEARCHER)
