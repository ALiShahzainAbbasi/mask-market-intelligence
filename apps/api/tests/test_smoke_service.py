from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mask_api.modules.smoke.contracts import SmokeResponse
from mask_api.modules.smoke.errors import SmokeNotFound, SmokeUnavailable
from mask_api.modules.smoke.ports import SmokeRepository
from mask_api.modules.smoke.services import SmokeService


def make_response() -> SmokeResponse:
    return SmokeResponse(
        id=uuid4(),
        status="queued",
        correlation_id=uuid4(),
        execution_count=0,
        attempt_count=0,
        created_at=datetime.now(UTC),
    )


def test_submit_returns_durably_enqueued_job() -> None:
    repository = Mock(spec=SmokeRepository)
    job = make_response()
    repository.enqueue.return_value = job
    key = uuid4()
    correlation_id = uuid4()
    assert SmokeService(repository).submit(key, correlation_id) == job
    repository.enqueue.assert_called_once_with(key, correlation_id)


def test_completed_idempotent_job_is_returned_without_side_effect() -> None:
    repository = Mock(spec=SmokeRepository)
    repository.enqueue.return_value = make_response().model_copy(update={"status": "succeeded"})
    result = SmokeService(repository).submit(uuid4(), uuid4())
    assert result.status == "succeeded"


def test_enqueue_failure_is_safe_and_preserves_retry_contract() -> None:
    repository = Mock(spec=SmokeRepository)
    repository.enqueue.side_effect = RuntimeError("private database payload")
    service = SmokeService(repository)
    with pytest.raises(SmokeUnavailable, match="retry same key") as failure:
        service.submit(uuid4(), uuid4())
    assert "private" not in str(failure.value)
    repository.enqueue.assert_called_once()


def test_missing_job_is_a_domain_error() -> None:
    repository = Mock(spec=SmokeRepository)
    repository.get.return_value = None
    with pytest.raises(SmokeNotFound):
        SmokeService(repository).get(uuid4())


def test_repository_failure_does_not_leak_driver_details() -> None:
    repository = Mock(spec=SmokeRepository)
    repository.get.side_effect = RuntimeError("private connection")
    with pytest.raises(SmokeUnavailable) as failure:
        SmokeService(repository).get(uuid4())
    assert "private" not in str(failure.value)
