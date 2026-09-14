"""Real metro (CBSA) -level regional discovery for us_hvac_10_99 (NAICS 238220).

Directive section 27: perform the same discovery process as states.py for
Metropolitan/Micropolitan Statistical Areas, where Census CBP supports it.
Verified live before writing this: `for=metropolitan statistical area/
micropolitan statistical area:*` returns one real row per CBSA in a single
call (190 real metro rows for one employment band), the same bulk pattern
already used for states. The only code change required anywhere was
widening census_cbp_request()'s geography validator to accept this
literal Census geography-level name; no new adapter/parser was needed.

At CBSA level, Census suppresses EMP/PAYANN for many small-area cells for
disclosure avoidance (both fields legitimately return 0 even when ESTAB is
present) -- these are treated as UNKNOWN, never a real zero, per the
project's UNKNOWN-never-invented rule. Establishment counts are the
reliable metric at this geography level and are what section 27 actually
asks for.

BEA Regional MSA-level enrichment is NOT attempted in this pass (documented
limitation, not silently skipped) -- state-level BEA enrichment already
exists in discover_regions_us_hvac_10_99.py; MSA-level BEA join is later
work if the dossier needs it.

Usage:
    uv run python scripts/discover_metros_us_hvac_10_99.py
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

NAICS = 238220
CURRENT_YEAR = 2023
BASELINE_YEAR = 2018
BANDS = {"10_19": "230", "20_49": "241", "50_99": "242", "all_sizes": "001"}
CBSA_GEOGRAPHY = "metropolitan statistical area/micropolitan statistical area:*"
MIN_ESTABLISHMENTS = 100  # section 27 default
MIN_NATIONAL_SHARE = Decimal("0.005")  # 0.5%
RUN_ID = f"discover_metros_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
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
    request = census_cbp_request(
        year=year,
        naics=NAICS,
        employment_size=code,
        geography=CBSA_GEOGRAPHY,
        api_key=SecretStr(api_key),
    )
    result = adapter.fetch(request, ledger)
    by_metro: dict[str, dict[str, Decimal]] = {}
    for obs in result.batch.observations:
        by_metro.setdefault(obs.geography or "UNKNOWN", {})[obs.metric] = obs.value
    return by_metro


def _suppressed_as_unknown(value: Decimal | None, estab: Decimal | None) -> Decimal | None:
    """Census returns 0 for many EMP/PAYANN cells it has actually suppressed
    at CBSA granularity; a real zero alongside a nonzero establishment count
    is not credible, so treat it as UNKNOWN rather than inventing a zero."""
    if value == 0 and estab is not None and estab > 0:
        return None
    return value


def main() -> None:
    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_CENSUS_API_KEY")
    if not api_key:
        raise SystemExit("MASK_CENSUS_API_KEY is not configured; cannot run real metro discovery.")

    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=20,
            max_documents=20,
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
                print(f"OK   {year} {band_name}: {len(raw[str(year)][band_name])} metros")
            except OfficialTransportError as error:
                raw[str(year)][band_name] = {}
                print(f"FAIL {year} {band_name}: {error.code}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw_census_metro_bands.json").write_text(
        json.dumps(raw, indent=2, default=str), encoding="utf-8"
    )

    target_bands = ("10_19", "20_49", "50_99")
    metros: set[str] = set()
    for band in raw[str(CURRENT_YEAR)].values():
        metros.update(band.keys())

    per_metro: list[dict[str, object]] = []
    for metro in sorted(metros):
        cur = {b: raw[str(CURRENT_YEAR)].get(b, {}).get(metro, {}) for b in BANDS}
        base = {b: raw[str(BASELINE_YEAR)].get(b, {}).get(metro, {}) for b in BANDS}

        def _sum(bands_map: dict[str, dict[str, Decimal]], metric: str) -> Decimal | None:
            values = [bands_map[b].get(metric) for b in target_bands]
            if any(v is None for v in values):
                return None
            return sum(v for v in values if v is not None)  # type: ignore[misc]

        target_estab = _sum(cur, "establishment_count")
        target_estab_baseline = _sum(base, "establishment_count")
        target_payroll = _suppressed_as_unknown(_sum(cur, "annual_payroll_usd"), target_estab)
        target_emp = _suppressed_as_unknown(_sum(cur, "employment"), target_estab)
        all_estab = cur["all_sizes"].get("establishment_count")

        cagr = None
        if target_estab is not None and target_estab_baseline and target_estab_baseline > 0:
            years = CURRENT_YEAR - BASELINE_YEAR
            cagr = float((float(target_estab) / float(target_estab_baseline)) ** (1 / years) - 1)

        target_band_share = (
            float(target_estab / all_estab) if target_estab is not None and all_estab else None
        )

        per_metro.append(
            {
                "metro": metro,
                "target_establishments_10_99": (
                    int(target_estab) if target_estab is not None else None
                ),
                "target_establishments_10_99_baseline_2018": (
                    int(target_estab_baseline) if target_estab_baseline is not None else None
                ),
                "target_establishment_cagr_5yr": cagr,
                "target_employment_10_99": (
                    int(target_emp) if target_emp is not None else "UNKNOWN_SUPPRESSED"
                ),
                "target_annual_payroll_usd_10_99": (
                    int(target_payroll) if target_payroll is not None else "UNKNOWN_SUPPRESSED"
                ),
                "all_sizes_establishments": int(all_estab) if all_estab is not None else None,
                "target_band_share_of_all_sizes": target_band_share,
            }
        )

    national_target_total = sum(
        m["target_establishments_10_99"]
        for m in per_metro
        if m["target_establishments_10_99"] is not None
    )
    for m in per_metro:
        m["national_target_share"] = (
            m["target_establishments_10_99"] / national_target_total
            if m["target_establishments_10_99"] is not None and national_target_total
            else None
        )

    qualifying = [
        m
        for m in per_metro
        if m["target_establishments_10_99"] is not None
        and (
            m["target_establishments_10_99"] >= MIN_ESTABLISHMENTS
            or (m["national_target_share"] or 0) >= float(MIN_NATIONAL_SHARE)
        )
    ]
    qualifying.sort(key=lambda m: m["target_establishments_10_99"] or -1, reverse=True)
    per_metro.sort(key=lambda m: m["target_establishments_10_99"] or -1, reverse=True)

    output = {
        "market_id": "us_hvac_10_99",
        "naics": NAICS,
        "current_year": CURRENT_YEAR,
        "baseline_year": BASELINE_YEAR,
        "national_target_establishments_10_99": national_target_total,
        "min_establishments_threshold": MIN_ESTABLISHMENTS,
        "min_national_share_threshold": float(MIN_NATIONAL_SHARE),
        "metros_with_data": len(per_metro),
        "metros_qualifying": len(qualifying),
        "bea_msa_enrichment": "NOT_ATTEMPTED_THIS_PASS",
        "all_metros": per_metro,
        "qualifying_metros_ranked": qualifying,
    }
    (OUT_DIR / "metro_regional_discovery.json").write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )

    print(f"\nRun: {RUN_ID}")
    print(f"National target establishments across all metros: {national_target_total}")
    print(f"Metros with data: {len(per_metro)} / qualifying threshold: {len(qualifying)}")
    print(f"\n{'metro':<55} {'estab':>7} {'share':>7} {'cagr':>7}")
    for m in qualifying[:10]:
        share = m["national_target_share"] or 0
        cagr = m["target_establishment_cagr_5yr"]
        cagr_display = f"{cagr * 100:.2f}%" if cagr is not None else "UNKNOWN"
        print(
            f"{m['metro']:<55} {m['target_establishments_10_99']:>7} "
            f"{share * 100:>6.2f}% {cagr_display:>7}"
        )
    print(f"\nBudget used: {ledger.usage.requests} requests, {ledger.usage.total_bytes} bytes")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
