"""Explicit provisioned-service acceptance; never silently replaced by mocks."""

import os
import socket
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from mask_api.config import Settings, get_settings
from mask_api.database import get_engine
from mask_api.main import create_app
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION
from psycopg import connect, sql
from sqlalchemy import create_engine, make_url, text
from starlette.testclient import TestClient

from scripts.check_services import require_local_test_config

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def local_settings() -> Settings:
    settings = Settings()
    require_local_test_config(
        settings, os.environ.get("MASK_TEST_API_URL", "http://127.0.0.1:8000")
    )
    return settings


def test_database_extension_revision_and_role() -> None:
    settings = local_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == EXPECTED_SCHEMA_REVISION
        )
        assert connection.scalar(text("SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector")) == 0
        assert (
            connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"))
            is False
        )
    engine.dispose()


def test_api_worker_round_trip_and_idempotency() -> None:
    settings = local_settings()
    assert settings.dev_token is not None
    base = os.environ.get("MASK_TEST_API_URL", "http://127.0.0.1:8000")
    assert httpx.URL(base).host in {"127.0.0.1", "localhost"}
    key = str(uuid4())
    correlation = str(uuid4())
    headers = {
        "X-Dev-Token": settings.dev_token.get_secret_value(),
        "X-Correlation-ID": correlation,
    }
    with httpx.Client(base_url=base, headers=headers, timeout=10) as client:
        assert client.get("/health/ready").status_code == 200
        first = client.post("/dev/jobs/smoke", json={"idempotency_key": key})
        assert first.status_code == 202
        first_job = first.json()
        second = client.post("/dev/jobs/smoke", json={"idempotency_key": key})
        assert second.json()["id"] == first_job["id"]
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            response = client.get("/dev/jobs/" + first_job["id"])
            assert response.status_code == 200
            job = response.json()
            if job["status"] == "succeeded":
                break
            time.sleep(0.5)
        else:
            pytest.fail("Worker did not complete smoke job within 35 seconds")
        assert job["execution_count"] == 1
        assert job["correlation_id"] == correlation
        replay = client.post("/dev/jobs/smoke", json={"idempotency_key": key})
        assert replay.json()["execution_count"] == 1


def test_migrations_in_disposable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = local_settings()
    assert settings.migration_database_url is not None
    admin_url = make_url(settings.migration_database_url.get_secret_value())
    assert admin_url.host in {"127.0.0.1", "localhost"}
    test_name = "mask_it_" + uuid4().hex
    assert test_name.startswith("mask_it_") and len(test_name) == 40
    admin_dsn = admin_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_name)))
        try:
            test_url = admin_url.set(database=test_name).render_as_string(hide_password=False)
            monkeypatch.setenv("MASK_MIGRATION_DATABASE_URL", test_url)
            get_settings.cache_clear()
            config = Config(str(ROOT / "apps/api/alembic.ini"))
            command.upgrade(config, "head")
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            engine = create_engine(test_url)
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == EXPECTED_SCHEMA_REVISION
                )
            engine.dispose()
        finally:
            get_settings.cache_clear()
            # Only the exact disposable database created in this test is removed.
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(test_name)))


def test_dependency_connection_failure_is_safe_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real probes, isolated configuration fault; never stop shared host services.

    This verifies application reconnect behavior, not OS-service restart or
    worker graceful shutdown. Those remain explicit operator acceptance items.
    """
    settings = local_settings()
    variable = "MASK_DATABASE_URL"
    value = settings.database_url

    def clear_probe_state() -> None:
        if get_engine.cache_info().currsize:
            get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()

    clear_probe_state()
    try:
        with TestClient(create_app(settings)) as client, socket.socket() as unavailable:
            # Reserve a loopback port WITHOUT listening. Nothing else can claim it.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                unavailable.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            unavailable.bind(("127.0.0.1", 0))
            port = unavailable.getsockname()[1]
            assert client.get("/health/ready").status_code == 200
            broken = make_url(value.get_secret_value()).set(host="127.0.0.1", port=port)
            with monkeypatch.context() as fault:
                fault.setenv(variable, broken.render_as_string(hide_password=False))
                clear_probe_state()
                response = client.get("/health/ready")
                assert response.status_code == 503
                assert response.json()["dependencies"]["postgres"] == "down"
                assert "password" not in response.text.lower()
            clear_probe_state()
            assert client.get("/health/ready").status_code == 200
    finally:
        clear_probe_state()
