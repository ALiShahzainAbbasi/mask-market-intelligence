"""Stage B, Wave A: real, free, national Census CBP pre-screen across a
real candidate-market list -- the cheap first cut described to the owner
before any per-market Gemini/search evidence gathering starts.

Not a MethodExecutor -- a one-off driver, matching
scripts/run_census_m1.py's proof-of-real-wiring pattern, reusing
mask_api.modules.official_data.census_cbp_request/OfficialApiAdapter
completely unchanged.

Candidate list rationale (real NAICS 2017 6-digit codes, not invented):
drawn from the Specialty Trade Contractors (238), Repair and Maintenance
(811), and Other Services (561/812) subsectors -- the same shape as
us_hvac_10_99 (238220): small-business-dominated, appointment/dispatch-
driven field or shop service work. Excludes anything the owner's real
MASK AI Capability Registry flags as a weak fit (deep regulated
enterprise/licensed-professional verticals: medical, legal, financial,
childcare) per its own "capability boundaries" guardrail (section 9).
us_hvac_10_99 itself (238220) is included as a real, already-verified
baseline row to sanity-check this script's math against AUTONOMOUS-030s'
known real M1 result before trusting it on new candidates.

This is ONLY the M1-light slice of the real, full DiscoveryPreScreenScore
(30% M1-light + 25% M2-light + 20% M4-light + 15% M7-light + 10%
M9-light per the owner's directive) -- the free, fast first cut (Wave A)
to narrow ~40 candidates before spending any real Gemini/search budget
on Wave B's multi-source pass over the survivors. It is NOT a final
market score and is not the approved M1 formula (no economic_capacity/
target_band_match sub-scoring here, just business_count/concentration/
growth, matching the state-regional-discovery script's own precedent for
a pre-score, not an official one).

Usage:
    uv run python scripts/discover_candidate_markets_wave_a.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.official_data.errors import OfficialDataError  # noqa: E402
from mask_api.modules.official_data.requests import census_cbp_request  # noqa: E402
from mask_api.modules.official_data.transport import (  # noqa: E402
    OfficialApiAdapter,
    OfficialApiSettings,
    OfficialTransportError,
    UrllibOfficialTransport,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import load_source_profile  # noqa: E402
from pydantic import SecretStr  # noqa: E402

CURRENT_YEAR = 2022  # matches AUTONOMOUS-030s' verified-working real M1 vintage
BASELINE_YEAR = 2017  # 5-year CAGR, matching M1's own real convention
BANDS = {"10_19": "230", "20_49": "241", "50_99": "242", "all_sizes": "001"}
TARGET_BANDS = ("10_19", "20_49", "50_99")
MIN_ESTABLISHMENTS = 300  # same default as the state-regional pre-screen
MIN_NATIONAL_SHARE_OF_BAND = None  # intentionally unused at the national level

CANDIDATES: tuple[tuple[int, str], ...] = (
    (238220, "HVAC Contractors (real, already-scored baseline)"),
    (238210, "Electrical Contractors"),
    (238160, "Roofing Contractors"),
    (238130, "Framing Contractors"),
    (238140, "Masonry Contractors"),
    (238150, "Glass and Glazing Contractors"),
    (238190, "Other Foundation, Structure, and Building Exterior Contractors"),
    (238290, "Other Building Equipment Contractors"),
    (238320, "Painting and Wall Covering Contractors"),
    (238330, "Flooring Contractors"),
    (238340, "Tile and Terrazzo Contractors"),
    (238350, "Finish Carpentry Contractors"),
    (238910, "Site Preparation Contractors"),
    (238990, "All Other Specialty Trade Contractors"),
    (236118, "Residential Remodelers"),
    (811111, "General Automotive Repair"),
    (811118, "Other Automotive Mechanical and Electrical Repair and Maintenance"),
    (811121, "Automotive Body, Paint, and Interior Repair and Maintenance"),
    (811192, "Car Washes"),
    (811211, "Consumer Electronics Repair and Maintenance"),
    (811310, "Commercial and Industrial Machinery and Equipment Repair and Maintenance"),
    (811411, "Home and Garden Equipment Repair and Maintenance"),
    (811412, "Appliance Repair and Maintenance"),
    (811420, "Reupholstery and Furniture Repair"),
    (811430, "Footwear and Leather Goods Repair"),
    (811490, "Other Personal and Household Goods Repair and Maintenance"),
    (561210, "Facilities Support Services"),
    (561621, "Security Systems Services (except Locksmiths)"),
    (561622, "Locksmiths"),
    (561710, "Exterminating and Pest Control Services"),
    (561720, "Janitorial Services"),
    (561730, "Landscaping Services"),
    (561740, "Carpet and Upholstery Cleaning Services"),
    (561790, "Other Services to Buildings and Dwellings"),
    (484210, "Used Household and Office Goods Moving"),
    (812320, "Drycleaning and Laundry Services (except Coin-Operated)"),
    (812910, "Pet Care Services (except Veterinary)"),
    (812112, "Beauty Salons"),
    (812113, "Nail Salons"),
    (541519, "Other Computer Related Services"),
)

RUN_ID = f"discover_candidate_markets_wave_a_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _fetch_band(
    adapter: OfficialApiAdapter,
    ledger: BudgetLedger,
    api_key: str,
    naics: int,
    year: int,
    code: str,
) -> dict[str, Decimal]:
    """Returns {metric: value} for one national (us:*) NAICS/year/band -- a
    single real row since geography is the national total, not a wildcard
    over many rows like the state-level regional script."""
    request = census_cbp_request(
        year=year, naics=naics, employment_size=code, geography="us:*", api_key=SecretStr(api_key)
    )
    result = adapter.fetch(request, ledger)
    values: dict[str, Decimal] = {}
    for obs in result.batch.observations:
        values[obs.metric] = obs.value
    return values


def main() -> None:
    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_CENSUS_API_KEY")
    if not api_key:
        raise SystemExit("MASK_CENSUS_API_KEY is not configured; cannot run real pre-screen.")

    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=len(CANDIDATES) * 8 + 20,
            max_documents=len(CANDIDATES) * 8 + 20,
            max_total_bytes=50_000_000,
            max_duration_seconds=3_600,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    adapter = OfficialApiAdapter(
        "census_cbp",
        profile.sources["census_cbp"].model_copy(update={"operational_status": "available"}),
        OfficialApiSettings(enabled=True, policy_approved=True),
        UrllibOfficialTransport(),
        user_agent="MASK-AI-Market-Research/0.1",
    )

    results: list[dict[str, object]] = []
    for naics, label in CANDIDATES:
        current: dict[str, dict[str, Decimal]] = {}
        baseline_target_estab = None
        fetch_errors: list[str] = []
        for band_name, code in BANDS.items():
            try:
                current[band_name] = _fetch_band(
                    adapter, ledger, api_key, naics, CURRENT_YEAR, code
                )
            except (OfficialTransportError, OfficialDataError) as error:
                current[band_name] = {}
                fetch_errors.append(f"{CURRENT_YEAR}:{band_name}:{error.code}")
        baseline_target = Decimal(0)
        baseline_had_data = False
        for band_name in TARGET_BANDS:
            code = BANDS[band_name]
            try:
                values = _fetch_band(adapter, ledger, api_key, naics, BASELINE_YEAR, code)
                estab = values.get("establishment_count")
                if estab is not None:
                    baseline_target += estab
                    baseline_had_data = True
            except (OfficialTransportError, OfficialDataError) as error:
                fetch_errors.append(f"{BASELINE_YEAR}:{band_name}:{error.code}")
        if baseline_had_data:
            baseline_target_estab = baseline_target

        target_estab = sum(
            (current[b].get("establishment_count") or Decimal(0)) for b in TARGET_BANDS
        )
        target_payroll = sum(
            (current[b].get("annual_payroll_usd") or Decimal(0)) for b in TARGET_BANDS
        )
        all_estab = current.get("all_sizes", {}).get("establishment_count")
        any_target_data = any(current[b] for b in TARGET_BANDS)

        cagr = None
        if any_target_data and baseline_target_estab and baseline_target_estab > 0:
            years = CURRENT_YEAR - BASELINE_YEAR
            cagr = float((float(target_estab) / float(baseline_target_estab)) ** (1 / years) - 1)
        target_band_share = (
            float(target_estab / all_estab) if any_target_data and all_estab else None
        )
        payroll_per_estab = (
            float(target_payroll / target_estab) if any_target_data and target_estab > 0 else None
        )

        results.append(
            {
                "naics": naics,
                "label": label,
                "target_establishments_10_99": int(target_estab) if any_target_data else None,
                "target_establishments_10_99_baseline_2017": (
                    int(baseline_target_estab) if baseline_target_estab is not None else None
                ),
                "target_establishment_cagr_5yr": cagr,
                "all_sizes_establishments": int(all_estab) if all_estab is not None else None,
                "target_band_share_of_all_sizes": target_band_share,
                "payroll_per_target_establishment_usd": payroll_per_estab,
                "fetch_errors": fetch_errors,
            }
        )
        estab_display = results[-1]["target_establishments_10_99"]
        print(f"NAICS {naics} {label[:50]:<50}: {estab_display} target-band establishments")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw_candidates.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    qualifying = [
        r
        for r in results
        if cast(int | None, r["target_establishments_10_99"]) is not None
        and cast(int, r["target_establishments_10_99"]) >= MIN_ESTABLISHMENTS
    ]

    def _normalize(values: list[float], value: float | None) -> float | None:
        if value is None or not values:
            return None
        lo, hi = min(values), max(values)
        if hi <= lo:
            return 10.0
        return round(max(0.0, min(10.0, (value - lo) / (hi - lo) * 10)), 2)

    def _floats(rows: list[dict[str, object]], field: str) -> list[float]:
        return [float(cast(float, r[field])) for r in rows if r[field] is not None]

    def _as_float(value: object) -> float | None:
        return None if value is None else float(cast(float, value))

    q_estab = _floats(qualifying, "target_establishments_10_99")
    q_share = _floats(qualifying, "target_band_share_of_all_sizes")
    q_cagr = _floats(qualifying, "target_establishment_cagr_5yr")
    q_payroll = _floats(qualifying, "payroll_per_target_establishment_usd")

    for r in qualifying:
        business_count_n = _normalize(q_estab, _as_float(r["target_establishments_10_99"]))
        concentration_n = _normalize(q_share, _as_float(r["target_band_share_of_all_sizes"]))
        growth_n = _normalize(q_cagr, _as_float(r["target_establishment_cagr_5yr"]))
        economic_n = _normalize(q_payroll, _as_float(r["payroll_per_target_establishment_usd"]))
        components: list[tuple[str, float, float | None]] = [
            ("business_count", 0.40, business_count_n),
            ("concentration", 0.20, concentration_n),
            ("growth", 0.20, growth_n),
            ("economic_capacity", 0.20, economic_n),
        ]
        observed = [(w, v) for _, w, v in components if v is not None]
        observed_weight = sum(w for w, _ in observed)
        score = sum(w * v for w, v in observed) / observed_weight if observed_weight > 0 else None
        r["m1_light_score_components"] = {name: value for name, _, value in components}
        r["m1_light_observed_weight"] = round(observed_weight, 2)
        r["m1_light_score"] = round(score, 2) if score is not None else None

    qualifying.sort(key=lambda r: cast(float, r["m1_light_score"] or -1), reverse=True)
    results.sort(key=lambda r: cast(float, r["target_establishments_10_99"] or -1), reverse=True)

    output = {
        "current_year": CURRENT_YEAR,
        "baseline_year": BASELINE_YEAR,
        "min_establishments_threshold": MIN_ESTABLISHMENTS,
        "candidates_screened": len(results),
        "candidates_qualifying": len(qualifying),
        "all_candidates": results,
        "qualifying_candidates_ranked": qualifying,
    }
    (OUT_DIR / "wave_a_prescreen.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )

    print(f"\nRun: {RUN_ID}")
    print(
        f"Candidates screened: {len(results)} / "
        f"qualifying (>= {MIN_ESTABLISHMENTS} est.): {len(qualifying)}"
    )
    print(f"\n{'NAICS':<8} {'label':<45} {'estab':>8} {'cagr':>7} {'m1_light':>9}")
    for r in qualifying[:25]:
        cagr = cast(float | None, r["target_establishment_cagr_5yr"])
        print(
            f"{r['naics']:<8} {str(r['label'])[:45]:<45} "
            f"{r['target_establishments_10_99']:>8} "
            f"{(cagr * 100 if cagr is not None else float('nan')):>6.1f}% "
            f"{r['m1_light_score']:>9}"
        )
    print(f"\nBudget used: {ledger.usage.requests} requests, {ledger.usage.total_bytes} bytes")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
