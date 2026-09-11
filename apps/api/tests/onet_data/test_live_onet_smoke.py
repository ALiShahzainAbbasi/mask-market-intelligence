from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.onet_data.bootstrap import OnetBootstrapper, OnetBootstrapSettings
from mask_api.modules.onet_data.cache import LocalOnetCache
from mask_api.modules.onet_data.transport import UrllibOnetTransport
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MASK_RUN_LIVE_ONET_SMOKE") != "1"
        or os.getenv("MASK_ONET_POLICY_APPROVED") != "1",
        reason="live O*NET smoke requires explicit run and policy approval flags",
    ),
]

ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = ROOT / "outputs" / "reference_data" / "onet"


def test_live_onet_dataset_bootstrap_and_import() -> None:
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=3,
            max_documents=1,
            max_total_bytes=30_000_000,
            max_duration_seconds=120,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    bootstrap = OnetBootstrapper(
        OnetBootstrapSettings(enabled=True, policy_approved=True),
        UrllibOnetTransport(),
        LocalOnetCache(CACHE_DIR),
        now=lambda: datetime.now(UTC),
    )

    descriptor = bootstrap.ensure_dataset(ledger)
    batch = bootstrap.import_batch(descriptor)

    assert descriptor.content_length > 1_000_000
    assert len(descriptor.sha256) == 64
    assert len(batch.occupations) > 500
    assert len(batch.task_statements) > 5_000
