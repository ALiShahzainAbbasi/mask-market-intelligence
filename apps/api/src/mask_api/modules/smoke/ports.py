from typing import Protocol
from uuid import UUID

from mask_api.modules.smoke.contracts import SmokeResponse


class SmokeRepository(Protocol):
    def enqueue(self, key: UUID, correlation_id: UUID) -> SmokeResponse: ...

    def get(self, job_id: UUID) -> SmokeResponse | None: ...
