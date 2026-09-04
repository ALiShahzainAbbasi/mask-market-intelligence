import hashlib
import json
import math
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def request_hash(input_reference: dict[str, Any], configuration_versions: dict[str, str]) -> str:
    """Stable request identity; secrets and full evidence do not belong in references."""
    serialized = json.dumps(
        {"configuration_versions": configuration_versions, "input_reference": input_reference},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def retry_delay_seconds(
    attempt: int,
    *,
    jitter_fraction: float,
    base_seconds: int = 1,
    cap_seconds: int = 30,
) -> int:
    """Capped exponential backoff with bounded full jitter in the upper half."""
    if attempt < 1 or base_seconds < 1 or cap_seconds < 1:
        raise ValueError("Retry inputs must be positive")
    if not 0 <= jitter_fraction <= 1:
        raise ValueError("Jitter fraction must be between zero and one")
    ceiling: int = min(cap_seconds, base_seconds * (2 ** (attempt - 1)))
    return int(max(1, math.ceil(ceiling * (0.5 + 0.5 * jitter_fraction))))
