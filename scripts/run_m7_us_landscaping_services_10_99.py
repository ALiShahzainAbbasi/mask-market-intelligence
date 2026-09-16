"""Run real M7 (buyer accessibility) for us_landscaping_services_10_99 from real,
manually captured evidence -- no Gemini call involved.

Matches scripts/run_m7_us_hvac_10_99.py's pattern exactly: this is the
"finalist pass" M7 full manual buyer-accessibility check called for in
docs/RESEARCH_QUALITY_PLAN.md section 4, run here for NAICS 561730
(Landscaping Services, 10-99 employees, US).

Real homepage sample (2026-09-16, via WebFetch), 5 independent (non-
franchise) landscaping businesses found via WebSearch:
- 4brotherslandscapingllc.com: homepage and /contact both returned only
  partial/truncated text (JS-heavy page WebFetch could not fully render --
  reported honestly, not guessed). No phone number or contact form was
  visible in the retrieved text (the site instead shows 'Call Now'/'Send us
  a Text' CTA buttons without a visible number). No formally named
  individual (an owner is referred to informally as "Romeo"/"Romero" only
  in customer reviews, never self-identified by the company).
- hugheslandscapinginc.com (Parker, CO): phone yes, no embedded contact form
  (links out to a separate Contact Us page instead). Names Kurt Hughes as
  Founder.
- helpmyyard.com / Father & Son Landscaping (Lake County, FL): phone yes,
  contact form yes. No individual named -- page refers only to "the family".
- landscapesbylandon.com (Carlisle, PA): phone yes, contact form yes. Names
  "Landon" (no last name given on-site) as Owner/Founder.
- naturesownlandscapes.com (Springfield, OH): phone yes, contact form yes.
  Names BJ Hamilton as Owner/Founder.
-> 3 of 5 real companies self-identify a real, named individual buyer
(hugheslandscapinginc, landscapesbylandon, naturesownlandscapes);
helpmyyard and 4brotherslandscapingllc do not.
-> 4 of 5 have at least one real, confirmed reachable channel (phone and/or
contact form); 4brotherslandscapingllc is the one exclusion, honestly
recorded as unconfirmed rather than assumed reachable, given the
WebFetch access limitation described above.

Real Meta Ad Library check (2026-09-16, via the in-session browser,
https://www.facebook.com/ads/library, no login required): an initial
broader query, "landscaping business software", returned ~52 results
dominated by irrelevant matches, so the more specific query "lawn care
business software" (US, active ads) was used instead, returning ~49 real
results. 5 real, distinct, clearly relevant advertisers were directly
observed: LawnPro Lawn Care Business Software, GorillaDesk, SnowScape,
Jobber (via a co-branded "That Lawn Dude with Jobber" ad), and Spraye.

Real Facebook-presence check (2026-09-16, via WebSearch) of 3 of the 5 real
companies: all 3 have a real, active Facebook business page (196 likes for
Hughes Landscaping, Inc.; 357 likes for Landscapes by Landon; 1,297 likes
for Natures Own Landscapes) -> 3 of 3.

median_days_to_decision and procurement_complexity_index_0_10 remain
honestly None: no real, free source for either was found, so M7 stays
UNKNOWN even with this real evidence base -- per v1's completeness rule,
ALL SIX components are required.

Usage:
    uv run python scripts/run_m7_us_landscaping_services_10_99.py
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

MARKET_ID = "us_landscaping_services_10_99"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m7_{MARKET_ID}_{_RUN_TIMESTAMP}"

SAMPLE_URLS = (
    "https://4brotherslandscapingllc.com/",
    "https://hugheslandscapinginc.com/",
    "https://helpmyyard.com/",
    "https://landscapesbylandon.com/",
    "https://www.naturesownlandscapes.com/",
)
GEOGRAPHY = "US (mixed states: unspecified/4 Brothers, CO, FL, PA, OH)"
POPULATION = (
    "Independent, non-national-franchise small landscaping business "
    "homepages found via web search, 2026-09-16"
)
EVIDENCE_REFERENCE = (
    f"Manual homepage check (SCRAPING_POLICY.md path #6), 2026-09-16, of "
    f"{', '.join(SAMPLE_URLS)}. 4brotherslandscapingllc.com returned only "
    "partial/truncated text via WebFetch (JS-heavy page) -- honestly "
    "excluded from the reachable-channel count rather than guessed."
)
BUYER_EVIDENCE_REFERENCE = (
    "Manual homepage/About-page check, 2026-09-16: hugheslandscapinginc.com/"
    "about names 'Kurt Hughes - Founder'; landscapesbylandon.com/about names "
    "'Landon - Owner/Founder' (no last name given on-site); "
    "naturesownlandscapes.com names 'BJ Hamilton - Owner/Founder'. "
    "helpmyyard.com/about names no individual (refers only to 'the family'); "
    "4brotherslandscapingllc.com names no individual on the company's own "
    "behalf (only an informal 'Romeo'/'Romero' mention in customer reviews)."
)
ADVERTISER_EVIDENCE_REFERENCE = (
    "Meta Ad Library (facebook.com/ads/library), 2026-09-16, keyword 'lawn "
    "care business software', US, active ads: ~49 real active ads found "
    "(after an initial broader query, 'landscaping business software', "
    "returned ~52 results dominated by irrelevant matches and was "
    "discarded); 5 real, distinct, clearly relevant advertisers directly "
    "observed (LawnPro Lawn Care Business Software, GorillaDesk, SnowScape, "
    "Jobber, Spraye) -- a conservative real lower bound, not an exhaustive "
    "count."
)
SOCIAL_PRESENCE_EVIDENCE_REFERENCE = (
    "WebSearch, 2026-09-16, for 3 of the 5 real companies' Facebook "
    "presence: all 3 have a real, active Facebook business page (196 likes "
    "for Hughes Landscaping, Inc./facebook.com/p/Hughes-Landscaping-"
    "61559223209098; 357 likes for Landscapes by Landon/facebook.com/"
    "landscapesbylandon; 1,297 likes for Natures Own Landscapes/facebook.com/"
    "Naturesownllc)."
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
        accounts_with_valid_reachable_channel=_metric(Decimal(4), "companies"),
        viable_channel_count=_metric(Decimal(2), "channel_types"),
        median_days_to_decision=None,
        procurement_complexity_index_0_10=None,
        active_relevant_advertisers=_metric(
            Decimal(5), "distinct_advertisers", evidence_reference=ADVERTISER_EVIDENCE_REFERENCE
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
