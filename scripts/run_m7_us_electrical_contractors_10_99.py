"""Run real M7 (buyer accessibility) for us_electrical_contractors_10_99 from real,
manually captured evidence -- no Gemini call involved.

Matches scripts/run_m7_us_hvac_10_99.py's pattern exactly: this is the "finalist
pass" M7 full manual buyer-accessibility check called for in
docs/RESEARCH_QUALITY_PLAN.md section 4 ("M7 -- full manual buyer-accessibility
pass ... for every finalist, matching the depth already done for us_hvac_10_99"),
run here for NAICS 238210 (Electrical Contractors, 10-99 employees, US).

Real homepage sample (2026-09-16, via WebFetch), 5 independent (non-franchise)
electrical contractors found via WebSearch:
- family-electric.com (Concord/Kannapolis, NC): phone yes, contact form yes.
  No formally named owner/founder on-page ("Michael" appears only in customer
  testimonials, never self-identified by the company).
- sccoelectric.com (MD): phone yes, contact form yes. About page says
  "owner-operated" but never names the owner; "Shaun" appears only in
  testimonials.
- duhonelectric.com (TX): phone yes, contact form yes. Company itself names
  two real brothers, Damien and William Duhon, as the operators (no formal
  title given, but this is a direct, company-stated identification, not a
  testimonial mention).
- smalljobselectric.com (Tampa, FL): phone yes (x2 numbers), contact form
  yes. Names Nathaniel Houle as current Owner/Operator and Tom Houle as
  Founder (retired 2023).
- chapmanelectrictx.com (Spicewood, TX): phone yes, contact form yes. Names
  Alex Chapman and Kayla Chapman as Founders/Owners.
-> 3 of 5 real companies self-identify a real, named individual buyer
(duhonelectric, smalljobselectric, chapmanelectrictx); family-electric and
sccoelectric do not (testimonial-only first names, not counted).
-> 5 of 5 have both a real phone number and a real contact form.

Real Meta Ad Library check (2026-09-16, via the in-session browser,
https://www.facebook.com/ads/library, no login required): searching
"electrical contractor scheduling software" (US, active ads) returned ~8 real
active ads. 6 real, distinct advertisers were directly observed: Contractor
Foreman, Markate, Trade Books, Your Atlas (omerjamz), Contractor Plus (5
genuine B2B software vendors), plus Hireline Construction Jobs (2 real job-
recruitment ads for electrical contractor BESCO -- included honestly as a
real distinct advertiser observed, not a software vendor).

Real Facebook-presence check (2026-09-16, via WebSearch) of 3 of the 5 real
companies: all 3 have a real, active Facebook business page (132 likes for
Family Electric LLC; 909 likes for Small Jobs Electric; 100% recommend / 10
reviews for Chapman Electric) -> 3 of 3.

median_days_to_decision and procurement_complexity_index_0_10 remain
honestly None: no real, free source for either was found (both would need
real primary/sales-process research), so M7 stays UNKNOWN even with this
real evidence base -- per v1's completeness rule, ALL SIX components are
required.

Usage:
    uv run python scripts/run_m7_us_electrical_contractors_10_99.py
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

MARKET_ID = "us_electrical_contractors_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m7_{MARKET_ID}_{_RUN_TIMESTAMP}"

SAMPLE_URLS = (
    "https://family-electric.com/",
    "https://www.sccoelectric.com/",
    "https://www.duhonelectric.com/",
    "https://www.smalljobselectric.com/",
    "https://www.chapmanelectrictx.com/",
)
GEOGRAPHY = "US (mixed states: NC, MD, TX, FL)"
POPULATION = (
    "Independent, non-national-franchise small electrical contractor "
    "homepages found via web search, 2026-09-16"
)
EVIDENCE_REFERENCE = (
    f"Manual homepage check (SCRAPING_POLICY.md path #6), 2026-09-16, of "
    f"{', '.join(SAMPLE_URLS)}. All 5 reachable via WebFetch."
)
BUYER_EVIDENCE_REFERENCE = (
    "Manual homepage/About-page check, 2026-09-16: duhonelectric.com/about-us "
    "names 'Damien and William Duhon' (brothers, no formal title); "
    "smalljobselectric.com/about names 'Nathaniel Houle - Owner/Operator' "
    "(and founder Tom Houle, retired 2023); chapmanelectrictx.com/about names "
    "'Alex Chapman and Kayla Chapman - Founders/Owners'. family-electric.com "
    "and sccoelectric.com/about name no individual on the company's own "
    "behalf (only informal testimonial mentions)."
)
ADVERTISER_EVIDENCE_REFERENCE = (
    "Meta Ad Library (facebook.com/ads/library), 2026-09-16, keyword "
    "'electrical contractor scheduling software', US, active ads: ~8 real "
    "active ads found; 6 real distinct advertisers directly observed "
    "(Contractor Foreman, Markate, Trade Books, Your Atlas/omerjamz, "
    "Contractor Plus, and Hireline Construction Jobs job-recruitment ads for "
    "BESCO) -- a conservative real lower bound, not an exhaustive count."
)
SOCIAL_PRESENCE_EVIDENCE_REFERENCE = (
    "WebSearch, 2026-09-16, for 3 of the 5 real companies' Facebook presence: "
    "all 3 have a real, active Facebook business page (132 likes for Family "
    "Electric LLC/facebook.com/FAMthebetteroption; 909 likes for Small Jobs "
    "Electric/facebook.com/smalljobselectric; 100% recommend with 10 reviews "
    "for Chapman Electric/facebook.com/chapmanelectrictx)."
)


def _metric(
    value: Decimal, unit: str, *, evidence_reference: str = EVIDENCE_REFERENCE
) -> SourcedMetric:
    return SourcedMetric(
        value=value,
        provenance=MetricProvenance(
            source_id="manual_website_check",
            evidence_reference=evidence_reference,
            observation_state=ObservationState.OBSERVED,
            geography=GEOGRAPHY,
            population=POPULATION,
            period="2026-09-16",
            unit=unit,
        ),
    )


def main() -> None:
    inputs = M7Inputs(
        market_id=MARKET_ID,
        accounts_with_economic_buyer=_metric(
            Decimal(3), "companies", evidence_reference=BUYER_EVIDENCE_REFERENCE
        ),
        target_accounts=_metric(Decimal(len(SAMPLE_URLS)), "companies"),
        accounts_with_valid_reachable_channel=_metric(Decimal(5), "companies"),
        viable_channel_count=_metric(Decimal(2), "channel_types"),
        median_days_to_decision=None,
        procurement_complexity_index_0_10=None,
        active_relevant_advertisers=_metric(
            Decimal(6), "distinct_advertisers", evidence_reference=ADVERTISER_EVIDENCE_REFERENCE
        ),
        account_social_presence_rate=_metric(
            Decimal("1.0"), "share", evidence_reference=SOCIAL_PRESENCE_EVIDENCE_REFERENCE
        ),
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
