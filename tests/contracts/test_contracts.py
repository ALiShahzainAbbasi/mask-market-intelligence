import json
import subprocess
import sys
from pathlib import Path

from mask_api.config import Settings
from mask_api.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_openapi_has_no_callable_http_parameters() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        environment="test",
        enable_dev_routes=False,
    )
    schema = create_app(settings).openapi()
    assert "parameters" not in schema["paths"]["/health/ready"]["get"]
    assert schema["components"]["schemas"]["Readiness"]


def test_generated_contract_matches_backend() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/export-openapi.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    schema = json.loads((ROOT / "packages/schemas/openapi.json").read_text())
    assert "/dev/jobs/smoke" in schema["paths"]


def test_native_commands_are_local_only_and_integration_is_gated() -> None:
    commands = json.loads((ROOT / "package.json").read_text())["scripts"]
    assert commands["dev"] == "pnpm run dev:web"
    web_commands = json.loads((ROOT / "apps/web/package.json").read_text())["scripts"]
    assert commands["dev:web"] == "pnpm --filter @mask/web dev --port 3000"
    assert "--hostname 127.0.0.1" in web_commands["dev"]
    assert "--host 127.0.0.1" in commands["dev:api"]
    assert commands["dev:worker"] == "uv run python -m workers"
    assert commands["bootstrap:owner"] == "uv run python -m scripts.bootstrap_owner"
    assert commands["test:integration"].startswith("pnpm run check:services && ")
    assert "down" not in commands
    assert all("docker" not in command.lower() for command in commands.values())
    assert "NEXT_PUBLIC_" not in (ROOT / ".env.example").read_text()


def test_migration_offline_sql_contains_only_infrastructure() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "0001", "--sql"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "CREATE TABLE infrastructure_smoke_jobs" in result.stdout
    assert "CREATE TABLE markets" not in result.stdout
