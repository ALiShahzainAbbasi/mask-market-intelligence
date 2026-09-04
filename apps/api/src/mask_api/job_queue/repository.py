from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from mask_api.job_queue.contracts import EnqueueJob, JobEnvelope, JobFailure, JobSnapshot
from mask_api.job_queue.domain import JobStatus, request_hash, retry_delay_seconds
from mask_api.job_queue.errors import IdempotencyConflict, JobOwnershipLost
from mask_api.job_queue.models import JobRecord, WorkerHeartbeat


def build_claim_query(now: datetime) -> Select[tuple[JobRecord]]:
    """Eligible jobs only; the repository executes this inside one transaction."""
    return (
        select(JobRecord)
        .where(
            JobRecord.attempt_count < JobRecord.max_attempts,
            or_(
                and_(JobRecord.status == JobStatus.QUEUED, JobRecord.available_at <= now),
                and_(
                    JobRecord.status == JobStatus.RUNNING,
                    JobRecord.lease_expires_at.is_not(None),
                    JobRecord.lease_expires_at <= now,
                ),
            ),
        )
        .order_by(JobRecord.available_at, JobRecord.queued_at, JobRecord.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def _database_now(session: Session) -> datetime:
    return cast(datetime, session.scalar(select(func.now())))


def _snapshot(record: JobRecord) -> JobSnapshot:
    return JobSnapshot.model_validate(record)


def _owned_job(session: Session, job_id: UUID, lease_token: UUID) -> JobRecord:
    record = session.scalar(
        select(JobRecord)
        .where(
            JobRecord.id == job_id,
            JobRecord.status == JobStatus.RUNNING,
            JobRecord.lease_token == lease_token,
        )
        .with_for_update()
    )
    if record is None:
        raise JobOwnershipLost("Job lease is no longer owned")
    return record


def _clear_lease(record: JobRecord) -> None:
    record.lease_owner = None
    record.lease_token = None
    record.lease_expires_at = None


class SQLAlchemyJobQueue:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def enqueue(self, request: EnqueueJob) -> JobSnapshot:
        fingerprint = request_hash(request.input_reference, request.configuration_versions)
        with self.sessions.begin() as session:
            session.execute(
                insert(JobRecord)
                .values(
                    id=uuid4(),
                    organization_id=request.organization_id,
                    market_id=request.market_id,
                    job_type=request.job_type,
                    status=JobStatus.QUEUED,
                    idempotency_key=request.idempotency_key,
                    schema_version=request.schema_version,
                    configuration_version=request.configuration_version,
                    configuration_versions=request.configuration_versions,
                    input_reference=request.input_reference,
                    input_hash=fingerprint,
                    max_attempts=request.max_attempts,
                    progress_total=request.progress_total,
                    correlation_id=request.correlation_id,
                )
                .on_conflict_do_nothing(constraint="uq_job_idempotency")
            )
            organization = (
                JobRecord.organization_id.is_(None)
                if request.organization_id is None
                else JobRecord.organization_id == request.organization_id
            )
            record = session.scalars(
                select(JobRecord).where(
                    organization,
                    JobRecord.job_type == request.job_type,
                    JobRecord.idempotency_key == request.idempotency_key,
                    JobRecord.configuration_version == request.configuration_version,
                )
            ).one()
            if record.input_hash != fingerprint:
                raise IdempotencyConflict("Idempotency key belongs to another request")
            return _snapshot(record)

    def get(self, job_id: UUID) -> JobSnapshot | None:
        with self.sessions() as session:
            record = session.get(JobRecord, job_id)
            return _snapshot(record) if record is not None else None

    def claim(self, worker_id: UUID, lease_seconds: int) -> JobEnvelope | None:
        with self.sessions.begin() as session:
            now = _database_now(session)
            session.execute(
                update(JobRecord)
                .where(
                    JobRecord.status == JobStatus.RUNNING,
                    JobRecord.lease_expires_at <= now,
                    JobRecord.attempt_count >= JobRecord.max_attempts,
                )
                .values(
                    status=JobStatus.FAILED,
                    completed_at=now,
                    error_code="attempts_exhausted",
                    error_message="Job attempts exhausted",
                    lease_owner=None,
                    lease_token=None,
                    lease_expires_at=None,
                )
            )
            record = session.scalar(build_claim_query(now))
            if record is None:
                return None
            token = uuid4()
            record.status = JobStatus.RUNNING
            record.attempt_count += 1
            record.started_at = record.started_at or now
            record.heartbeat_at = now
            record.lease_owner = worker_id
            record.lease_token = token
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)
            record.error_code = None
            record.error_message = None
            session.flush()
            return JobEnvelope(
                job_id=record.id,
                job_type=record.job_type,
                idempotency_key=record.idempotency_key,
                correlation_id=record.correlation_id,
                organization_id=record.organization_id,
                market_id=record.market_id,
                schema_version=record.schema_version,
                configuration_version=record.configuration_version,
                configuration_versions=record.configuration_versions,
                input_reference=record.input_reference,
                attempt=record.attempt_count,
                attempt_limit=record.max_attempts,
                lease_token=token,
                lease_expires_at=record.lease_expires_at,
            )

    def heartbeat(
        self, job_id: UUID, lease_token: UUID, worker_id: UUID, lease_seconds: int
    ) -> bool:
        with self.sessions.begin() as session:
            now = _database_now(session)
            result = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status == JobStatus.RUNNING,
                    JobRecord.lease_token == lease_token,
                    JobRecord.lease_owner == worker_id,
                    JobRecord.cancel_requested_at.is_(None),
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                .returning(JobRecord.id)
            )
            return result.scalar_one_or_none() is not None

    def succeed(
        self, job_id: UUID, lease_token: UUID, output_reference: dict[str, JsonValue]
    ) -> JobStatus:
        with self.sessions.begin() as session:
            now = _database_now(session)
            record = _owned_job(session, job_id, lease_token)
            record.completed_at = now
            if record.cancel_requested_at is not None:
                record.status = JobStatus.CANCELLED
            else:
                record.status = JobStatus.SUCCEEDED
                record.output_reference = output_reference
                if record.progress_total is not None:
                    record.progress_current = record.progress_total
            _clear_lease(record)
            return record.status

    def fail(self, job_id: UUID, lease_token: UUID, failure: JobFailure) -> JobStatus:
        with self.sessions.begin() as session:
            now = _database_now(session)
            record = _owned_job(session, job_id, lease_token)
            record.error_code = failure.code
            record.error_message = "Job handler failed"
            if record.cancel_requested_at is not None:
                record.status = JobStatus.CANCELLED
                record.completed_at = now
            elif failure.retryable and record.attempt_count < record.max_attempts:
                record.status = JobStatus.QUEUED
                record.available_at = now + timedelta(
                    seconds=retry_delay_seconds(
                        record.attempt_count, jitter_fraction=failure.jitter_fraction
                    )
                )
            else:
                record.status = JobStatus.FAILED
                record.completed_at = now
            _clear_lease(record)
            return record.status

    def cancel(self, job_id: UUID) -> JobStatus | None:
        with self.sessions.begin() as session:
            now = _database_now(session)
            record = session.scalar(
                select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            )
            if record is None:
                return None
            if record.status == JobStatus.QUEUED:
                record.status = JobStatus.CANCELLED
                record.completed_at = now
            elif record.status == JobStatus.RUNNING:
                record.cancel_requested_at = now
            return record.status

    def touch_worker(self, worker_id: UUID, started_at: datetime) -> None:
        with self.sessions.begin() as session:
            now = _database_now(session)
            session.execute(
                insert(WorkerHeartbeat)
                .values(
                    worker_id=worker_id,
                    started_at=started_at,
                    heartbeat_at=now,
                    stopped_at=None,
                )
                .on_conflict_do_update(
                    index_elements=[WorkerHeartbeat.worker_id],
                    set_={"heartbeat_at": now, "stopped_at": None},
                )
            )

    def stop_worker(self, worker_id: UUID) -> None:
        with self.sessions.begin() as session:
            now = _database_now(session)
            session.execute(
                update(WorkerHeartbeat)
                .where(WorkerHeartbeat.worker_id == worker_id)
                .values(heartbeat_at=now, stopped_at=now)
            )

    def is_worker_ready(self, stale_after_seconds: int) -> bool:
        with self.sessions() as session:
            now = _database_now(session)
            return bool(
                session.scalar(
                    select(func.count())
                    .select_from(WorkerHeartbeat)
                    .where(
                        WorkerHeartbeat.stopped_at.is_(None),
                        WorkerHeartbeat.heartbeat_at
                        >= now - timedelta(seconds=stale_after_seconds),
                    )
                )
            )
