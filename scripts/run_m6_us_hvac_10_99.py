"""Run M6 (search-and-buying-intent) for us_hvac_10_99 -- a deliberately
"light" real pass, confirming the honest free-mode result rather than
building new paid-keyword infrastructure.

Not a MethodExecutor yet (M6 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern.

Per docs/RESEARCH_METHODOLOGY.md and this project's own prior, separate
owner decision (see progress.txt's A07/search_intent history), M6 runs
in FREE MODE: no Google Ads (or other paid keyword-tool) credential is
approved, so weighted_monthly_volume, weighted_avg_cpc_usd,
high_intent_share, growth, switching_share, and qualified_keyword_count
have no real free source and stay honestly None -- this is a pre-
existing, deliberate constraint, not something today's Gemini quota
exhaustion caused, and not something this script works around by
approximating volume from YouTube's per-query result counts (those were
capped at 10 per query during collection, so they are not a real
prevalence measure and would misrepresent one if used as a stand-in).

Usage:
    uv run python scripts/run_m6_us_hvac_10_99.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.method_metrics import M6Inputs, calculate_m6  # noqa: E402
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402

MARKET_ID = "us_hvac_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m6_us_hvac_10_99_{_RUN_TIMESTAMP}"


def main() -> None:
    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m6_formula = formulas.method_formulas[MethodId.M6]
    inputs = M6Inputs(market_id=MARKET_ID)
    result = calculate_m6(
        formula_version=formulas.formula_version, formula=m6_formula, inputs=inputs
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "m6_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"status={result.status.value} score={result.score}")
    print(f"unknown_reasons={list(result.unknown_reasons)}")
    for item in result.breakdown:
        print(f"  {item.component}: status={item.status.value}")
    print(f"Output: {RUN_DIR}")


if __name__ == "__main__":
    main()
