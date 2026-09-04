from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from mask_api.job_queue.domain import JobStatus


class JobValue(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", from_attributes=True, hide_input_in_errors=True
    )


class EnqueueJob(JobValue):
    job_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    idempotency_key: UUID
    correlation_id: UUID
    organization_id: UUID | None = None
    market_id: UUID | None = None
    schema_version: str = Field(default="1", min_length=1, max_length=32)
    configuration_version: str = Field(default="1", min_length=1, max_length=64)
    configuration_versions: dict[str, str] = Field(default_factory=dict)
    input_reference: dict[str, JsonValue] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)
    progress_total: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_scope(self) -> "EnqueueJob":
        if self.market_id is not None and self.organization_id is None:
            raise ValueError("A market-scoped job requires an organization")
        return self


class JobEnvelope(JobValue):
    job_id: UUID
    job_type: str
    idempotency_key: UUID
    correlation_id: UUID
    organization_id: UUID | None = None
    market_id: UUID | None = None
    schema_version: str
    configuration_version: str
    configuration_versions: dict[str, str]
    input_reference: dict[str, JsonValue]
    attempt: int = Field(ge=1, le=10)
    attempt_limit: int = Field(ge=1, le=10)
    lease_token: UUID
    lease_expires_at: AwareDatetime


class JobSnapshot(JobValue):
    id: UUID
    job_type: str
    status: JobStatus
    idempotency_key: UUID
    correlation_id: UUID
    organization_id: UUID | None = None
    market_id: UUID | None = None
    schema_version: str
    configuration_version: str
    configuration_versions: dict[str, str]
    input_reference: dict[str, JsonValue]
    output_reference: dict[str, JsonValue] | None = None
    attempt_count: int
    max_attempts: int
    progress_current: int
    progress_total: int | None = None
    queued_at: datetime
    available_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None


class JobFailure(JobValue):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    retryable: bool
    jitter_fraction: float = Field(ge=0, le=1)
