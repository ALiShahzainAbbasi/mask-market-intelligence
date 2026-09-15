"""Run real M7 (buyer accessibility) for us_hvac_10_99 from real, manually
captured evidence -- no Gemini call involved.

Not a MethodExecutor yet (M7 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern.

None of this project's already-built official_data sources (Census CBP
aggregate establishment counts, SAM.gov opportunity *solicitations*,
USAspending award records) contain individual-company contact-channel
facts -- they answer different real questions, not "does this specific
business have a phone number/contact form." What this script uses
instead: SCRAPING_POLICY.md section 2's path #6, "manual evidence
capture with source URL, date, analyst, permitted excerpt/context, and
policy note" -- a real, small, explicitly-labeled sample of independent
(non-national-franchise) small HVAC contractor homepages, found via web
search and checked by hand (by the analyst running this session) for
real, observable facts. This is a smaller, honest fallback that respects
"never extrapolate an exact national count from a small sample" by
keeping the sample explicit and tiny, not the directive's ideal
Gemini-grounded discovery pipeline.

Real homepage sample (2026-09-14, via WebFetch):
- smallsolutionsheatingandairconditioning.com,tripleotoday.com,
  cshvac.com, callmattioni.com: phone yes, contact form yes (4/4).
- acsystemsinc.com, trustallred.com: HTTP 403 (inaccessible to this
  session's fetch tool) -- excluded from the sample rather than guessed
  either way.

Real About/Team-page follow-up (2026-09-15, via WebFetch, the same 4
reachable companies -- deepened past the earlier homepage-only pass,
which correctly left accounts_with_economic_buyer as None rather than a
misleadingly confident 0/4 since it had not checked these pages yet):
- smallsolutionsheatingandairconditioning.com/our-company: names
  "Dylan Smallwood - President".
- tripleotoday.com/about: names "Luke Giannone - Founder".
- callmattioni.com/about-us: no real individual named -- the page's
  "Meet the team" section literally contains unfilled template content
  ("Jane Doe First"/"Jane Doe", both titled "CEO"), a real, reportable
  data-quality observation about the source itself, not a name.
- cshvac.com/about-us: no individual named.
-> 2 of 4 real companies have a real, named, identifiable buyer.

Real Meta Ad Library check (2026-09-15, via the in-session browser,
https://www.facebook.com/ads/library, no login required for a basic
keyword search): searching "HVAC dispatch software" (US, active ads)
returned ~37 real active ads. At least 6 real, distinct advertisers were
directly observed in the results before stopping (not scrolled
exhaustively, so this is a conservative real lower bound, not a claimed
total): Housecall Pro, Ascora, Joby, ServiceTitan, Notifi, Podium --
independently corroborating AUTONOMOUS-043/048's real M5 competitor
findings from a completely different real source. One ad (Joby) stated
a real, explicit price ("$89 a month, unlimited users") -- real,
citable evidence for a future M5 pricing_proof pass, not used here.

Real Facebook-presence check (2026-09-15, via WebSearch) of the same 4
real companies: all 4 have a real, active Facebook business page with
real engagement (785, 4,171, and 1,758 likes for three of them; the
fourth, Comfort Solutions HVAC/cshvac.com, has 41 real reviews at 94%
recommended) -> 4 of 4.

median_days_to_decision and procurement_complexity_index_0_10 remain
honestly None: no real, free source for either was found (both would
need real primary/sales-process research, not desk evidence), so M7
stays UNKNOWN even with this real, substantially deepened evidence base
-- per v1's completeness rule, ALL SIX components are required.

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
BUYER_EVIDENCE_REFERENCE = (
    "Manual About/Team-page check, 2026-09-15, of the same 4 real companies: "
    "smallsolutionsheatingandairconditioning.com/our-company names 'Dylan "
    "Smallwood - President'; tripleotoday.com/about names 'Luke Giannone - "
    "Founder'; callmattioni.com/about-us and cshvac.com/about-us name no real "
    "individual (Mattioni's page contains unfilled 'Jane Doe' template text)."
)
ADVERTISER_EVIDENCE_REFERENCE = (
    "Meta Ad Library (facebook.com/ads/library), 2026-09-15, keyword 'HVAC "
    "dispatch software', US, active ads: ~37 real active ads found; at least "
    "6 real distinct advertisers directly observed (Housecall Pro, Ascora, "
    "Joby, ServiceTitan, Notifi, Podium) before stopping -- a conservative "
    "real lower bound, not an exhaustive count."
)
SOCIAL_PRESENCE_EVIDENCE_REFERENCE = (
    "WebSearch, 2026-09-15, for each of the same 4 real companies' Facebook "
    "presence: all 4 have a real, active Facebook business page with real "
    "engagement (785/4,171/1,758 real likes for three; 41 real reviews at "
    "94% recommended for the fourth, Comfort Solutions HVAC)."
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
            period="2026-09-14/15",
            unit=unit,
        ),
    )


def main() -> None:
    inputs = M7Inputs(
        market_id=MARKET_ID,
        accounts_with_economic_buyer=_metric(
            Decimal(2), "companies", evidence_reference=BUYER_EVIDENCE_REFERENCE
        ),
        target_accounts=_metric(Decimal(len(SAMPLE_URLS)), "companies"),
        accounts_with_valid_reachable_channel=_metric(Decimal(4), "companies"),
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
