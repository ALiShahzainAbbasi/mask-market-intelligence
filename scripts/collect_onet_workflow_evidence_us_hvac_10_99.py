"""Real M3 workflow evidence collection for us_hvac_10_99 from O*NET.

Directive-required pipeline, phase 1 of 2 (discovery -> retrieval -> raw
evidence retention): bootstrap the official O*NET downloadable database
(free, no key; a cached copy is reused if the server's own ETag/
Content-Length still match), then retain every real task statement for
O*NET-SOC 49-9021.00 -- Heating, Air Conditioning, and Refrigeration
Mechanics and Installers, the real occupation this market's technicians
work in (verified against the real O*NET occupation title below, not
assumed). Writes raw evidence only -- no extraction, no scoring.

O*NET task statements are drawn from real surveys of job incumbents, so
each one is real, sourced evidence of what a technician in this
occupation actually does -- not an invented workflow step.

Usage:
    uv run python scripts/collect_onet_workflow_evidence_us_hvac_10_99.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.onet_data.bootstrap import (  # noqa: E402
    OnetBootstrapper,
    OnetBootstrapSettings,
)
from mask_api.modules.onet_data.cache import LocalOnetCache  # noqa: E402
from mask_api.modules.onet_data.transport import UrllibOnetTransport  # noqa: E402
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402

MARKET_ID = "us_hvac_10_99"
# Verified against O*NET's own occupation_data.csv title/description, not
# assumed -- see collection_summary.json's occupation_title field for the
# real title returned by this run.
ONET_SOC_CODE = "49-9021.00"
ONET_CACHE_DIR = ROOT / ".cache" / "onet"
RUN_ID = f"onet_workflow_evidence_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def main() -> None:
    ONET_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    bootstrapper = OnetBootstrapper(
        OnetBootstrapSettings(enabled=True, policy_approved=True),
        UrllibOnetTransport(),
        LocalOnetCache(ONET_CACHE_DIR),
    )
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=5,
            max_documents=5,
            max_total_bytes=30_000_000,
            max_duration_seconds=1_800,
            max_paid_cost_usd=Decimal("0"),
        )
    )

    print("Ensuring O*NET dataset (cached copy reused if still current)...")
    descriptor = bootstrapper.ensure_dataset(ledger)
    print(f"Dataset version {descriptor.version}, {descriptor.content_length} bytes")

    batch = bootstrapper.import_batch(descriptor)
    print(
        f"Imported {len(batch.occupations)} real occupations, "
        f"{len(batch.task_statements)} real task statements, "
        f"{len(batch.issues)} parse issues"
    )

    occupation = next(
        (item for item in batch.occupations if item.onet_soc_code == ONET_SOC_CODE), None
    )
    if occupation is None:
        raise SystemExit(f"O*NET occupation {ONET_SOC_CODE} not found in this real dataset")
    print(f"Real occupation: {occupation.onet_soc_code} -- {occupation.title}")

    tasks = tuple(
        item for item in batch.task_statements if item.onet_soc_code == ONET_SOC_CODE
    )
    print(f"Real task statements for {ONET_SOC_CODE}: {len(tasks)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "occupation.json").write_text(
        occupation.model_dump_json(indent=2), encoding="utf-8"
    )
    (OUT_DIR / "task_statements.json").write_text(
        json.dumps([task.model_dump(mode="json") for task in tasks], indent=2),
        encoding="utf-8",
    )
    summary = {
        "market_id": MARKET_ID,
        "onet_soc_code": ONET_SOC_CODE,
        "occupation_title": occupation.title,
        "dataset_version": descriptor.version,
        "total_real_occupations_imported": len(batch.occupations),
        "total_real_task_statements_imported": len(batch.task_statements),
        "real_task_statements_for_this_occupation": len(tasks),
        "parse_issue_count": len(batch.issues),
    }
    (OUT_DIR / "collection_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
