from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mask_api.config import Settings
from mask_api.database import create_db_engine, postgres_connection_uses_tls
from mask_api.persistence.targets import database_endpoint
from pydantic import SecretStr, ValidationError
from sqlalchemy.pool import NullPool

PROJECT = "abcdefghijklmnopqrst"
APP_URL = (
    "postgresql+psycopg://mask_app."
    f"{PROJECT}:private@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
)
MIGRATION_URL = (
    f"postgresql+psycopg://postgres:private@db.{PROJECT}.supabase.co:5432/"
    "postgres?sslmode=verify-full"
)


def supabase_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "database_target": "supabase",
        "database_url": APP_URL,
        "migration_database_url": MIGRATION_URL,
    }
    values.update(changes)
    return Settings(**values)


def test_supabase_target_accepts_tls_session_runtime_and_direct_migrations() -> None:
    settings = supabase_settings(hosted_integration_enabled=True)
    application = database_endpoint(settings.database_url)
    assert application.role == "mask_app"
    assert application.project_ref == PROJECT
    assert application.sslmode == "require"
    assert "private" not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", APP_URL.replace(":5432/", ":6543/")),
        ("database_url", APP_URL.replace("?sslmode=require", "")),
        ("database_url", APP_URL.replace("supabase.com", "example.invalid")),
        ("database_url", APP_URL.replace("mask_app.", "postgres.")),
        ("migration_database_url", MIGRATION_URL.replace(PROJECT, "differentprojectref")),
        ("migration_database_url", None),
    ],
)
def test_supabase_target_rejects_unsafe_or_incompatible_urls(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        supabase_settings(**{field: value})


def test_local_target_cannot_enable_hosted_integration() -> None:
    with pytest.raises(ValidationError, match="Hosted integration"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://mask_app@127.0.0.1:5432/mask",
            hosted_integration_enabled=True,
        )


def test_database_endpoint_errors_never_include_credentials() -> None:
    with pytest.raises(ValueError) as captured:
        database_endpoint(SecretStr("not-a-url:private-password"))
    assert "private-password" not in str(captured.value)


def test_runtime_engine_uses_small_recycled_pool_and_private_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock(return_value=Mock())
    monkeypatch.setattr("mask_api.database.create_engine", factory)
    settings = supabase_settings(
        database_pool_size=2,
        database_max_overflow=1,
        database_pool_recycle_seconds=180,
    )
    create_db_engine(settings)
    _, kwargs = factory.call_args
    assert kwargs["pool_size"] == 2
    assert kwargs["max_overflow"] == 1
    assert kwargs["pool_recycle"] == 180
    assert "search_path=mask,public" in kwargs["connect_args"]["options"]
    assert kwargs["connect_args"]["application_name"] == "mask-api-worker"


def test_migration_engine_uses_no_persistent_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(return_value=Mock())
    monkeypatch.setattr("mask_api.database.create_engine", factory)
    create_db_engine(supabase_settings(), migration=True)
    _, kwargs = factory.call_args
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["application_name"] == "mask-migration"


@pytest.mark.parametrize("ssl_in_use", [True, False])
def test_tls_probe_reads_the_client_connection_state(ssl_in_use: bool) -> None:
    connection = SimpleNamespace(
        connection=SimpleNamespace(
            driver_connection=SimpleNamespace(
                pgconn=SimpleNamespace(ssl_in_use=ssl_in_use),
            )
        )
    )
    assert postgres_connection_uses_tls(connection) is ssl_in_use
