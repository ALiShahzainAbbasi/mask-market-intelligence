from dataclasses import dataclass
from uuid import UUID

from mask_api.modules.smoke.contracts import SmokeResponse
from mask_api.modules.smoke.errors import SmokeNotFound, SmokeUnavailable
from mask_api.modules.smoke.ports import SmokeRepository


@dataclass(frozen=True)
class SmokeService:
    repository: SmokeRepository

    def submit(self, key: UUID, correlation_id: UUID) -> SmokeResponse:
        try:
            return self.repository.enqueue(key, correlation_id)
        except Exception:
            # Never expose driver exception payloads to adapters/loggers.
            raise SmokeUnavailable("Smoke job service unavailable; retry same key") from None

    def get(self, job_id: UUID) -> SmokeResponse:
        try:
            job = self.repository.get(job_id)
        except Exception:
            raise SmokeUnavailable("Smoke job service unavailable") from None
        if job is None:
            raise SmokeNotFound("Job not found")
        return job
