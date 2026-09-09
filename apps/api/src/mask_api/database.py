from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from mask_api.config import Settings, get_settings
from mask_api.persistence.base import Base as Base


def create_db_engine(settings: Settings, *, migration: bool = False) -> Engine:
    url = settings.migration_database_url if migration else settings.database_url
    if url is None:
        raise ValueError("MASK_MIGRATION_DATABASE_URL is required for migrations")
    connect_args = {
        "connect_timeout": settings.dependency_timeout_seconds,
        "application_name": "mask-migration" if migration else "mask-api-worker",
        "options": (
            f"-c search_path={settings.database_schema},public "
            f"-c statement_timeout={settings.dependency_timeout_seconds * 1000}"
        ),
    }
    if migration:
        return create_engine(
            url.get_secret_value(),
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args=connect_args,
        )
    return create_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_timeout=settings.dependency_timeout_seconds,
        connect_args=connect_args,
    )


def postgres_connection_uses_tls(connection: Connection) -> bool:
    """Inspect the client-to-endpoint TLS state, including pooled connections."""
    driver_connection = connection.connection.driver_connection
    pg_connection = getattr(driver_connection, "pgconn", None)
    return bool(pg_connection is not None and pg_connection.ssl_in_use)


@lru_cache
def get_engine() -> Engine:
    return create_db_engine(get_settings())


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
