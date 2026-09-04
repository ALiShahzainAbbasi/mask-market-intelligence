import logging
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.job_queue.contracts import JobEnvelope
from mask_api.job_queue.domain import JobStatus
from mask_api.job_queue.errors import RetryableJobError
from mask_api.job_queue.ports import JobQueue
from pydantic import JsonValue

from workers.runtime import JobHandler, WorkerRuntime
from workers.smoke_handler import handle_smoke


def envelope(job_type: str = "infrastructure.smoke") -> JobEnvelope:
    return JobEnvelope(
        job_id=uuid4(),
        job_type=job_type,
        idempotency_key=uuid4(),
        correlation_id=uuid4(),
        schema_version="1",
        configuration_version="1",
        configuration_versions={},
        input_reference={},
        attempt=1,
        attempt_limit=3,
        lease_token=uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )


def runtime(queue: Mock, handlers: dict[str, JobHandler] | None = None) -> WorkerRuntime:
    return WorkerRuntime(
        queue,
        handlers or {"infrastructure.smoke": handle_smoke},
        lease_seconds=30,
        heartbeat_seconds=5,
        poll_seconds=0.1,
        worker_id=uuid4(),
        jitter=lambda: 0.25,
    )


def test_successful_job_is_completed_once_by_lease() -> None:
    queue = Mock(spec=JobQueue)
    claimed = envelope()
    queue.claim.return_value = claimed
    queue.succeed.return_value = JobStatus.SUCCEEDED
    assert runtime(queue).run_once()
    queue.succeed.assert_called_once_with(
        claimed.job_id, claimed.lease_token, {"execution_count": 1}
    )
    queue.fail.assert_not_called()


def test_retryable_handler_failure_is_scheduled_without_error_payload() -> None:
    queue = Mock(spec=JobQueue)
    claimed = envelope("research.collect")
    queue.claim.return_value = claimed
    queue.fail.return_value = JobStatus.QUEUED

    def fail(_: JobEnvelope) -> dict[str, JsonValue]:
        raise RetryableJobError("source_timeout")

    assert runtime(queue, {"research.collect": fail}).run_once()
    failure = queue.fail.call_args.args[2]
    assert failure.code == "source_timeout"
    assert failure.retryable is True
    assert failure.jitter_fraction == 0.25
    queue.succeed.assert_not_called()


def test_unknown_handler_fails_permanently() -> None:
    queue = Mock(spec=JobQueue)
    claimed = envelope("unknown.job")
    queue.claim.return_value = claimed
    queue.fail.return_value = JobStatus.FAILED
    assert runtime(queue).run_once()
    failure = queue.fail.call_args.args[2]
    assert failure.code == "unknown_job_type"
    assert failure.retryable is False


def test_empty_queue_does_not_report_work() -> None:
    queue = Mock(spec=JobQueue)
    queue.claim.return_value = None
    assert runtime(queue).run_once() is False


def test_run_records_start_and_bounded_stop() -> None:
    queue = Mock(spec=JobQueue)
    queue.claim.return_value = None
    stop = Event()
    queue.touch_worker.side_effect = lambda *_: stop.set()
    worker = runtime(queue)
    assert worker.run(stop) == 0
    queue.touch_worker.assert_called_once_with(worker.worker_id, worker.started_at)
    queue.stop_worker.assert_called_once_with(worker.worker_id)


def test_unexpected_handler_details_are_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = Mock(spec=JobQueue)
    queue.claim.return_value = envelope("research.collect")
    queue.fail.return_value = JobStatus.QUEUED

    def fail(_: JobEnvelope) -> dict[str, JsonValue]:
        raise RuntimeError("private-secret-payload")

    logger = logging.getLogger("worker-test")
    worker = WorkerRuntime(
        queue,
        {"research.collect": fail},
        lease_seconds=30,
        heartbeat_seconds=5,
        poll_seconds=0.1,
        logger=logger,
        jitter=lambda: 0,
    )
    worker.run_once()
    assert "private-secret-payload" not in caplog.text
