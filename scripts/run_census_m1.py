"""One-off driver: run the real CensusM1Executor against us_hvac_10_99.

Not a permanent CLI entry point -- proves the first real MethodExecutor
produces a real, source-grounded M1 score end to end before it gets
registered with the ResearchRunner CLI.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))


def _load_env_file(path: Path) -> None:
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(ROOT / ".env.official.local")

from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import (  # noqa: E402
    load_formula_configuration,
    load_market_configuration,
    load_source_profile,
)
from mask_api.research_runner.execution import MethodExecutionContext  # noqa: E402
from mask_api.research_runner.executors.census_m1 import CensusM1Executor  # noqa: E402
from mask_api.research_runner.local_artifacts import LocalArtifactStore  # noqa: E402

RUN_DIR = ROOT / "outputs" / "runs" / f"m1_census_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def main() -> None:
    market = load_market_configuration(ROOT / "configs/markets/us_hvac_10_99.yaml")
    formula = load_formula_configuration(ROOT / "configs/formulas/v1.yaml")
    sources = load_source_profile(ROOT / "configs/sources/default_us_public.yaml")
    artifacts = LocalArtifactStore(RUN_DIR)

    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=100,
            max_documents=500,
            max_total_bytes=52_428_800,
            max_duration_seconds=3600,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    context = MethodExecutionContext(
        run_id="m1_census_proof",
        market=market,
        formula=formula,
        sources=sources,
        artifacts=artifacts,
        budget=ledger,
        deadline=datetime.now(UTC) + timedelta(minutes=10),
    )

    executor = CensusM1Executor()
    result = executor.execute(context)

    print(f"status={result.status.value} reason_code={result.reason_code}")
    print(json.dumps(result.payload, indent=2))
    print()
    print(f"Budget used: {ledger.usage.requests} requests, {ledger.usage.total_bytes} bytes")
    print(f"Artifacts: {RUN_DIR}")


if __name__ == "__main__":
    main()
