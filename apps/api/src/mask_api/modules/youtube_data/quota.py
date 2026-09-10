"""Reserve YouTube Data API quota units before a call, separately from BudgetLedger.

YouTube meters cost in quota units per endpoint (not requests, bytes, or
currency), reset daily by Google, so the shared run `BudgetLedger` cannot
express it. `search.list` costs 100 units; `commentThreads.list` costs 1 unit.
https://developers.google.com/youtube/v3/determine_quota_cost
"""

from __future__ import annotations

from dataclasses import dataclass

from mask_api.modules.youtube_data.contracts import YouTubeEndpoint

QUOTA_COST_UNITS: dict[YouTubeEndpoint, int] = {
    YouTubeEndpoint.SEARCH: 100,
    YouTubeEndpoint.COMMENT_THREADS: 1,
}


@dataclass(frozen=True)
class YouTubeQuotaLimits:
    max_quota_units: int

    def __post_init__(self) -> None:
        if self.max_quota_units < 0:
            raise ValueError("YouTube quota limit cannot be negative")


class YouTubeQuotaExceeded(RuntimeError):
    def __init__(self) -> None:
        super().__init__("YouTube Data API quota limit would be exceeded")


class YouTubeQuotaLedger:
    """Reserve quota units before a call; report exhaustion without failing the run."""

    def __init__(self, limits: YouTubeQuotaLimits, units_used: int = 0) -> None:
        if units_used < 0:
            raise ValueError("YouTube quota usage cannot be negative")
        self._limits = limits
        self._units_used = units_used

    @property
    def limits(self) -> YouTubeQuotaLimits:
        return self._limits

    @property
    def units_used(self) -> int:
        return self._units_used

    @property
    def units_remaining(self) -> int:
        return self._limits.max_quota_units - self._units_used

    def ensure_capacity(self, endpoint: YouTubeEndpoint) -> None:
        if self._units_used + QUOTA_COST_UNITS[endpoint] > self._limits.max_quota_units:
            raise YouTubeQuotaExceeded()

    def consume(self, endpoint: YouTubeEndpoint) -> int:
        cost = QUOTA_COST_UNITS[endpoint]
        candidate = self._units_used + cost
        if candidate > self._limits.max_quota_units:
            raise YouTubeQuotaExceeded()
        self._units_used = candidate
        return cost
