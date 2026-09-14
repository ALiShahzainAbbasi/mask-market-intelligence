"""Run real M4 (economic pain) for us_hvac_10_99 from real, sourced evidence only.

Not a MethodExecutor yet (M4 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern, until
M4 gets a formal executor under A12.

M4 has four required raw components (mask_api.modules.method_metrics.m4
.M4_RAW_INPUT_BY_COMPONENT). Only one has real, defensible evidence right
now: `mean_m2_purchase_intent_0_4`, derived from the real M2 pain
mentions extracted in AUTONOMOUS-039
(scripts/extract_m2_pain_us_hvac_10_99.py's output). Of the 9 real
mentions, only 2 carried a real purchase_intent_0_4 value -- this is an
honest, very thin sample (n=2 of 9 mentions, 600 candidate comments) and
is labeled as such in its evidence_reference, not presented as robust.

The other three components -- annual_problem_cost_usd,
annual_existing_paid_spend_usd, verified_paid_workaround_share -- have no
real sourced evidence yet (no BLS/Census/pricing/survey evidence has been
gathered for this specific economic question). They are left as None.
Per calculate_m4()'s real, unmodified contract, this means the result
honestly resolves to UNKNOWN with unknown_reasons=
["m4.required_component_missing"] -- a real, valid finding, not
something to work around by inventing or estimating a number Gemini or
this script was not given real evidence for.

Usage:
    uv run python scripts/run_m4_us_hvac_10_99.py <m2_extraction_run_dir>
    (the outputs/runs/extract_m2_pain_us_hvac_10_99_* directory
    scripts/extract_m2_pain_us_hvac_10_99.py wrote)
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.method_metrics import (  # noqa: E402
    M4Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m4,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402

MARKET_ID = "us_hvac_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m4_us_hvac_10_99_{_RUN_TIMESTAMP}"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: run_m4_us_hvac_10_99.py <m2_extraction_run_dir>")
    m2_run_dir = Path(sys.argv[1])
    mentions = json.loads((m2_run_dir / "pain_mentions.json").read_text(encoding="utf-8"))

    with_intent = [m for m in mentions if m.get("purchase_intent_0_4") is not None]
    purchase_intent_metric: SourcedMetric | None = None
    if with_intent:
        values = [Decimal(str(m["purchase_intent_0_4"])) for m in with_intent]
        mean_value = (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        mention_ids = ", ".join(m["mention_id"][:16] for m in with_intent)
        purchase_intent_metric = SourcedMetric(
            value=mean_value,
            provenance=MetricProvenance(
                source_id="youtube_comments_gemini_extraction",
                evidence_reference=(
                    f"Mean of {len(values)} real Gemini-extracted purchase_intent_0_4 values "
                    f"from real YouTube-comment pain mentions (mention_ids: {mention_ids}). "
                    f"THIN SAMPLE: {len(values)} of {len(mentions)} total real mentions, "
                    "600 candidate comments assessed -- not a robust estimate, reportable "
                    "as directional only."
                ),
                observation_state=ObservationState.OBSERVED,
                geography="US",
                population="Anonymous YouTube commenters on HVAC dispatch/operations videos",
                period=m2_run_dir.name,
                unit="purchase_intent_0_4_scale",
            ),
        )

    inputs = M4Inputs(
        market_id=MARKET_ID,
        annual_problem_cost_usd=None,
        annual_existing_paid_spend_usd=None,
        verified_paid_workaround_share=None,
        mean_m2_purchase_intent_0_4=purchase_intent_metric,
    )

    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m4_formula = formulas.method_formulas[MethodId.M4]
    result = calculate_m4(
        formula_version=formulas.formula_version, formula=m4_formula, inputs=inputs
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "m4_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"status={result.status.value} score={result.score}")
    print(f"unknown_reasons={list(result.unknown_reasons)}")
    for item in result.breakdown:
        print(f"  {item.component}: status={item.status.value} raw_value={item.raw_value}")
    print(f"Output: {RUN_DIR}")


if __name__ == "__main__":
    main()
