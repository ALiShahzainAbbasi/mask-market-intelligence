from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from mask_api.job_queue.contracts import JobEnvelope
from mask_api.job_queue.errors import PermanentJobError

from workers.smoke_handler import handle_smoke


def envelope(job_type: str) -> JobEnvelope:
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


def test_smoke_handler_returns_a_bounded_result() -> None:
    assert handle_smoke(envelope("infrastructure.smoke")) == {"execution_count": 1}


def test_smoke_handler_rejects_another_job_type() -> None:
    with pytest.raises(PermanentJobError, match="unexpected_smoke_job_type"):
        handle_smoke(envelope("research.collect"))
