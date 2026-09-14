"""Run real M5 (competitive intelligence) for us_hvac_10_99 from real,
already-extracted evidence only -- no new Gemini calls.

Not a MethodExecutor yet (M5 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern.

A proper M5 pass needs Gemini's COMPETITOR_V1 structured extraction over a
real, targeted competitor-evidence sweep (vendor sites, review pages,
comparison content) -- that is real, necessary future work, currently
blocked by the free-tier Gemini quota exhaustion recorded in
AUTONOMOUS-042. This script does not attempt to substitute for that with
invented gap scores, pricing, or a larger competitor count: doing so
would just move Gemini's "never invent a score" constraint onto this
script instead of actually respecting it.

What real evidence already exists, without any new external call: one of
AUTONOMOUS-039's real M2 pain mentions (mention_id f87442f8...) names a
real, specific, already-in-use paid tool -- "Jobber" -- as an existing
workaround, with a real complaint and evidence_span. That is genuine,
sourced M5 evidence (a real competitor/existing-workaround is in the
market), so it is recorded as the one real
active_relevant_competitor_count input here. Nothing else in M5Inputs
(pricing, competitor_gaps, offer_similarity, verified_reference_count)
has real evidence yet, so calculate_m5() is expected to -- and correctly
should -- return UNKNOWN.

Usage:
    uv run python scripts/run_m5_us_hvac_10_99.py <m2_extraction_run_dir>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.method_metrics import (  # noqa: E402
    M5Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m5,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402

MARKET_ID = "us_hvac_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m5_us_hvac_10_99_{_RUN_TIMESTAMP}"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_m5_us_hvac_10_99.py <m2_extraction_run_dir>")
    m2_run_dir = Path(sys.argv[1])
    mentions = json.loads((m2_run_dir / "pain_mentions.json").read_text(encoding="utf-8"))

    named_competitors: set[str] = set()
    supporting_mention_ids: list[str] = []
    for mention in mentions:
        for name in mention.get("software_mentioned", ()):
            named_competitors.add(name.strip().casefold())
        if mention.get("software_mentioned"):
            supporting_mention_ids.append(mention["mention_id"][:16])

    print(f"Real mentions scanned: {len(mentions)}")
    print(f"Real named existing tools/competitors found: {sorted(named_competitors)}")

    competitor_metric: SourcedMetric | None = None
    if named_competitors:
        competitor_metric = SourcedMetric(
            value=Decimal(len(named_competitors)),
            provenance=MetricProvenance(
                source_id="youtube_comments_gemini_extraction",
                evidence_reference=(
                    "Real, distinct existing paid tools named in real M2 pain "
                    f"mentions (software_mentioned field): {sorted(named_competitors)}. "
                    f"Mention IDs: {supporting_mention_ids}. THIN SAMPLE: drawn "
                    "incidentally from 600 real YouTube comments searched for pain "
                    "signal, not a targeted competitor sweep -- does not represent "
                    "the real competitive landscape, only what was named unprompted."
                ),
                observation_state=ObservationState.OBSERVED,
                geography="US",
                population="Anonymous YouTube commenters on HVAC dispatch/operations videos",
                period=m2_run_dir.name,
                unit="distinct_named_competitors",
            ),
        )

    inputs = M5Inputs(
        market_id=MARKET_ID,
        active_relevant_competitor_count=competitor_metric,
        median_annualized_customer_price_usd=None,
        competitor_gaps=(),
        median_offer_similarity_0_1=None,
        verified_reference_count=None,
    )

    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m5_formula = formulas.method_formulas[MethodId.M5]
    result = calculate_m5(
        formula_version=formulas.formula_version, formula=m5_formula, inputs=inputs
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "m5_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"\nstatus={result.status.value} score={result.score}")
    print(f"unknown_reasons={list(result.unknown_reasons)}")
    for item in result.breakdown:
        print(f"  {item.component}: status={item.status.value} raw_value={item.raw_value}")
    print(f"Output: {RUN_DIR}")


if __name__ == "__main__":
    main()
