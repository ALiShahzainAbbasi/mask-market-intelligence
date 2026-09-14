"""Run real M7 (buyer accessibility) for us_hvac_10_99 from a real, manually
captured small website sample -- no Gemini call involved.

Not a MethodExecutor yet (M7 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern.

None of this project's already-built official_data sources (Census CBP
aggregate establishment counts, SAM.gov opportunity *solicitations*,
USAspending award records) contain individual-company contact-channel
facts -- they answer different real questions, not "does this specific
business have a phone number/contact form." Gemini-grounded Search/Maps
discovery, the directive's other suggested M7 path, is blocked by
today's exhausted free-tier quota (AUTONOMOUS-042).

What this script uses instead: SCRAPING_POLICY.md section 2's path #6,
"manual evidence capture with source URL, date, analyst, permitted
excerpt/context, and policy note" -- a real, small, explicitly-labeled
sample of independent (non-national-franchise) small HVAC contractor
homepages, found via web search and checked by hand (by the analyst
running this session, 2026-09-14) for real, observable, homepage-level
facts: is a phone number shown, is there a contact form, is a named
individual buyer/decision-maker identifiable. This is NOT the
directive's ideal Gemini-grounded discovery pipeline; it is a smaller,
honest fallback that respects "never extrapolate an exact national count
from a small sample" by keeping the sample explicit and tiny.

Real sample (2026-09-14, homepage-only, via WebFetch):
- smallsolutionsheatingandairconditioning.com: phone yes, contact form
  yes, named buyer no.
- tripleotoday.com: phone yes, contact form yes, named buyer no.
- cshvac.com: phone yes, contact form yes, named buyer no.
- callmattioni.com: phone yes, contact form yes, named buyer no.
- acsystemsinc.com, trustallred.com: HTTP 403 (inaccessible to this
  session's fetch tool) -- excluded from the sample rather than guessed
  either way.

accounts_with_economic_buyer is deliberately left None, not a confident
real 0/4: the check only looked at each homepage, not an About/Team
subpage where an owner's name more often appears, so "not seen" here
does not honestly support "not identifiable" as a real finding.

Usage:
    uv run python scripts/run_m7_us_hvac_10_99.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.method_metrics import (  # noqa: E402
    M7Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m7,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402

MARKET_ID = "us_hvac_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m7_us_hvac_10_99_{_RUN_TIMESTAMP}"

SAMPLE_URLS = (
    "https://www.smallsolutionsheatingandairconditioning.com/",
    "https://www.tripleotoday.com/",
    "https://www.cshvac.com/",
    "https://www.callmattioni.com/",
)
UNAVAILABLE_URLS = (
    "https://www.acsystemsinc.com/ (HTTP 403)",
    "https://www.trustallred.com/ (HTTP 403)",
)
GEOGRAPHY = "US (mixed states: VA/WV, NY, PA)"
POPULATION = (
    "Independent, non-national-franchise small HVAC contractor homepages "
    "found via web search, 2026-09-14"
)
EVIDENCE_REFERENCE = (
    f"Manual homepage check (SCRAPING_POLICY.md path #6), 2026-09-14, of "
    f"{', '.join(SAMPLE_URLS)}. Excluded as inaccessible: "
    f"{', '.join(UNAVAILABLE_URLS)}."
)


def _metric(value: Decimal, unit: str) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="manual_website_check",
            evidence_reference=EVIDENCE_REFERENCE,
            observation_state=ObservationState.OBSERVED,
            geography=GEOGRAPHY,
            population=POPULATION,
            period="2026-09-14",
            unit=unit,
        ),
    )


def main() -> None:
    inputs = M7Inputs(
        market_id=MARKET_ID,
        accounts_with_economic_buyer=None,
        target_accounts=_metric(Decimal(len(SAMPLE_URLS)), "companies"),
        accounts_with_valid_reachable_channel=_metric(Decimal(4), "companies"),
        viable_channel_count=_metric(Decimal(2), "channel_types"),
        median_days_to_decision=None,
        procurement_complexity_index_0_10=None,
        active_relevant_advertisers=None,
        account_social_presence_rate=None,
    )

    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m7_formula = formulas.method_formulas[MethodId.M7]
    result = calculate_m7(
        formula_version=formulas.formula_version, formula=m7_formula, inputs=inputs
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "m7_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"status={result.status.value} score={result.score}")
    print(f"unknown_reasons={list(result.unknown_reasons)}")
    for item in result.breakdown:
        print(f"  {item.component}: status={item.status.value} raw_value={item.raw_value}")
    print(f"Output: {RUN_DIR}")


if __name__ == "__main__":
    main()
