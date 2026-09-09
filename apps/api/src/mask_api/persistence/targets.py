"""Safe database-target inspection without exposing connection credentials."""

from dataclasses import dataclass

from pydantic import SecretStr
from sqlalchemy import URL, make_url

LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1"})
SUPABASE_DIRECT_HOST_SUFFIX = ".supabase.co"
SUPABASE_POOLER_HOST_SUFFIX = ".pooler.supabase.com"
SUPABASE_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})


@dataclass(frozen=True)
class DatabaseEndpoint:
    host: str
    port: int
    database: str
    role: str
    project_ref: str | None
    sslmode: str | None
    has_password: bool


def database_endpoint(value: SecretStr) -> DatabaseEndpoint:
    """Return only non-secret connection metadata used by configuration guards."""
    try:
        url: URL = make_url(value.get_secret_value())
    except Exception:
        raise ValueError("Database URL is invalid") from None
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Database URL must use postgresql+psycopg")
    if not url.host or not url.database:
        raise ValueError("Database URL is incomplete")
    username = (url.username or "").lower()
    host = url.host.lower().rstrip(".")
    role, separator, pooler_ref = username.partition(".")
    direct_parts = host.split(".")
    direct_ref = (
        direct_parts[1]
        if len(direct_parts) >= 4
        and direct_parts[0] == "db"
        and host.endswith(SUPABASE_DIRECT_HOST_SUFFIX)
        else None
    )
    query_sslmode = url.query.get("sslmode")
    sslmode = query_sslmode if isinstance(query_sslmode, str) else None
    return DatabaseEndpoint(
        host=host,
        port=url.port or 5432,
        database=url.database,
        role=role,
        project_ref=pooler_ref if separator else direct_ref,
        sslmode=sslmode,
        has_password=bool(url.password),
    )


def is_local_endpoint(endpoint: DatabaseEndpoint) -> bool:
    return endpoint.host in LOCAL_DATABASE_HOSTS


def is_supabase_endpoint(endpoint: DatabaseEndpoint) -> bool:
    return (
        endpoint.host.endswith(SUPABASE_DIRECT_HOST_SUFFIX) and endpoint.host != "supabase.co"
    ) or endpoint.host.endswith(SUPABASE_POOLER_HOST_SUFFIX)


def validate_supabase_endpoints(application: SecretStr, migration: SecretStr) -> None:
    """Require one TLS Supabase project and separate least-privilege identities."""
    app = database_endpoint(application)
    migrator = database_endpoint(migration)
    if not is_supabase_endpoint(app) or not is_supabase_endpoint(migrator):
        raise ValueError("Supabase database URLs must use official Supabase hosts")
    if app.port != 5432 or migrator.port != 5432:
        raise ValueError("Supabase connections must use direct or session mode on port 5432")
    if app.database != "postgres" or migrator.database != "postgres":
        raise ValueError("Supabase database URLs must target the postgres database")
    if app.sslmode not in SUPABASE_SSL_MODES or migrator.sslmode not in SUPABASE_SSL_MODES:
        raise ValueError("Supabase database URLs must explicitly require TLS")
    if not app.has_password or not migrator.has_password:
        raise ValueError("Supabase database URLs require private credentials")
    if app.role != "mask_app" or migrator.role == "mask_app":
        raise ValueError("Supabase runtime and migration identities must be separate")
    if app.project_ref and migrator.project_ref and app.project_ref != migrator.project_ref:
        raise ValueError("Supabase database URLs must target the same project")
