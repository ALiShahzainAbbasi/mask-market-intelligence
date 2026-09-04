from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.modules.identity.contracts import Membership
from mask_api.modules.identity.domain import OrganizationStatus, Role, UserStatus
from mask_api.modules.identity.errors import IdentityUnavailable
from mask_api.modules.identity.repository import SQLAlchemyMembershipReader
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def reader(rows: list[tuple[object, ...]]) -> tuple[SQLAlchemyMembershipReader, Mock]:
    session = Mock(spec=Session)
    session.execute.return_value.all.return_value = rows
    manager = Mock()
    manager.__enter__ = Mock(return_value=session)
    manager.__exit__ = Mock(return_value=False)
    sessions = Mock(return_value=manager)
    return SQLAlchemyMembershipReader(sessions), session


def test_query_scopes_user_and_role_join_to_tenant_and_uses_bound_parameters() -> None:
    adapter, session = reader([])
    organization, user = uuid4(), uuid4()
    assert adapter.get(organization, user) is None
    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    assert "users.organization_id = %(organization_id_1)s" in sql
    assert "users.id = %(id_1)s" in sql
    assert "user_roles.organization_id = users.organization_id" in sql
    assert "user_roles.user_id = users.id" in sql
    assert "organizations.id = users.organization_id" in sql
    assert compiled.params == {"organization_id_1": organization, "id_1": user}
    session.execute.assert_called_once()


def test_collects_roles_without_leaking_orm_objects_or_email() -> None:
    adapter, _ = reader(
        [
            (OrganizationStatus.ACTIVE, UserStatus.ACTIVE, Role.RESEARCHER),
            (OrganizationStatus.ACTIVE, UserStatus.ACTIVE, Role.REVIEWER),
        ]
    )
    membership = adapter.get(uuid4(), uuid4())
    assert membership is not None
    assert membership.roles == frozenset({Role.RESEARCHER, Role.REVIEWER})
    assert "email" not in Membership.model_fields


def test_member_without_roles_is_not_promoted() -> None:
    adapter, _ = reader([(OrganizationStatus.ACTIVE, UserStatus.ACTIVE, None)])
    membership = adapter.get(uuid4(), uuid4())
    assert membership is not None and membership.roles == frozenset()


def test_database_error_is_sanitized() -> None:
    adapter, session = reader([])
    session.execute.side_effect = OperationalError(
        "private SQL", {}, Exception("private credential")
    )
    with pytest.raises(IdentityUnavailable) as failure:
        adapter.get(uuid4(), uuid4())
    assert str(failure.value) == "Identity service unavailable"
    assert failure.value.__suppress_context__


def test_unknown_database_role_fails_closed() -> None:
    adapter, _ = reader([(OrganizationStatus.ACTIVE, UserStatus.ACTIVE, "superuser")])
    with pytest.raises(IdentityUnavailable):
        adapter.get(uuid4(), uuid4())
