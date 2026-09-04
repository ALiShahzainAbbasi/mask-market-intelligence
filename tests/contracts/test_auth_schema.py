"""Offline authentication schema checks; real PostgreSQL execution remains separate."""

import ast
import re
import subprocess
import sys
from pathlib import Path

from mask_api.persistence import registry
from mask_api.persistence.base import Base
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import ExecutableDDLElement

ROOT = Path(__file__).resolve().parents[2]
AUTH_TABLES = {"user_credentials", "server_sessions", "identity_security_events"}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def test_auth_models_are_registered_with_hash_and_tenant_constraints() -> None:
    assert registry.UserCredential.__table__.name == "user_credentials"
    assert registry.ServerSession.__table__.name == "server_sessions"
    assert registry.IdentitySecurityEvent.__table__.name == "identity_security_events"
    sessions = Base.metadata.tables["server_sessions"]
    assert sessions.c.token_hash.type.length == 64
    assert sessions.c.csrf_hash.type.length == 64
    assert sessions.c.organization_id.nullable is False
    assert sessions.c.user_id.nullable is False
    assert {constraint.name for constraint in sessions.constraints} >= {
        "uq_session_token_hash",
        "uq_session_rotation_source",
        "ck_session_timeline",
        "ck_session_revocation_pair",
        "fk_session_tenant_user",
    }


def test_frozen_auth_migration_matches_current_metadata() -> None:
    source = (ROOT / "apps/api/migrations/versions/0004_local_authentication.py").read_text()
    assignment = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "UPGRADE_SQL" for target in node.targets
        )
    )
    frozen = ast.literal_eval(assignment.value)
    generated: list[str] = []

    def capture(statement: ExecutableDDLElement, *args: object, **kwargs: object) -> None:
        generated.append(str(statement.compile(dialect=engine.dialect)))

    engine = create_mock_engine("postgresql+psycopg://", capture)
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in sorted(AUTH_TABLES)]
    )
    assert {_normalize(value) for value in generated} == {_normalize(value) for value in frozen}
    assert "mask_api" not in source


def test_auth_migration_offline_upgrade_and_downgrade_are_scoped() -> None:
    def sql(*arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments, "--sql"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    upgrade = sql("upgrade", "0003:0004")
    downgrade = sql("downgrade", "0004:0003")
    for name in AUTH_TABLES:
        assert f"CREATE TABLE {name} (" in upgrade
        assert f"DROP TABLE {name};" in downgrade
    assert (
        "GRANT SELECT, INSERT, UPDATE ON user_credentials, server_sessions TO mask_app" in upgrade
    )
    assert "GRANT SELECT, INSERT ON identity_security_events TO mask_app" in upgrade
    assert "DROP TABLE jobs" not in downgrade
