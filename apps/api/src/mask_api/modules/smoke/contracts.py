from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from mask_api.job_queue.contracts import JobEnvelope
from mask_api.job_queue.domain import JobStatus


class SmokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID


class SmokeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: JobStatus
    correlation_id: UUID
    execution_count: int
    attempt_count: int
    created_at: datetime
    completed_at: datetime | None = None


__all__ = ["JobEnvelope", "SmokeRequest", "SmokeResponse"]
