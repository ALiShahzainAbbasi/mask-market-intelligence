from datetime import UTC, datetime
from uuid import uuid4

import pytest
from mask_api.job_queue.contracts import EnqueueJob, JobEnvelope, JobFailure
from mask_api.job_queue.domain import JobStatus, request_hash, retry_delay_seconds
from mask_api.job_queue.repository import build_claim_query
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql


def test_request_hash_is_canonical_and_version_sensitive() -> None:
    first = request_hash({"b": 2, "a": 1}, {"prompt": "v1", "schema": "v2"})
    reordered = request_hash({"a": 1, "b": 2}, {"schema": "v2", "prompt": "v1"})
    changed = request_hash({"a": 1, "b": 3}, {"schema": "v2", "prompt": "v1"})
    assert first == reordered
    assert len(first) == 64
    assert changed != first


@pytest.mark.parametrize(
    "attempt,jitter,expected",
    [(1, 0, 1), (2, 0, 1), (2, 1, 2), (6, 1, 30), (20, 1, 30)],
)
def test_retry_backoff_is_bounded(attempt: int, jitter: float, expected: int) -> None:
    assert retry_delay_seconds(attempt, jitter_fraction=jitter) == expected


@pytest.mark.parametrize("jitter", [-0.01, 1.01])
def test_retry_backoff_rejects_invalid_jitter(jitter: float) -> None:
    with pytest.raises(ValueError, match="Jitter"):
        retry_delay_seconds(1, jitter_fraction=jitter)


def test_market_job_requires_tenant_and_payload_is_bounded() -> None:
    with pytest.raises(ValidationError, match="requires an organization"):
        EnqueueJob(
            job_type="research.collect",
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
            market_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        EnqueueJob(
            job_type="invalid job type",
            idempotency_key=uuid4(),
            correlation_id=uuid4(),
        )


def test_envelope_rejects_untrusted_extra_or_attempt_overflow() -> None:
    now = datetime.now(UTC)
    valid = {
        "job_id": str(uuid4()),
        "job_type": "infrastructure.smoke",
        "idempotency_key": str(uuid4()),
        "correlation_id": str(uuid4()),
        "schema_version": "1",
        "configuration_version": "1",
        "configuration_versions": {},
        "input_reference": {},
        "attempt": 1,
        "attempt_limit": 3,
        "lease_token": str(uuid4()),
        "lease_expires_at": now.isoformat(),
    }
    assert JobEnvelope.model_validate(valid).attempt == 1
    with pytest.raises(ValidationError):
        JobEnvelope.model_validate({**valid, "attempt": 11})
    with pytest.raises(ValidationError):
        JobEnvelope.model_validate({**valid, "private_payload": "not allowed"})


def test_failure_code_is_safe_and_structured() -> None:
    assert JobFailure(code="source.timeout", retryable=True, jitter_fraction=0.5).retryable
    with pytest.raises(ValidationError):
        JobFailure(code="private failure details", retryable=False, jitter_fraction=0)


def test_claim_query_uses_atomic_skip_locked_and_lease_recovery() -> None:
    statement = build_claim_query(datetime.now(UTC))
    sql = str(statement.compile(dialect=postgresql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "JOBS.STATUS" in sql
    assert "JOBS.LEASE_EXPIRES_AT" in sql
    assert "JOBS.ATTEMPT_COUNT < JOBS.MAX_ATTEMPTS" in sql


def test_job_status_contract_contains_required_terminal_states() -> None:
    assert {state.value for state in JobStatus} == {
        "queued",
        "running",
        "partial",
        "succeeded",
        "failed",
        "cancelled",
    }
