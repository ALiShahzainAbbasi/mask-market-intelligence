from uuid import UUID

from mask_api.job_queue.contracts import EnqueueJob, JobSnapshot
from mask_api.job_queue.ports import JobQueue
from mask_api.modules.smoke.contracts import SmokeResponse


def _smoke_response(job: JobSnapshot) -> SmokeResponse:
    output = job.output_reference or {}
    execution_count = output.get("execution_count", 0)
    return SmokeResponse(
        id=job.id,
        status=job.status,
        correlation_id=job.correlation_id,
        execution_count=execution_count if isinstance(execution_count, int) else 0,
        attempt_count=job.attempt_count,
        created_at=job.queued_at,
        completed_at=job.completed_at,
    )


class JobQueueSmokeRepository:
    """Feature adapter: translate smoke requests to the shared durable queue."""

    def __init__(self, queue: JobQueue) -> None:
        self.queue = queue

    def enqueue(self, key: UUID, correlation_id: UUID) -> SmokeResponse:
        return _smoke_response(
            self.queue.enqueue(
                EnqueueJob(
                    job_type="infrastructure.smoke",
                    idempotency_key=key,
                    correlation_id=correlation_id,
                    max_attempts=3,
                    progress_total=1,
                )
            )
        )

    def get(self, job_id: UUID) -> SmokeResponse | None:
        job = self.queue.get(job_id)
        return _smoke_response(job) if job is not None else None
