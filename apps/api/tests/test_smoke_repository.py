from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from mask_api.job_queue.contracts import JobSnapshot
from mask_api.job_queue.domain import JobStatus
from mask_api.job_queue.ports import JobQueue
from mask_api.modules.smoke.repository import JobQueueSmokeRepository


def snapshot(status: JobStatus = JobStatus.QUEUED) -> JobSnapshot:
    now = datetime.now(UTC)
    return JobSnapshot(
        id=uuid4(),
        job_type="infrastructure.smoke",
        status=status,
        idempotency_key=uuid4(),
        correlation_id=uuid4(),
        schema_version="1",
        configuration_version="1",
        configuration_versions={},
        input_reference={},
        output_reference={"execution_count": 1} if status == JobStatus.SUCCEEDED else None,
        attempt_count=1 if status == JobStatus.SUCCEEDED else 0,
        max_attempts=3,
        progress_current=1 if status == JobStatus.SUCCEEDED else 0,
        progress_total=1,
        queued_at=now,
        available_at=now,
        completed_at=now if status == JobStatus.SUCCEEDED else None,
    )


def test_smoke_adapter_enqueues_the_shared_job_contract() -> None:
    queue = Mock(spec=JobQueue)
    stored = snapshot()
    queue.enqueue.return_value = stored
    key = uuid4()
    correlation = uuid4()
    response = JobQueueSmokeRepository(queue).enqueue(key, correlation)
    request = queue.enqueue.call_args.args[0]
    assert request.job_type == "infrastructure.smoke"
    assert request.idempotency_key == key
    assert request.correlation_id == correlation
    assert request.progress_total == 1
    assert response.id == stored.id
    assert response.execution_count == 0


def test_smoke_adapter_reads_worker_output_without_inventing_execution() -> None:
    queue = Mock(spec=JobQueue)
    stored = snapshot(JobStatus.SUCCEEDED)
    queue.get.return_value = stored
    response = JobQueueSmokeRepository(queue).get(stored.id)
    assert response is not None
    assert response.execution_count == 1
    assert response.attempt_count == 1


def test_smoke_adapter_preserves_missing_job() -> None:
    queue = Mock(spec=JobQueue)
    queue.get.return_value = None
    assert JobQueueSmokeRepository(queue).get(uuid4()) is None
