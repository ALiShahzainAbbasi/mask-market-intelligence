from datetime import datetime
from typing import Protocol
from uuid import UUID

from mask_api.modules.evidence.contracts import (
    CollectionBatch,
    FetchedResource,
    PersistReceipt,
    SourcePolicy,
)


class SourcePolicyProvider(Protocol):
    def get_policy(self, policy_version_id: UUID) -> SourcePolicy | None: ...


class ResourceFetcher(Protocol):
    def fetch(
        self, url: str, policy: SourcePolicy, fetched_at: datetime, max_bytes: int
    ) -> FetchedResource: ...


class EvidenceWriter(Protocol):
    def persist(self, batch: CollectionBatch, idempotency_key: str) -> PersistReceipt: ...


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class CancellationSignal(Protocol):
    def is_cancelled(self) -> bool: ...


class JitterSource(Protocol):
    def fraction(self) -> float: ...
