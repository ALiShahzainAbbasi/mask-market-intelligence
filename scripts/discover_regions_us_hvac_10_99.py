"""Real state-level regional discovery for us_hvac_10_99 (NAICS 238220).

Per the owner's explicit instruction: do NOT manually pick a BEA region.
Discover the strongest states from real Census CBP data first, then
qualify a subset by a configurable threshold, matching
docs/AUTONOMOUS_RESEARCH_MODE.md's UNKNOWN-never-invented discipline.

This reuses mask_api.modules.official_data.requests.census_cbp_request /
OfficialApiAdapter completely unchanged -- `for=state:*` already returns
one real row per state in a single call, and the existing parser already
attaches each row's own geography name and a state-qualified record_id.
No new adapter or parser code was needed for this.

Usage:
    uv run python scripts/discover_regions_us_hvac_10_99.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.official_data.errors import OfficialDataError  # noqa: E402
from mask_api.modules.official_data.requests import (  # noqa: E402
    bea_regional_request,
    census_cbp_request,
)
from mask_api.modules.official_data.transport import (  # noqa: E402
    OfficialApiAdapter,
    OfficialApiSettings,
    OfficialTransportError,
    UrllibOfficialTransport,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import load_source_profile  # noqa: E402
from pydantic import SecretStr  # noqa: E402

NAICS = 238220
CURRENT_YEAR = 2023
BASELINE_YEAR = 2018  # verified available; 5-year window matches SCORING's CAGR convention
BANDS = {"10_19": "230", "20_49": "241", "50_99": "242", "all_sizes": "001"}
MIN_ESTABLISHMENTS = 300  # section 25 default
# CAINC4 line codes verified via BEA's own GetParameterValuesFiltered metadata call
# (not guessed): 10 = total personal income, 30 = per-capita personal income.
BEA_TABLE = "CAINC4"
BEA_LINE_CODES = {
    "personal_income_total_usd_thousands": "10",
    "per_capita_personal_income_usd": "30",
}
MIN_NATIONAL_SHARE = Decimal("0.015")  # 1.5%
RUN_ID = f"discover_regions_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
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
    adapter: OfficialApiAdapter, ledger: BudgetLedger, api_key: str, year: int, code: str
) -> dict[str, dict[str, Decimal]]:
    """Returns {state_name: {metric: value}} for one year/employment-size band."""
    request = census_cbp_request(
        year=year,
        naics=NAICS,
        employment_size=code,
        geography="state:*",
        api_key=SecretStr(api_key),
    )
    result = adapter.fetch(request, ledger)
    by_state: dict[str, dict[str, Decimal]] = {}
    for obs in result.batch.observations:
        by_state.setdefault(obs.geography or "UNKNOWN", {})[obs.metric] = obs.value
    return by_state


def _fetch_bea_state(
    adapter: OfficialApiAdapter, ledger: BudgetLedger, api_key: str, line_code: str, year: int
) -> tuple[dict[str, dict[str, object]], str | None]:
    """Returns ({state_name: {value, unit, period}}, error_code_or_None).

    GeoFIPS=STATE returns one real row per state (plus the national total
    and territories) in a single call -- verified against BEA's own API
    before use, matching the same bulk-query pattern as Census's `state:*`.
    """
    request = bea_regional_request(
        table_name=BEA_TABLE,
        line_code=int(line_code),
        geography="STATE",
        year=year,
        api_key=SecretStr(api_key),
    )
    try:
        result = adapter.fetch(request, ledger)
    except (OfficialTransportError, OfficialDataError) as error:
        return {}, getattr(error, "code", type(error).__name__)
    by_state: dict[str, dict[str, object]] = {}
    for obs in result.batch.observations:
        if obs.geography and obs.geography != "United States":
            by_state[obs.geography] = {
                "value": float(obs.value),
                "unit": obs.unit,
                "period": obs.period,
            }
    return by_state, None


def main() -> None:
    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_CENSUS_API_KEY")
    bea_key = os.environ.get("MASK_BEA_API_KEY")
    if not api_key:
        raise SystemExit(
            "MASK_CENSUS_API_KEY is not configured; cannot run real regional discovery."
        )

    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=50,
            max_documents=50,
            max_total_bytes=20_000_000,
            max_duration_seconds=1800,
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

    raw: dict[str, dict[str, dict[str, dict[str, Decimal]]]] = {}
    for year in (CURRENT_YEAR, BASELINE_YEAR):
        raw[str(year)] = {}
        for band_name, code in BANDS.items():
            try:
                raw[str(year)][band_name] = _fetch_band(adapter, ledger, api_key, year, code)
                print(f"OK   {year} {band_name}: {len(raw[str(year)][band_name])} states")
            except OfficialTransportError as error:
                raw[str(year)][band_name] = {}
                print(f"FAIL {year} {band_name}: {error.code}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw_census_state_bands.json").write_text(
        json.dumps(raw, indent=2, default=str), encoding="utf-8"
    )

    target_bands = ("10_19", "20_49", "50_99")
    states: set[str] = set()
    for band in raw[str(CURRENT_YEAR)].values():
        states.update(band.keys())

    per_state: list[dict[str, object]] = []
    for state in sorted(states):
        cur = {b: raw[str(CURRENT_YEAR)].get(b, {}).get(state, {}) for b in BANDS}
        base = {b: raw[str(BASELINE_YEAR)].get(b, {}).get(state, {}) for b in BANDS}

        def _sum(bands_map: dict[str, dict[str, Decimal]], metric: str) -> Decimal | None:
            values = [bands_map[b].get(metric) for b in target_bands]
            if any(v is None for v in values):
                return None
            return sum(v for v in values if v is not None)  # type: ignore[misc]

        target_estab = _sum(cur, "establishment_count")
        target_estab_baseline = _sum(base, "establishment_count")
        target_payroll = _sum(cur, "annual_payroll_usd")
        target_emp = _sum(cur, "employment")
        all_estab = cur["all_sizes"].get("establishment_count")

        cagr = None
        if target_estab is not None and target_estab_baseline and target_estab_baseline > 0:
            years = CURRENT_YEAR - BASELINE_YEAR
            cagr = float((float(target_estab) / float(target_estab_baseline)) ** (1 / years) - 1)

        target_band_share = (
            float(target_estab / all_estab) if target_estab is not None and all_estab else None
        )
        payroll_per_estab = (
            float(target_payroll / target_estab)
            if target_payroll is not None and target_estab and target_estab > 0
            else None
        )

        per_state.append(
            {
                "state": state,
                "target_establishments_10_99": int(target_estab)
                if target_estab is not None
                else None,
                "target_establishments_10_99_baseline_2018": (
                    int(target_estab_baseline) if target_estab_baseline is not None else None
                ),
                "target_establishment_cagr_5yr": cagr,
                "target_employment_10_99": int(target_emp) if target_emp is not None else None,
                "target_annual_payroll_usd_10_99": (
                    int(target_payroll) if target_payroll is not None else None
                ),
                "all_sizes_establishments": int(all_estab) if all_estab is not None else None,
                "target_band_share_of_all_sizes": target_band_share,
                "payroll_per_target_establishment_usd": payroll_per_estab,
            }
        )

    national_target_total = sum(
        s["target_establishments_10_99"]
        for s in per_state
        if s["target_establishments_10_99"] is not None
    )
    for s in per_state:
        s["national_target_share"] = (
            s["target_establishments_10_99"] / national_target_total
            if s["target_establishments_10_99"] is not None and national_target_total
            else None
        )

    qualifying = [
        s
        for s in per_state
        if s["target_establishments_10_99"] is not None
        and (
            s["target_establishments_10_99"] >= MIN_ESTABLISHMENTS
            or (s["national_target_share"] or 0) >= float(MIN_NATIONAL_SHARE)
        )
    ]

    def _normalize(values: list[float], value: float | None) -> float | None:
        if value is None or not values:
            return None
        lo, hi = min(values), max(values)
        if hi <= lo:
            return 10.0
        return round(max(0.0, min(10.0, (value - lo) / (hi - lo) * 10)), 2)

    q_estab = [
        s["target_establishments_10_99"]
        for s in qualifying
        if s["target_establishments_10_99"] is not None
    ]
    q_share = [
        s["target_band_share_of_all_sizes"]
        for s in qualifying
        if s["target_band_share_of_all_sizes"] is not None
    ]
    q_cagr = [
        s["target_establishment_cagr_5yr"]
        for s in qualifying
        if s["target_establishment_cagr_5yr"] is not None
    ]
    q_payroll = [
        s["payroll_per_target_establishment_usd"]
        for s in qualifying
        if s["payroll_per_target_establishment_usd"] is not None
    ]

    for s in qualifying:
        business_count_n = _normalize(q_estab, s["target_establishments_10_99"])
        concentration_n = _normalize(q_share, s["target_band_share_of_all_sizes"])
        growth_n = _normalize(q_cagr, s["target_establishment_cagr_5yr"])
        economic_n = _normalize(q_payroll, s["payroll_per_target_establishment_usd"])
        components = [
            ("business_count", 0.40, business_count_n),
            ("concentration", 0.20, concentration_n),
            ("growth", 0.20, growth_n),
            ("economic_capacity", 0.20, economic_n),
        ]
        observed = [(w, v) for _, w, v in components if v is not None]
        observed_weight = sum(w for w, _ in observed)
        score = sum(w * v for w, v in observed) / observed_weight if observed_weight > 0 else None
        s["regional_prescreen_score_components"] = {name: value for name, _, value in components}
        s["regional_prescreen_observed_weight"] = round(observed_weight, 2)
        s["regional_prescreen_score"] = round(score, 2) if score is not None else None

    # --- Section 26: BEA all-state enrichment, joined onto qualifying states only ---
    # GeoFIPS=STATE is the aggregate selector -- no manually-picked FIPS code.
    bea_errors: dict[str, str] = {}
    bea_by_metric: dict[str, dict[str, dict[str, object]]] = {}
    if bea_key:
        bea_adapter = OfficialApiAdapter(
            "bea",
            profile.sources["bea"].model_copy(update={"operational_status": "available"}),
            OfficialApiSettings(enabled=True, policy_approved=True),
            UrllibOfficialTransport(),
            user_agent="MASK-AI-Market-Research/0.1",
        )
        for metric_name, line_code in BEA_LINE_CODES.items():
            by_state, err = _fetch_bea_state(bea_adapter, ledger, bea_key, line_code, CURRENT_YEAR)
            bea_by_metric[metric_name] = by_state
            if err:
                bea_errors[metric_name] = err
            print(f"BEA {metric_name} (LineCode {line_code}): {len(by_state)} states, err={err}")
        for s in qualifying:
            bea_record: dict[str, object] = {}
            for metric_name, by_state in bea_by_metric.items():
                row = by_state.get(s["state"])
                bea_record[metric_name] = row["value"] if row else None
                if row:
                    bea_record[f"{metric_name}_unit"] = row["unit"]
                    bea_record[f"{metric_name}_period"] = row["period"]
            s["bea_enrichment"] = bea_record
            s["bea_enrichment_status"] = (
                "OBSERVED"
                if any(v is not None for v in bea_record.values())
                else "SOURCE_UNAVAILABLE"
            )
    else:
        for s in qualifying:
            s["bea_enrichment"] = None
            s["bea_enrichment_status"] = "SOURCE_UNAVAILABLE_NO_KEY"

    qualifying.sort(key=lambda s: s["regional_prescreen_score"] or -1, reverse=True)
    per_state.sort(key=lambda s: s["target_establishments_10_99"] or -1, reverse=True)

    output = {
        "market_id": "us_hvac_10_99",
        "naics": NAICS,
        "current_year": CURRENT_YEAR,
        "baseline_year": BASELINE_YEAR,
        "national_target_establishments_10_99": national_target_total,
        "min_establishments_threshold": MIN_ESTABLISHMENTS,
        "min_national_share_threshold": float(MIN_NATIONAL_SHARE),
        "states_with_data": len(per_state),
        "states_qualifying": len(qualifying),
        "bea_table": BEA_TABLE,
        "bea_line_codes": BEA_LINE_CODES,
        "bea_errors": bea_errors,
        "all_states": per_state,
        "qualifying_states_ranked": qualifying,
    }
    (OUT_DIR / "state_regional_discovery.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )

    print(f"\nRun: {RUN_ID}")
    print(f"National target establishments (10-99, NAICS {NAICS}): {national_target_total}")
    print(f"States with usable data: {len(per_state)} / qualifying threshold: {len(qualifying)}")
    print(
        f"\n{'state':<20} {'estab':>7} {'share':>7} {'cagr':>7} {'score':>7} {'per_cap_income':>15}"
    )
    for s in qualifying[:10]:
        share = s["national_target_share"] or 0
        cagr = s["target_establishment_cagr_5yr"]
        bea = s.get("bea_enrichment") or {}
        per_cap = bea.get("per_capita_personal_income_usd")
        print(
            f"{s['state']:<20} {s['target_establishments_10_99']:>7} "
            f"{share * 100:>6.2f}% {(cagr * 100 if cagr is not None else float('nan')):>6.2f}% "
            f"{s['regional_prescreen_score']:>7} "
            f"{('$' + format(per_cap, ',.0f')) if per_cap else 'UNKNOWN':>15}"
        )
    print(f"\nBudget used: {ledger.usage.requests} requests, {ledger.usage.total_bytes} bytes")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
