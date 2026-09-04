from collections.abc import Callable

from sqlalchemy import text

from mask_api.database import get_engine
from mask_api.modules.health.contracts import Readiness
from mask_api.persistence.schema import EXPECTED_SCHEMA_REVISION


def postgres_probe() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
        if not connection.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none():
            raise RuntimeError("Required migration is unavailable")
        if (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            != EXPECTED_SCHEMA_REVISION
        ):
            raise RuntimeError("Migration revision differs from application")


def check_readiness(postgres: Callable[[], None] = postgres_probe) -> Readiness:
    results = {}
    for name, probe in (("postgres", postgres),):
        try:
            probe()
            results[name] = "up"
        except Exception:
            # Do not expose database URLs, exception payloads, or credentials.
            results[name] = "down"
    return Readiness.model_validate(
        {
            "status": "ready" if all(v == "up" for v in results.values()) else "not_ready",
            "dependencies": results,
        }
    )


def readiness_report() -> Readiness:
    """Zero-argument dependency; injectable probe callables are not HTTP fields."""
    return check_readiness()
