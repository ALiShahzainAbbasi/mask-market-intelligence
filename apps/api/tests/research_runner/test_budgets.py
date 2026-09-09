from decimal import Decimal

import pytest
from mask_api.research_runner.budgets import (
    BudgetCharge,
    BudgetLedger,
    BudgetLimitExceeded,
    BudgetUsage,
    RunBudgetLimits,
)


def limits() -> RunBudgetLimits:
    return RunBudgetLimits(
        max_requests=2,
        max_documents=3,
        max_total_bytes=10,
        max_duration_seconds=60,
        max_paid_cost_usd=Decimal("1.50"),
    )


def test_budget_ledger_accumulates_measured_usage() -> None:
    ledger = BudgetLedger(limits())

    usage = ledger.consume(
        BudgetCharge(requests=1, documents=2, total_bytes=4, paid_cost_usd=Decimal("0.25"))
    )
    usage = ledger.consume(
        BudgetCharge(requests=1, documents=1, total_bytes=6, paid_cost_usd=Decimal("1.25"))
    )

    assert usage == BudgetUsage(
        requests=2,
        documents=3,
        total_bytes=10,
        paid_cost_usd=Decimal("1.50"),
    )


@pytest.mark.parametrize(
    ("charge", "dimension"),
    [
        (BudgetCharge(requests=3), "requests"),
        (BudgetCharge(documents=4), "documents"),
        (BudgetCharge(total_bytes=11), "total_bytes"),
        (BudgetCharge(paid_cost_usd=Decimal("1.51")), "paid_cost_usd"),
    ],
)
def test_budget_stops_before_overage(charge: BudgetCharge, dimension: str) -> None:
    ledger = BudgetLedger(limits())

    with pytest.raises(BudgetLimitExceeded) as captured:
        ledger.consume(charge)

    assert captured.value.dimension == dimension
    assert ledger.usage == BudgetUsage()


def test_existing_over_limit_usage_cannot_resume() -> None:
    with pytest.raises(BudgetLimitExceeded, match="would be exceeded"):
        BudgetLedger(limits(), BudgetUsage(requests=3))


def test_invalid_budget_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="limits cannot be negative"):
        RunBudgetLimits(-1, 1, 1, 1, Decimal("0"))
    with pytest.raises(ValueError, match="must be positive"):
        RunBudgetLimits(1, 1, 0, 1, Decimal("0"))
    with pytest.raises(ValueError, match="charges cannot be negative"):
        BudgetCharge(documents=-1)
    with pytest.raises(ValueError, match="charge cannot be negative"):
        BudgetCharge(paid_cost_usd=Decimal("-0.01"))
