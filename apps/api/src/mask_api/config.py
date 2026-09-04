"""Validated server settings. Never serialize settings into API responses."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MASK_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: SecretStr
    migration_database_url: SecretStr | None = None
    dev_token: SecretStr | None = None
    enable_dev_routes: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    dependency_timeout_seconds: int = Field(default=2, ge=1, le=5)
    queue_poll_seconds: float = Field(default=1.0, ge=0.1, le=30)
    job_lease_seconds: int = Field(default=30, ge=10, le=300)
    worker_heartbeat_seconds: int = Field(default=5, ge=1, le=30)
    worker_stale_seconds: int = Field(default=15, ge=2, le=120)
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    auth_failure_limit: int = Field(default=5, ge=3, le=10)
    auth_lockout_seconds: int = Field(default=900, ge=30, le=86400)
    auth_recent_minutes: int = Field(default=15, ge=1, le=60)

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("MASK_DATABASE_URL must use postgresql+psycopg")
        if self.job_lease_seconds <= self.worker_heartbeat_seconds:
            raise ValueError("Job lease must exceed the worker heartbeat interval")
        if self.worker_stale_seconds < self.worker_heartbeat_seconds * 2:
            raise ValueError("Worker stale interval must allow at least two heartbeats")
        if self.enable_dev_routes:
            if self.environment not in {"development", "test"}:
                raise ValueError(
                    "Development routes cannot be enabled outside local/test environments"
                )
            if self.dev_token is None or len(self.dev_token.get_secret_value()) < 32:
                raise ValueError(
                    "Enabled development routes require MASK_DEV_TOKEN (32+ characters)"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
