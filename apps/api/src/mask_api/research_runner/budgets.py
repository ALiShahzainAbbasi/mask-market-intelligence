"""Shared hard-stop budget ledger for one autonomous research run."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RunBudgetLimits:
    max_requests: int
    max_documents: int
    max_total_bytes: int
    max_duration_seconds: int
    max_paid_cost_usd: Decimal

    def __post_init__(self) -> None:
        if (
            min(
                self.max_requests,
                self.max_documents,
                self.max_total_bytes,
                self.max_duration_seconds,
            )
            < 0
        ):
            raise ValueError("run budget limits cannot be negative")
        if self.max_duration_seconds == 0 or self.max_total_bytes == 0:
            raise ValueError("duration and byte limits must be positive")
        if self.max_paid_cost_usd < 0:
            raise ValueError("paid cost limit cannot be negative")


@dataclass(frozen=True)
class BudgetCharge:
    requests: int = 0
    documents: int = 0
    total_bytes: int = 0
    paid_cost_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if min(self.requests, self.documents, self.total_bytes) < 0:
            raise ValueError("budget charges cannot be negative")
        if self.paid_cost_usd < 0:
            raise ValueError("paid cost charge cannot be negative")


@dataclass(frozen=True)
class BudgetUsage:
    requests: int = 0
    documents: int = 0
    total_bytes: int = 0
    paid_cost_usd: Decimal = Decimal("0")


class BudgetLimitExceeded(RuntimeError):
    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__("research run budget limit would be exceeded")


class BudgetLedger:
    """Reserve measured work before an adapter performs it."""

    def __init__(self, limits: RunBudgetLimits, usage: BudgetUsage | None = None) -> None:
        self._limits = limits
        self._usage = usage or BudgetUsage()
        self._validate_usage(self._usage)

    @property
    def limits(self) -> RunBudgetLimits:
        return self._limits

    @property
    def usage(self) -> BudgetUsage:
        return self._usage

    def consume(self, charge: BudgetCharge) -> BudgetUsage:
        candidate = self._candidate(charge)
        self._validate_usage(candidate)
        self._usage = candidate
        return candidate

    def ensure_capacity(self, charge: BudgetCharge) -> None:
        """Fail before external work when its maximum charge cannot fit."""
        self._validate_usage(self._candidate(charge))

    def _candidate(self, charge: BudgetCharge) -> BudgetUsage:
        return BudgetUsage(
            requests=self._usage.requests + charge.requests,
            documents=self._usage.documents + charge.documents,
            total_bytes=self._usage.total_bytes + charge.total_bytes,
            paid_cost_usd=self._usage.paid_cost_usd + charge.paid_cost_usd,
        )

    def _validate_usage(self, usage: BudgetUsage) -> None:
        comparisons = (
            ("requests", usage.requests, self._limits.max_requests),
            ("documents", usage.documents, self._limits.max_documents),
            ("total_bytes", usage.total_bytes, self._limits.max_total_bytes),
            ("paid_cost_usd", usage.paid_cost_usd, self._limits.max_paid_cost_usd),
        )
        for name, value, limit in comparisons:
            if value > limit:
                raise BudgetLimitExceeded(name)
