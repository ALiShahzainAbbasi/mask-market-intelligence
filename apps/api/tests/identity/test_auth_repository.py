from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.modules.identity.auth_models import ServerSession, UserCredential
from mask_api.modules.identity.auth_repository import SQLAlchemyAuthenticationStore
from mask_api.modules.identity.domain import OrganizationStatus, UserStatus
from mask_api.modules.identity.errors import IdentityUnavailable
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def adapter() -> tuple[SQLAlchemyAuthenticationStore, Mock]:
    session = Mock(spec=Session)
    manager = Mock()
    manager.__enter__ = Mock(return_value=session)
    manager.__exit__ = Mock(return_value=False)
    sessions = Mock(return_value=manager)
    return SQLAlchemyAuthenticationStore(sessions), session


def test_credential_lookup_is_tenant_scoped_and_parameterized() -> None:
    store, session = adapter()
    session.execute.return_value.one_or_none.return_value = None
    organization_id = uuid4()
    assert store.find(organization_id, "owner@example.com") is None

    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    assert "user_credentials.organization_id = %(organization_id_1)s" in sql
    assert "users.email = %(email_1)s" in sql
    assert "users.id = user_credentials.user_id" in sql
    assert "organizations.id = users.organization_id" in sql
    assert compiled.params == {
        "organization_id_1": organization_id,
        "email_1": "owner@example.com",
    }


def test_credential_lookup_returns_values_not_orm_identity() -> None:
    store, session = adapter()
    organization_id, user_id = uuid4(), uuid4()
    record = UserCredential(
        organization_id=organization_id,
        user_id=user_id,
        password_hash="$argon2id$synthetic-password-hash",
        password_changed_at=NOW,
        failed_login_count=2,
        locked_until=NOW + timedelta(minutes=1),
    )
    session.execute.return_value.one_or_none.return_value = (
        record,
        OrganizationStatus.ACTIVE,
        UserStatus.ACTIVE,
    )

    result = store.find(organization_id, "owner@example.com")
    assert result is not None
    assert result.user_id == user_id
    assert result.failed_login_count == 2
    assert result.password_hash == record.password_hash


def test_session_lookup_uses_only_fixed_hash_and_maps_safe_record() -> None:
    store, session = adapter()
    organization_id, user_id, session_id = uuid4(), uuid4(), uuid4()
    persisted = ServerSession(
        id=session_id,
        organization_id=organization_id,
        user_id=user_id,
        token_hash="a" * 64,
        csrf_hash="b" * 64,
        authenticated_at=NOW,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    session.scalar.return_value = persisted

    result = store.resolve_hash("a" * 64)
    assert result is not None and result.record.session_id == session_id
    assert result.csrf_hash == "b" * 64
    compiled = session.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
    assert compiled.params == {"token_hash_1": "a" * 64}


def test_auth_repository_database_errors_are_sanitized() -> None:
    store, session = adapter()
    session.execute.side_effect = OperationalError(
        "private SQL", {}, Exception("private database password")
    )
    with pytest.raises(IdentityUnavailable, match="Identity service unavailable") as caught:
        store.find(uuid4(), "owner@example.com")
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__
