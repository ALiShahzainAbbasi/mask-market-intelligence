"""Real PostgreSQL checks; every synthetic data transaction is rolled back."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from mask_api.config import Settings
from mask_api.persistence import registry as tables
from mask_api.persistence.base import Base
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION
from sqlalchemy import Connection, create_engine, insert, make_url, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

pytestmark = pytest.mark.integration


@pytest.fixture
def database() -> Iterator[tuple[Connection, dict[str, UUID]]]:
    settings = Settings()
    assert settings.environment == "development"
    assert make_url(settings.database_url.get_secret_value()).host in {"localhost", "127.0.0.1"}
    engine = create_engine(settings.database_url.get_secret_value())
    ids = {
        name: uuid4()
        for name in ("org_a", "org_b", "user_a", "user_b", "m1", "m2", "m3", "d1", "d2", "d3")
    }
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == EXPECTED_SCHEMA_REVISION
                )
                assert connection.scalar(text("SELECT current_user")) == "mask_app"
                for suffix in ("a", "b"):
                    connection.execute(
                        insert(tables.Organization).values(
                            id=ids["org_" + suffix],
                            name="Synthetic schema test",
                        )
                    )
                    connection.execute(
                        insert(tables.User).values(
                            id=ids["user_" + suffix],
                            organization_id=ids["org_" + suffix],
                            name="Synthetic user",
                            email=f"{suffix}@example.invalid",
                            status="active",
                        )
                    )
                for number, suffix in ((1, "a"), (2, "a"), (3, "b")):
                    fields = {
                        "name": "Synthetic market",
                        "submarket": "Fixture",
                        "geography": "Test",
                        "company_size_definition": "Test band",
                        "likely_buyer": "Fixture buyer",
                    }
                    connection.execute(
                        insert(tables.Market).values(
                            **fields,
                            id=ids[f"m{number}"],
                            organization_id=ids["org_" + suffix],
                            research_owner_id=ids["user_" + suffix],
                            current_definition_version_id=ids[f"d{number}"],
                        )
                    )
                    connection.execute(
                        insert(tables.MarketDefinitionVersion).values(
                            **fields,
                            id=ids[f"d{number}"],
                            organization_id=ids["org_" + suffix],
                            market_id=ids[f"m{number}"],
                            version_number=1,
                            change_reason="Synthetic fixture",
                            created_by=ids["user_" + suffix],
                        )
                    )
                # Validate the deferred cyclic FK before any test assertions.
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                yield connection, ids
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_postgres_metadata_matches_models(database: tuple[Connection, dict[str, UUID]]) -> None:
    connection, _ = database
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_cross_tenant_role_rejected(database: tuple[Connection, dict[str, UUID]]) -> None:
    connection, ids = database
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            insert(tables.UserRole).values(
                id=uuid4(),
                organization_id=ids["org_a"],
                user_id=ids["user_b"],
                role="researcher",
            )
        )


def test_cross_tenant_owner_rejected(database: tuple[Connection, dict[str, UUID]]) -> None:
    connection, ids = database
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            update(tables.Market)
            .where(tables.Market.id == ids["m1"])
            .values(
                research_owner_id=ids["user_b"],
            )
        )


@pytest.mark.parametrize("definition", ["d2", "d3"])
def test_other_market_definition_rejected(
    database: tuple[Connection, dict[str, UUID]],
    definition: str,
) -> None:
    connection, ids = database
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            update(tables.Market)
            .where(tables.Market.id == ids["m1"])
            .values(
                current_definition_version_id=ids[definition],
            )
        )


@pytest.mark.parametrize("kind", ["hypothesis", "plan"])
def test_child_definition_scope_rejected(
    database: tuple[Connection, dict[str, UUID]],
    kind: str,
) -> None:
    connection, ids = database
    values = {
        "id": uuid4(),
        "organization_id": ids["org_a"],
        "market_id": ids["m1"],
        "market_definition_version_id": ids["d2"],
        "created_by": ids["user_a"],
    }
    statement = (
        insert(tables.MarketHypothesis).values(
            **values,
            hypothesis_type="fixture",
            statement="Synthetic test only",
        )
        if kind == "hypothesis"
        else insert(tables.ResearchPlan).values(
            **values,
            research_profile="test-only",
            methodology_version="unapproved-fixture",
        )
    )
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(statement)


def test_definition_snapshot_cannot_be_updated(
    database: tuple[Connection, dict[str, UUID]],
) -> None:
    connection, ids = database
    with pytest.raises(ProgrammingError) as failure, connection.begin_nested():
        connection.execute(
            update(tables.MarketDefinitionVersion)
            .where(
                tables.MarketDefinitionVersion.id == ids["d1"],
            )
            .values(change_reason="Forbidden mutation")
        )
    assert failure.value.orig.sqlstate == "42501"
    assert (
        connection.scalar(
            select(tables.MarketDefinitionVersion.change_reason).where(
                tables.MarketDefinitionVersion.id == ids["d1"],
            )
        )
        == "Synthetic fixture"
    )


def test_approval_requires_actor_and_timestamp(
    database: tuple[Connection, dict[str, UUID]],
) -> None:
    connection, ids = database
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            insert(tables.ResearchPlan).values(
                id=uuid4(),
                organization_id=ids["org_a"],
                market_id=ids["m1"],
                market_definition_version_id=ids["d1"],
                created_by=ids["user_a"],
                research_profile="test-only",
                methodology_version="unapproved-fixture",
                status="approved",
            )
        )
