from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from mask_api.config import Settings, get_settings
from mask_api.persistence.base import Base as Base


def create_db_engine(settings: Settings, *, migration: bool = False) -> Engine:
    url = settings.migration_database_url if migration else settings.database_url
    if url is None:
        raise ValueError("MASK_MIGRATION_DATABASE_URL is required for migrations")
    return create_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=settings.dependency_timeout_seconds,
        connect_args={
            "connect_timeout": settings.dependency_timeout_seconds,
            "options": f"-c statement_timeout={settings.dependency_timeout_seconds * 1000}",
        },
    )


@lru_cache
def get_engine() -> Engine:
    return create_db_engine(get_settings())


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
