from mask_api.job_queue.contracts import JobEnvelope
from mask_api.job_queue.errors import PermanentJobError
from pydantic import JsonValue


def handle_smoke(envelope: JobEnvelope) -> dict[str, JsonValue]:
    """Minimal real handler used to prove Windows queue delivery and idempotency."""
    if envelope.job_type != "infrastructure.smoke":
        raise PermanentJobError("unexpected_smoke_job_type")
    return {"execution_count": 1}
