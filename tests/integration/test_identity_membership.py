"""Live membership-query acceptance, not OIDC/login end-to-end acceptance."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from mask_api.config import Settings
from mask_api.modules.identity.domain import OrganizationStatus, Role, UserStatus
from mask_api.modules.identity.models import Organization, User, UserRole
from mask_api.modules.identity.repository import SQLAlchemyMembershipReader
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION
from sqlalchemy import Connection, create_engine, insert, make_url, text, update
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture
def membership_database() -> Iterator[
    tuple[Connection, dict[str, UUID], SQLAlchemyMembershipReader]
]:
    settings = Settings()
    assert settings.environment == "development"
    assert make_url(settings.database_url.get_secret_value()).host in {"localhost", "127.0.0.1"}
    engine = create_engine(settings.database_url.get_secret_value())
    ids = {name: uuid4() for name in ("org_a", "org_b", "user_a", "user_b")}
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.scalar(text("SELECT current_user")) == "mask_app"
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == EXPECTED_SCHEMA_REVISION
                )
                for suffix in ("a", "b"):
                    connection.execute(
                        insert(Organization).values(
                            id=ids["org_" + suffix],
                            name="Synthetic identity test",
                        )
                    )
                    connection.execute(
                        insert(User).values(
                            id=ids["user_" + suffix],
                            organization_id=ids["org_" + suffix],
                            name="Synthetic identity",
                            email=f"identity-{suffix}@example.invalid",
                            status="active",
                        )
                    )
                # Session contexts use savepoints and never commit this outer fixture.
                reader = SQLAlchemyMembershipReader(
                    sessionmaker(
                        bind=connection,
                        join_transaction_mode="create_savepoint",
                    )
                )
                yield connection, ids, reader
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_membership_query_rejects_other_tenant_and_missing_user(
    membership_database: tuple[Connection, dict[str, UUID], SQLAlchemyMembershipReader],
) -> None:
    _, ids, reader = membership_database
    own = reader.get(ids["org_a"], ids["user_a"])
    assert own is not None and own.roles == frozenset()
    assert reader.get(ids["org_a"], ids["user_b"]) is None
    assert reader.get(ids["org_b"], ids["user_a"]) is None
    assert reader.get(ids["org_a"], uuid4()) is None


def test_membership_roles_are_fresh_and_scoped(
    membership_database: tuple[Connection, dict[str, UUID], SQLAlchemyMembershipReader],
) -> None:
    connection, ids, reader = membership_database
    for suffix, role in (("a", Role.RESEARCHER), ("a", Role.REVIEWER), ("b", Role.ADMIN)):
        connection.execute(
            insert(UserRole).values(
                organization_id=ids["org_" + suffix],
                user_id=ids["user_" + suffix],
                role=role,
            )
        )
    before = reader.get(ids["org_a"], ids["user_a"])
    assert before is not None and before.roles == frozenset({Role.RESEARCHER, Role.REVIEWER})
    connection.execute(
        update(UserRole)
        .where(
            UserRole.organization_id == ids["org_a"],
            UserRole.user_id == ids["user_a"],
            UserRole.role == Role.RESEARCHER,
        )
        .values(role=Role.SALES)
    )
    after = reader.get(ids["org_a"], ids["user_a"])
    assert after is not None and after.roles == frozenset({Role.SALES, Role.REVIEWER})


@pytest.mark.parametrize("entity", ["organization", "user"])
def test_membership_suspension_is_visible_on_next_lookup(
    membership_database: tuple[Connection, dict[str, UUID], SQLAlchemyMembershipReader],
    entity: str,
) -> None:
    connection, ids, reader = membership_database
    before = reader.get(ids["org_a"], ids["user_a"])
    assert before is not None and before.organization_status == OrganizationStatus.ACTIVE
    assert before.user_status == UserStatus.ACTIVE
    if entity == "organization":
        connection.execute(
            update(Organization)
            .where(
                Organization.id == ids["org_a"],
            )
            .values(status=OrganizationStatus.SUSPENDED)
        )
    else:
        connection.execute(
            update(User)
            .where(
                User.organization_id == ids["org_a"],
                User.id == ids["user_a"],
            )
            .values(status=UserStatus.SUSPENDED)
        )
    after = reader.get(ids["org_a"], ids["user_a"])
    assert after is not None
    assert (
        after.organization_status == OrganizationStatus.SUSPENDED
        if entity == "organization"
        else after.user_status == UserStatus.SUSPENDED
    )
