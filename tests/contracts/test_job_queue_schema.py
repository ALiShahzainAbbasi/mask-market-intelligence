"""Offline queue schema checks; PostgreSQL concurrency execution is separate."""

import ast
import re
import subprocess
import sys
from pathlib import Path

import mask_api.persistence.registry  # noqa: F401
from mask_api.persistence.base import Base
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import ExecutableDDLElement

ROOT = Path(__file__).resolve().parents[2]
QUEUE_TABLES = {"jobs", "worker_heartbeats"}


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def test_frozen_queue_migration_matches_current_metadata() -> None:
    source = (ROOT / "apps/api/migrations/versions/0003_postgres_job_queue.py").read_text()
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
        engine, tables=[Base.metadata.tables[name] for name in sorted(QUEUE_TABLES)]
    )
    assert {normalize(value) for value in generated} == {normalize(value) for value in frozen}
    assert "mask_api" not in source


def test_queue_schema_contains_durability_and_scope_invariants() -> None:
    jobs = Base.metadata.tables["jobs"]
    assert {column.name for column in jobs.primary_key.columns} == {"id"}
    assert {
        "uq_job_idempotency",
        "ck_job_attempts",
        "ck_job_active_lease",
        "ck_job_market_scope",
    } <= {constraint.name for constraint in jobs.constraints}
    assert {index.name for index in jobs.indexes} == {
        "ix_job_claim",
        "ix_job_tenant_market",
    }


def test_queue_upgrade_and_downgrade_preserve_smoke_transition() -> None:
    def sql(*arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments, "--sql"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    upgrade = sql("upgrade", "0002:0003")
    downgrade = sql("downgrade", "0003:0002")
    assert "CREATE TABLE jobs" in upgrade
    assert "UNIQUE NULLS NOT DISTINCT" in upgrade
    assert "CREATE TABLE worker_heartbeats" in upgrade
    assert "INSERT INTO jobs" in upgrade
    assert "DROP TABLE infrastructure_smoke_jobs" in upgrade
    assert "CREATE TABLE infrastructure_smoke_jobs" in downgrade
    assert "INSERT INTO infrastructure_smoke_jobs" in downgrade
    assert "DROP TABLE worker_heartbeats" in downgrade
    assert "DROP TABLE jobs" in downgrade
    assert "DROP EXTENSION" not in downgrade
