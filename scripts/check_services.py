"""Read-only native integration preflight. Never prints configuration or driver errors."""

import json
import os
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
from mask_api.config import Settings, get_settings
from mask_api.health import check_readiness
from mask_api.job_queue.wiring import get_job_queue
from sqlalchemy import make_url

LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def require_local_test_config(settings: Settings, api_url: str) -> None:
    """Integration can mutate synthetic state; never target an arbitrary remote."""
    migration = settings.migration_database_url
    api = urlsplit(api_url)
    if (
        settings.environment != "development"
        or not settings.enable_dev_routes
        or settings.dev_token is None
        or migration is None
        or make_url(settings.database_url.get_secret_value()).host not in LOCAL_HOSTS
        or make_url(migration.get_secret_value()).host not in LOCAL_HOSTS
        or api.scheme not in {"http", "https"}
        or api.hostname not in LOCAL_HOSTS
        or api.username is not None
        or api.password is not None
        or api.path not in {"", "/"}
        or api.query
        or api.fragment
    ):
        raise ValueError("Integration requires explicit local development configuration")


def api_ready(base_url: str) -> bool:
    # Do not follow redirects or proxy a local test request through ambient settings.
    with httpx.Client(timeout=6, trust_env=False, follow_redirects=False) as client:
        response = client.get(base_url.rstrip("/") + "/health/ready")
        return response.status_code == 200 and response.json().get("status") == "ready"


def worker_ready(stale_after_seconds: int) -> bool:
    return get_job_queue().is_worker_ready(stale_after_seconds)


def safe_check(check: Callable[[], bool]) -> bool:
    try:
        return check()
    except Exception:
        return False


def main() -> int:
    try:
        settings = get_settings()
        api_url = os.environ.get("MASK_TEST_API_URL", "http://127.0.0.1:8000")
        require_local_test_config(settings, api_url)
    except Exception:
        print(
            "Service preflight BLOCKED: configure local development URLs, migration identity, "
            "and the protected smoke harness. See docs/DEVELOPMENT.md. No tests were run."
        )
        return 1

    report = check_readiness()
    statuses: dict[str, str] = {name: status for name, status in report.dependencies.items()}
    statuses["api"] = "up" if safe_check(lambda: api_ready(api_url)) else "down"
    # PostgreSQL is the queue source of truth; do not probe a worker if it is down.
    statuses["worker"] = (
        "up"
        if statuses["postgres"] == "up"
        and safe_check(lambda: worker_ready(settings.worker_stale_seconds))
        else "down"
    )
    print(json.dumps({"service_preflight": statuses}))
    if any(status != "up" for status in statuses.values()):
        print(
            "Service preflight BLOCKED: native services are unavailable or not ready. "
            "Integration tests were NOT run. See docs/DEVELOPMENT.md."
        )
        return 1
    print("Service preflight PASS; run the real integration suite to verify behavior.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
