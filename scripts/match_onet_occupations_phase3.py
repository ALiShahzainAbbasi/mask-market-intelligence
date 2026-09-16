"""Find real O*NET occupation matches for the 14 Phase 3 shortlist markets,
reusing the already-cached O*NET dataset (bootstrapped for us_hvac_10_99,
no new download needed). Prints candidate occupation titles/codes per
market's real NAICS label so a verified SOC code can be chosen by hand --
mirrors how 49-9021.00 was verified for HVAC, not guessed.

Usage:
    uv run python scripts/match_onet_occupations_phase3.py
"""

from __future__ import annotations

import sys
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

ONET_CACHE_DIR = ROOT / ".cache" / "onet"

MARKETS_AND_KEYWORDS = [
    (238210, "Electrical Contractors", ["electric"]),
    (561730, "Landscaping Services", ["landscap", "groundskeep"]),
    (238910, "Site Preparation Contractors", ["excavat", "grading", "construction equipment"]),
    (238290, "Other Building Equipment Contractors", ["elevator", "hvac", "mechanical"]),
    (561720, "Janitorial Services", ["janitor", "cleaner", "building cleaning"]),
    (561621, "Security Systems Services", ["security", "alarm"]),
    (811121, "Automotive Body, Paint, and Interior Repair", ["automotive body", "paint"]),
    (238990, "All Other Specialty Trade Contractors", ["construction trade", "helper"]),
    (561210, "Facilities Support Services", ["facilities", "maintenance and repair"]),
    (811192, "Car Washes", ["wash", "cleaning equipment"]),
    (541519, "Other Computer Related Services", ["computer user support", "computer systems"]),
    (812910, "Pet Care Services", ["animal care", "nonfarm animal"]),
    (561710, "Exterminating and Pest Control Services", ["pest control"]),
    (238160, "Roofing Contractors", ["roofer"]),
]


def main() -> None:
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
    descriptor = bootstrapper.ensure_dataset(ledger)
    batch = bootstrapper.import_batch(descriptor)
    print(f"Real O*NET dataset {descriptor.version}: {len(batch.occupations)} occupations\n")

    for naics, label, keywords in MARKETS_AND_KEYWORDS:
        print(f"--- NAICS {naics} {label} ---")
        matches = [
            occ
            for occ in batch.occupations
            if any(kw.lower() in occ.title.lower() for kw in keywords)
        ]
        if not matches:
            print("  NO REAL MATCH FOUND in this dataset")
        for occ in matches[:6]:
            task_count = sum(
                1 for t in batch.task_statements if t.onet_soc_code == occ.onet_soc_code
            )
            print(f"  {occ.onet_soc_code}  {occ.title}  ({task_count} real task statements)")
        print()


if __name__ == "__main__":
    main()
