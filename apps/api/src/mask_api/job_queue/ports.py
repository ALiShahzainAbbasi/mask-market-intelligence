from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from mask_api.job_queue.contracts import EnqueueJob, JobEnvelope, JobFailure, JobSnapshot
from mask_api.job_queue.domain import JobStatus


class JobQueue(Protocol):
    def enqueue(self, request: EnqueueJob) -> JobSnapshot: ...

    def get(self, job_id: UUID) -> JobSnapshot | None: ...

    def claim(self, worker_id: UUID, lease_seconds: int) -> JobEnvelope | None: ...

    def heartbeat(
        self, job_id: UUID, lease_token: UUID, worker_id: UUID, lease_seconds: int
    ) -> bool: ...

    def succeed(
        self, job_id: UUID, lease_token: UUID, output_reference: dict[str, JsonValue]
    ) -> JobStatus: ...

    def fail(self, job_id: UUID, lease_token: UUID, failure: JobFailure) -> JobStatus: ...

    def cancel(self, job_id: UUID) -> JobStatus | None: ...

    def touch_worker(self, worker_id: UUID, started_at: datetime) -> None: ...

    def stop_worker(self, worker_id: UUID) -> None: ...

    def is_worker_ready(self, stale_after_seconds: int) -> bool: ...
