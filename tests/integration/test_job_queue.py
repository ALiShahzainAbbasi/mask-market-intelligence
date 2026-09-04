"""Real PostgreSQL queue acceptance; explicitly skipped without --integration."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from mask_api.config import Settings
from mask_api.job_queue.contracts import EnqueueJob, JobFailure
from mask_api.job_queue.domain import JobStatus
from mask_api.job_queue.errors import JobOwnershipLost
from mask_api.job_queue.models import JobRecord
from mask_api.job_queue.repository import SQLAlchemyJobQueue
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from scripts.check_services import require_local_test_config

pytestmark = pytest.mark.integration


@pytest.fixture
def queue() -> SQLAlchemyJobQueue:
    settings = Settings()
    require_local_test_config(settings, "http://127.0.0.1:8000")
    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield SQLAlchemyJobQueue(sessions)
    finally:
        engine.dispose()


def request(*, max_attempts: int = 3) -> EnqueueJob:
    return EnqueueJob(
        job_type="infrastructure.smoke",
        idempotency_key=uuid4(),
        correlation_id=uuid4(),
        max_attempts=max_attempts,
        progress_total=1,
    )


def test_atomic_claim_live_lease_and_idempotent_completion(
    queue: SQLAlchemyJobQueue,
) -> None:
    submitted = request()
    first = queue.enqueue(submitted)
    replay = queue.enqueue(submitted.model_copy(update={"correlation_id": uuid4()}))
    assert replay.id == first.id
    assert replay.correlation_id == first.correlation_id

    worker = uuid4()
    claimed = queue.claim(worker, 30)
    assert claimed is not None and claimed.job_id == first.id
    assert queue.claim(uuid4(), 30) is None
    assert queue.heartbeat(claimed.job_id, uuid4(), worker, 30) is False
    assert queue.heartbeat(claimed.job_id, claimed.lease_token, worker, 30) is True
    assert (
        queue.succeed(claimed.job_id, claimed.lease_token, {"execution_count": 1})
        == JobStatus.SUCCEEDED
    )
    completed = queue.get(first.id)
    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED
    assert completed.output_reference == {"execution_count": 1}
    assert completed.attempt_count == 1


def test_retry_exhaustion_is_bounded(queue: SQLAlchemyJobQueue) -> None:
    first = queue.enqueue(request(max_attempts=2))
    claimed = queue.claim(uuid4(), 30)
    assert claimed is not None and claimed.job_id == first.id
    assert (
        queue.fail(
            claimed.job_id,
            claimed.lease_token,
            JobFailure(code="source_timeout", retryable=True, jitter_fraction=0),
        )
        == JobStatus.QUEUED
    )

    with queue.sessions.begin() as session:
        session.execute(
            update(JobRecord)
            .where(JobRecord.id == first.id)
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    claimed_again = queue.claim(uuid4(), 30)
    assert claimed_again is not None and claimed_again.attempt == 2
    assert (
        queue.fail(
            claimed_again.job_id,
            claimed_again.lease_token,
            JobFailure(code="source_timeout", retryable=True, jitter_fraction=0),
        )
        == JobStatus.FAILED
    )


def test_expired_lease_is_reclaimed_and_old_owner_is_rejected(
    queue: SQLAlchemyJobQueue,
) -> None:
    submitted = queue.enqueue(request())
    first = queue.claim(uuid4(), 30)
    assert first is not None and first.job_id == submitted.id
    with queue.sessions.begin() as session:
        session.execute(
            update(JobRecord)
            .where(JobRecord.id == submitted.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    second = queue.claim(uuid4(), 30)
    assert second is not None and second.attempt == 2
    assert second.lease_token != first.lease_token
    with pytest.raises(JobOwnershipLost):
        queue.succeed(first.job_id, first.lease_token, {})
    queue.succeed(second.job_id, second.lease_token, {"execution_count": 1})


def test_cancel_and_worker_liveness_are_durable(queue: SQLAlchemyJobQueue) -> None:
    submitted = queue.enqueue(request())
    assert queue.cancel(submitted.id) == JobStatus.CANCELLED
    assert queue.claim(uuid4(), 30) is None

    worker_id = uuid4()
    started = datetime.now(UTC)
    queue.touch_worker(worker_id, started)
    assert queue.is_worker_ready(15)
    queue.stop_worker(worker_id)
    assert not queue.is_worker_ready(15)
