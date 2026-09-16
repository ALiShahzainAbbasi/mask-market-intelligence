"""Run real M7 (buyer accessibility) for us_pest_control_10_99 (NAICS 561710)
from real, manually captured evidence -- no Gemini call involved.

Same pattern as scripts/run_m7_us_hvac_10_99.py: a one-off driver (M7 has no
registered MethodExecutor yet), using SCRAPING_POLICY.md section 2's path #6,
"manual evidence capture with source URL, date, analyst, permitted
excerpt/context, and policy note" for a real, small, explicitly-labeled
sample of independent (non-national-franchise) small pest control business
homepages.

Real homepage sample (2026-09-16, via WebFetch):
- rottler.com, franklinpestsolutions.com (redirects to franklin.us),
  carolinapest.com, villageexterminating.com, familyhomepestcontrol.com:
  all 5 fetched successfully.
- familypestcontrol.com (San Antonio): HTTP 403 on both the homepage and
  /about-us/ -- excluded from the sample rather than guessed either way.

Real named-individual check (2026-09-16, via WebFetch, same 5 companies):
- rottler.com/about/: names founder "Fred Rottler" (1956) and current
  co-owners "Mike Rottler" and "Gary Rottler" (no formal title stated).
- familyhomepestcontrol.com: names founder "Jon Neff" (1999) and current
  operators "Jay Neff" and "Joe Neff" (no formal title stated).
- franklin.us, carolinapest.com, villageexterminating.com: no real
  individual named on the fetched pages.
-> 2 of 5 real companies have a real, named, identifiable buyer.

Real Meta Ad Library check (2026-09-16, via the in-session browser,
https://www.facebook.com/ads/library, no login required): exact-phrase
search "pest control software" (US, active ads) returned ~30 real active
ads. 6 real, distinct advertisers were directly observed in the results
before stopping (not scrolled exhaustively, so this is a conservative real
lower bound, not a claimed total): GorillaDesk, FieldRoutes (A ServiceTitan
Product), Fieldy Technologies, Rupipest, PestPac by WorkWave, Briostack.
Narrower phrasings ("pest control business software" as originally
suggested) intermittently returned unrelated results in this session (a
real UI/search-matching quirk of the Ad Library tool) before the exact
phrase above reliably returned on-topic results.

Real Facebook-presence check (2026-09-16, via WebSearch) of 3 of the 5 real
companies: all 3 have a real, active Facebook business page (Rottler Pest
Solutions: 5,715 likes, 98% recommended, 1,081 reviews; Family Home Pest
Control: a small local page, 37/42 likes per two search snippets; Carolina
Pest Management: company confirms FB/Instagram/Twitter presence and a
related branch-location page was found, but the exact like count for the
main page could not be confirmed via WebSearch) -> 3 of 3 checked.

median_days_to_decision and procurement_complexity_index_0_10 remain
honestly None: no real, free source for either was found (both would need
real primary/sales-process research, not desk evidence), so M7 stays
UNKNOWN even with this real evidence base -- per v1's completeness rule,
ALL SIX components are required. Identical honest outcome to
us_hvac_10_99's own M7 result.

Usage:
    uv run python scripts/run_m7_us_pest_control_10_99.py
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

MARKET_ID = "us_pest_control_10_99_p3"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m7_us_pest_control_10_99_{_RUN_TIMESTAMP}"

SAMPLE_URLS = (
    "https://www.rottler.com/",
    "https://www.franklinpestsolutions.com/ (redirects to https://franklin.us/)",
    "https://www.carolinapest.com/",
    "https://www.villageexterminating.com/",
    "https://familyhomepestcontrol.com/",
)
UNAVAILABLE_URLS = ("https://www.familypestcontrol.com/ (HTTP 403)",)
GEOGRAPHY = "US (mixed states: MO, PA/NJ, NC, NY/NJ, OR)"
POPULATION = (
    "Independent, non-national-franchise small pest control business "
    "homepages found via web search, 2026-09-16"
)
EVIDENCE_REFERENCE = (
    f"Manual homepage check (SCRAPING_POLICY.md path #6), 2026-09-16, of "
    f"{', '.join(SAMPLE_URLS)}. Excluded as inaccessible: "
    f"{', '.join(UNAVAILABLE_URLS)}."
)
BUYER_EVIDENCE_REFERENCE = (
    "Manual homepage/about-page check, 2026-09-16, of the same 5 real companies: "
    "rottler.com/about/ names founder 'Fred Rottler' and current co-owners "
    "'Mike Rottler'/'Gary Rottler'; familyhomepestcontrol.com names founder "
    "'Jon Neff' and current operators 'Jay Neff'/'Joe Neff'; franklin.us, "
    "carolinapest.com, and villageexterminating.com name no real individual."
)
ADVERTISER_EVIDENCE_REFERENCE = (
    "Meta Ad Library (facebook.com/ads/library), 2026-09-16, exact-phrase query "
    "'pest control software', US, active ads: ~30 real active ads found; 6 real "
    "distinct advertisers directly observed (GorillaDesk, FieldRoutes/A "
    "ServiceTitan Product, Fieldy Technologies, Rupipest, PestPac by WorkWave, "
    "Briostack) before stopping -- a conservative real lower bound, not an "
    "exhaustive count."
)
SOCIAL_PRESENCE_EVIDENCE_REFERENCE = (
    "WebSearch, 2026-09-16, for 3 of the 5 real companies' Facebook presence: "
    "all 3 (Rottler Pest Solutions, Family Home Pest Control, Carolina Pest "
    "Management) have a real, active Facebook business page (5,715 real likes "
    "for Rottler; a small local page for Family Home Pest Control; confirmed "
    "FB/Instagram/Twitter presence for Carolina Pest, exact like count "
    "unconfirmed)."
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
