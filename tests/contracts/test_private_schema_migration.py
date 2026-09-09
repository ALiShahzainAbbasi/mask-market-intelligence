"""Offline checks for the managed-PostgreSQL private schema boundary."""

import subprocess
import sys
from pathlib import Path

from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION

ROOT = Path(__file__).resolve().parents[2]
APPLICATION_TABLES = {
    "organizations",
    "users",
    "user_roles",
    "markets",
    "market_definition_versions",
    "market_hypotheses",
    "research_plans",
    "jobs",
    "worker_heartbeats",
    "user_credentials",
    "server_sessions",
    "identity_security_events",
}


def migration_sql(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *arguments, "--sql"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_private_schema_migration_moves_every_application_table_and_is_reversible() -> None:
    assert EXPECTED_SCHEMA_REVISION == "0006"
    upgrade = migration_sql("upgrade", "0004:0005")
    downgrade = migration_sql("downgrade", "0005:0004")
    assert "CREATE SCHEMA IF NOT EXISTS mask" in upgrade
    assert "REVOKE ALL ON SCHEMA mask FROM PUBLIC" in upgrade
    assert "GRANT USAGE ON SCHEMA mask TO mask_app" in upgrade
    assert "anon" in upgrade and "authenticated" in upgrade and "service_role" in upgrade
    for table in APPLICATION_TABLES:
        assert f'ALTER TABLE public."{table}" SET SCHEMA mask' in upgrade
        assert f'ALTER TABLE mask."{table}" SET SCHEMA public' in downgrade
    assert "DROP SCHEMA mask" in downgrade
