"""Live PostgreSQL acceptance for local credential/session persistence."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from mask_api.config import Settings
from mask_api.modules.identity.auth_contracts import LoginRequest
from mask_api.modules.identity.auth_models import (
    IdentitySecurityEvent,
    ServerSession,
    UserCredential,
)
from mask_api.modules.identity.auth_repository import SQLAlchemyAuthenticationStore
from mask_api.modules.identity.auth_services import LocalAuthenticationService
from mask_api.modules.identity.domain import IdentityEventType, OrganizationStatus, UserStatus
from mask_api.modules.identity.errors import (
    AuthenticationRequired,
    InvalidCredentials,
    LoginRateLimited,
)
from mask_api.modules.identity.models import Organization, User
from mask_api.modules.identity.security import Argon2idPasswordManager, Sha256TokenManager
from mask_api.modules.identity.session_adapter import HashedSessionReader
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION
from pydantic import SecretStr
from sqlalchemy import Connection, create_engine, func, insert, make_url, select, text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
NOW = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)


@pytest.fixture
def authentication_database() -> Iterator[
    tuple[Connection, dict[str, UUID], SQLAlchemyAuthenticationStore]
]:
    settings = Settings()
    assert settings.environment == "development"
    assert make_url(settings.database_url.get_secret_value()).host in {"localhost", "127.0.0.1"}
    engine = create_engine(settings.database_url.get_secret_value())
    ids = {name: uuid4() for name in ("organization", "user")}
    hasher = Argon2idPasswordManager()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.scalar(text("SELECT current_user")) == "mask_app"
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == EXPECTED_SCHEMA_REVISION
                )
                connection.execute(
                    insert(Organization).values(
                        id=ids["organization"],
                        name="Synthetic auth test",
                        status=OrganizationStatus.ACTIVE,
                    )
                )
                connection.execute(
                    insert(User).values(
                        id=ids["user"],
                        organization_id=ids["organization"],
                        name="Synthetic owner",
                        email="auth-owner@example.invalid",
                        status=UserStatus.ACTIVE,
                    )
                )
                connection.execute(
                    insert(UserCredential).values(
                        organization_id=ids["organization"],
                        user_id=ids["user"],
                        password_hash=hasher.hash(SecretStr(PASSWORD)),
                        password_changed_at=NOW,
                    )
                )
                store = SQLAlchemyAuthenticationStore(
                    sessionmaker(
                        bind=connection,
                        expire_on_commit=False,
                        join_transaction_mode="create_savepoint",
                    )
                )
                yield connection, ids, store
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def service(
    store: SQLAlchemyAuthenticationStore,
    clock: list[datetime],
) -> LocalAuthenticationService:
    return LocalAuthenticationService(
        store=store,
        passwords=Argon2idPasswordManager(),
        tokens=Sha256TokenManager(),
        clock=lambda: clock[0],
        session_lifetime=timedelta(hours=8),
        failure_limit=3,
        lockout=timedelta(minutes=15),
    )


def login_request(ids: dict[str, UUID], password: str = PASSWORD) -> LoginRequest:
    return LoginRequest(
        organization_id=ids["organization"],
        email="auth-owner@example.invalid",
        password=SecretStr(password),
        correlation_id=uuid4(),
    )


def test_login_persists_only_hashes_and_logout_revokes(
    authentication_database: tuple[Connection, dict[str, UUID], SQLAlchemyAuthenticationStore],
) -> None:
    connection, ids, store = authentication_database
    authentication = service(store, [NOW])
    issued = authentication.login(login_request(ids))

    persisted = connection.execute(
        select(ServerSession.token_hash, ServerSession.csrf_hash).where(
            ServerSession.id == issued.record.session_id
        )
    ).one()
    assert persisted.token_hash == Sha256TokenManager().digest(issued.session_token)
    assert persisted.csrf_hash == Sha256TokenManager().digest(issued.csrf_token)
    assert issued.session_token.get_secret_value() not in persisted.token_hash
    assert (
        HashedSessionReader(store, Sha256TokenManager()).resolve(issued.session_token) is not None
    )

    authentication.logout(
        issued.session_token,
        issued.csrf_token,
        correlation_id=uuid4(),
    )
    with pytest.raises(AuthenticationRequired):
        authentication.logout(
            issued.session_token,
            issued.csrf_token,
            correlation_id=uuid4(),
        )


def test_failed_logins_lock_account_without_creating_sessions(
    authentication_database: tuple[Connection, dict[str, UUID], SQLAlchemyAuthenticationStore],
) -> None:
    connection, ids, store = authentication_database
    authentication = service(store, [NOW])
    for _ in range(3):
        with pytest.raises(InvalidCredentials):
            authentication.login(login_request(ids, "incorrect password value"))
    with pytest.raises(LoginRateLimited):
        authentication.login(login_request(ids))

    assert connection.scalar(select(UserCredential.failed_login_count)) == 3
    assert connection.scalar(select(func.count()).select_from(ServerSession)) == 0
    assert (
        connection.scalar(
            select(func.count())
            .select_from(IdentitySecurityEvent)
            .where(IdentitySecurityEvent.event_type == IdentityEventType.LOGIN_FAILED)
        )
        == 3
    )


def test_rotation_atomically_revokes_old_session_and_keeps_absolute_expiry(
    authentication_database: tuple[Connection, dict[str, UUID], SQLAlchemyAuthenticationStore],
) -> None:
    connection, ids, store = authentication_database
    clock = [NOW]
    authentication = service(store, clock)
    original = authentication.login(login_request(ids))
    clock[0] += timedelta(minutes=10)
    replacement = authentication.rotate(
        original.session_token,
        original.csrf_token,
        correlation_id=uuid4(),
    )

    sessions = connection.execute(
        select(
            ServerSession.id,
            ServerSession.revocation_reason,
            ServerSession.rotated_from_id,
        ).where(ServerSession.id.in_([original.record.session_id, replacement.record.session_id]))
    ).all()
    by_id = {session.id: session for session in sessions}
    assert by_id[original.record.session_id].revocation_reason == "rotated"
    assert by_id[replacement.record.session_id].rotated_from_id == original.record.session_id
    assert replacement.record.expires_at == original.record.expires_at
