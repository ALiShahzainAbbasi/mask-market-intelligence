"""Offline structural checks; PostgreSQL constraint execution is separate."""

import ast
import re
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from mask_api.config import Settings
from mask_api.main import create_app
from mask_api.modules.identity.domain import Role
from mask_api.modules.markets.domain import MarketStage, MarketStatus
from mask_api.persistence import registry
from mask_api.persistence.base import Base
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import ExecutableDDLElement

ROOT = Path(__file__).resolve().parents[2]
PHASE2_TABLES = {
    "organizations",
    "users",
    "user_roles",
    "markets",
    "market_definition_versions",
    "market_hypotheses",
    "research_plans",
}
AUTH_TABLES = {"user_credentials", "server_sessions", "identity_security_events"}


def test_phase2_vocabulary_preserves_canonical_roles_and_stages() -> None:
    assert {role.value for role in Role} == {
        "researcher",
        "reviewer",
        "sales",
        "technical",
        "founder",
        "admin",
    }
    assert "hold" in {state.value for state in MarketStatus}
    assert "hold" not in {stage.value for stage in MarketStage}
    assert registry.Market.__mapper__.version_id_col is registry.Market.__table__.c.version


def test_metadata_registers_all_and_only_expected_tables() -> None:
    assert set(Base.metadata.tables) == PHASE2_TABLES | AUTH_TABLES | {
        "jobs",
        "worker_heartbeats",
    }
    for name in PHASE2_TABLES - {"organizations"}:
        assert not Base.metadata.tables[name].c.organization_id.nullable


def test_current_definition_reference_includes_organization_and_market() -> None:
    constraint = next(
        item
        for item in registry.Market.__table__.foreign_key_constraints
        if item.name == "fk_market_current_definition"
    )
    assert list(constraint.column_keys) == [
        "organization_id",
        "id",
        "current_definition_version_id",
    ]
    assert [item.target_fullname for item in constraint.elements] == [
        "market_definition_versions.organization_id",
        "market_definition_versions.market_id",
        "market_definition_versions.id",
    ]
    assert constraint.deferrable and constraint.initially == "DEFERRED"


def test_frozen_migration_matches_current_phase2_metadata() -> None:
    source = (ROOT / "apps/api/migrations/versions/0002_identity_markets.py").read_text()
    assignment = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "UPGRADE_SQL" for target in node.targets
        )
    )
    frozen = ast.literal_eval(assignment.value)
    generated = []

    def capture(statement: ExecutableDDLElement, *args: object, **kwargs: object) -> None:
        generated.append(str(statement.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", capture)
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in sorted(PHASE2_TABLES)],
    )

    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    assert {normalize(value) for value in generated} == {normalize(value) for value in frozen}
    assert "mask_api" not in source  # Historical migration cannot import live models.


def test_expected_schema_revision_matches_alembic_head() -> None:
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "apps/api/alembic.ini")))
    assert scripts.get_heads() == [EXPECTED_SCHEMA_REVISION]


def test_phase2_upgrade_and_downgrade_sql_is_reversible_and_append_only() -> None:
    def sql(*arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments, "--sql"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    upgrade = sql("upgrade", "0001:0002")
    downgrade = sql("downgrade", "0002:0001")
    for name in PHASE2_TABLES:
        assert f"CREATE TABLE {name} (" in upgrade
        assert f"DROP TABLE {name};" in downgrade
    assert "GRANT SELECT, INSERT ON market_definition_versions TO mask_app" in upgrade
    assert "DROP EXTENSION" not in downgrade
    assert "DROP TABLE infrastructure_smoke_jobs" not in downgrade
    assert downgrade.index("DROP CONSTRAINT fk_market_current_definition") < downgrade.index(
        "DROP TABLE market_definition_versions"
    )


def test_market_routes_are_not_exposed_before_authentication() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+psycopg://localhost/test",
    )
    app = create_app(settings)
    assert set(app.openapi()["paths"]) == {"/health/live", "/health/ready"}
    with TestClient(app) as client:
        assert client.get("/markets").status_code == 404
        assert client.post("/v1/markets", json={}).status_code == 404
