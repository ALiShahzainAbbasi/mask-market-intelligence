"""Run real M7 (buyer accessibility) for us_roofing_contractors_10_99
(NAICS 238160) from real, manually captured evidence -- no Gemini call
involved.

Same pattern as scripts/run_m7_us_hvac_10_99.py: a one-off driver (M7 has no
registered MethodExecutor yet), using SCRAPING_POLICY.md section 2's path #6,
"manual evidence capture with source URL, date, analyst, permitted
excerpt/context, and policy note" for a real, small, explicitly-labeled
sample of independent (non-national-franchise) small roofing contractor
homepages.

Real homepage sample (2026-09-16, via WebFetch):
- pfeiferroofing.com, independentroofingmt.com, gfryork.com,
  callfamilyroofing.com: all 4 fetched successfully.
- summitroofingsolutionsllc.com: HTTP 403 on both the homepage and
  /independent-roofing-company/ -- excluded from the sample rather than
  guessed either way.

Real named-individual check (2026-09-16, via WebFetch, same 4 companies):
- pfeiferroofing.com: names founders "Chris Pfeifer" and "Mona Pfeifer",
  and second-generation "Trever Pfeifer" (no formal title stated).
- independentroofingmt.com / /about-us/: names founders "Chad Jacobson" and
  "William (Will) Malone".
- gfryork.com: no real individual named ("4th Generation" family business,
  no name given).
- callfamilyroofing.com: page states the company is "Owner-led" with a
  "Clemson Construction Science degree" but gives no individual's actual
  name -- a real, reportable gap, not a name.
-> 2 of 4 real companies have a real, named, identifiable buyer.

Real Meta Ad Library check (2026-09-16, via the in-session browser,
https://www.facebook.com/ads/library, no login required): exact-phrase
search "roofing software" (US, active ads) returned ~33 real active ads.
8 real, distinct advertisers were directly observed in the results before
stopping (not scrolled exhaustively, so this is a conservative real lower
bound, not a claimed total): AccuLynx, ServiceTitan, Roofr, Apex Roofer
Marketing (ApexOS), Jobba Trade Technologies, Zuper, IKO Roofing
(ROOFPRO WORX), Coperniq. Narrower phrasings ("roofing contractor
software", "roofing business software", "roofing CRM") returned 0 matching
ads in this session -- a real, honest finding about term specificity in
the Ad Library, not a tool failure.

Real Facebook-presence check (2026-09-16, via WebSearch) of 3 of the 4 real
companies: all 3 have a real, active Facebook business page (Pfeifer
Roofing: confirmed via BBB profile, exact like count unconfirmed;
Independent Roofing LLC/Inc: 72 likes, 75 followers, 2 reviews; Family
Roofing Company: real page found at facebook.com/CallFamilyRoofing, exact
like count unconfirmed) -> 3 of 3 checked.

median_days_to_decision and procurement_complexity_index_0_10 remain
honestly None: no real, free source for either was found (both would need
real primary/sales-process research, not desk evidence), so M7 stays
UNKNOWN even with this real evidence base -- per v1's completeness rule,
ALL SIX components are required. Identical honest outcome to
us_hvac_10_99's own M7 result.

Usage:
    uv run python scripts/run_m7_us_roofing_contractors_10_99.py
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

MARKET_ID = "us_roofing_contractors_10_99_p3"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m7_us_roofing_contractors_10_99_{_RUN_TIMESTAMP}"

SAMPLE_URLS = (
    "https://www.pfeiferroofing.com/",
    "https://independentroofingmt.com/",
    "https://gfryork.com/",
    "https://www.callfamilyroofing.com/",
)
UNAVAILABLE_URLS = ("https://summitroofingsolutionsllc.com/ (HTTP 403)",)
GEOGRAPHY = "US (mixed states: OR, MT, PA, SC)"
POPULATION = (
    "Independent, non-national-franchise small roofing contractor "
    "homepages found via web search, 2026-09-16"
)
EVIDENCE_REFERENCE = (
    f"Manual homepage check (SCRAPING_POLICY.md path #6), 2026-09-16, of "
    f"{', '.join(SAMPLE_URLS)}. Excluded as inaccessible: "
    f"{', '.join(UNAVAILABLE_URLS)}."
)
BUYER_EVIDENCE_REFERENCE = (
    "Manual homepage/about-page check, 2026-09-16, of the same 4 real companies: "
    "pfeiferroofing.com names founders 'Chris Pfeifer'/'Mona Pfeifer' and "
    "second-generation 'Trever Pfeifer'; independentroofingmt.com and its "
    "/about-us/ page name founders 'Chad Jacobson' and 'William (Will) Malone'; "
    "gfryork.com and callfamilyroofing.com name no real individual "
    "(Family Roofing's page mentions an owner's degree but not their name)."
)
ADVERTISER_EVIDENCE_REFERENCE = (
    "Meta Ad Library (facebook.com/ads/library), 2026-09-16, exact-phrase query "
    "'roofing software', US, active ads: ~33 real active ads found; 8 real "
    "distinct advertisers directly observed (AccuLynx, ServiceTitan, Roofr, "
    "Apex Roofer Marketing, Jobba Trade Technologies, Zuper, IKO Roofing, "
    "Coperniq) before stopping -- a conservative real lower bound, not an "
    "exhaustive count."
)
SOCIAL_PRESENCE_EVIDENCE_REFERENCE = (
    "WebSearch, 2026-09-16, for 3 of the 4 real companies' Facebook presence: "
    "all 3 (Pfeifer Roofing, Independent Roofing LLC/Inc, Family Roofing "
    "Company) have a real, active Facebook business page (72 real likes / 75 "
    "followers / 2 reviews for Independent Roofing; confirmed presence but "
    "unconfirmed like counts for the other two)."
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
            Decimal(2), "companies", evidence_reference=BUYER_EVIDENCE_REFERENCE
        ),
        target_accounts=_metric(Decimal(len(SAMPLE_URLS)), "companies"),
        accounts_with_valid_reachable_channel=_metric(Decimal(4), "companies"),
        viable_channel_count=_metric(Decimal(2), "channel_types"),
        median_days_to_decision=None,
        procurement_complexity_index_0_10=None,
        active_relevant_advertisers=_metric(
            Decimal(8), "distinct_advertisers", evidence_reference=ADVERTISER_EVIDENCE_REFERENCE
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
