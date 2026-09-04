import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from workers import __main__ as worker_entrypoint

ROOT = Path(__file__).resolve().parents[2]


def test_windows_worker_runs_the_native_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = Mock()
    runtime.run.return_value = 0
    monkeypatch.setattr(worker_entrypoint, "get_worker_runtime", lambda: runtime)
    signal_handler = Mock()
    monkeypatch.setattr(worker_entrypoint.signal, "signal", signal_handler)
    assert worker_entrypoint.main() == 0
    runtime.run.assert_called_once()
    assert runtime.run.call_args.args[0].is_set() is False
    assert signal_handler.call_count >= 1


def test_worker_entrypoint_has_no_platform_or_broker_guard() -> None:
    source = (ROOT / "workers/__main__.py").read_text()
    assert "sys.platform" not in source
    assert "celery" not in source.lower()
    assert "redis" not in source.lower()


def test_no_active_container_runtime_files_or_commands() -> None:
    for relative in (
        "docker-compose.yml",
        ".dockerignore",
        "apps/api/Dockerfile",
        "apps/web/Dockerfile",
        "scripts/check-docker.mjs",
        "scripts/postgres-init.sh",
    ):
        assert not (ROOT / relative).exists()
    commands = json.loads((ROOT / "package.json").read_text())["scripts"]
    assert all("docker" not in command.lower() for command in commands.values())
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        content = path.read_text()
        assert "docker" not in content.lower()
        assert "redis" not in content.lower()
        assert "celery" not in content.lower()
        workflow = yaml.load(content, Loader=yaml.BaseLoader)
        for job in workflow["jobs"].values():
            assert "container" not in job and "services" not in job
        assert workflow["jobs"]["quality"]["runs-on"] == "windows-latest"
        live = workflow["jobs"]["integration"]
        assert "workflow_dispatch" in live["if"] and "refs/heads/main" in live["if"]
        assert live["environment"] == "integration"
        assert "windows" in live["runs-on"]
        assert "linux" not in live["runs-on"]


def test_native_secret_scan_pins_version_checks_integrity_and_redacts() -> None:
    source = (ROOT / "scripts/scan-secrets.ps1").read_text()
    assert 'version = "8.28.0"' in source
    assert "Get-FileHash" in source
    assert source.index("Get-FileHash") < source.index("Expand-Archive")
    assert "--redact" in source
    assert "--no-git --source ." in source
    assert "windows_x64.zip" in source
    assert "docker" not in source.lower()
    assert "linux" not in source.lower()
    assert not (ROOT / "scripts/scan-secrets.sh").exists()
