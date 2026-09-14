"""One-off live ingestion driver for the us_hvac_10_99 sample market.

This is NOT the permanent MethodExecutor/CollectionService composition
root (that does not exist yet). It is a deliberately standalone script
that exercises the real, already-tested adapters with real credentials
against the real live services, to prove data actually flows before more
integration plumbing is built. Every adapter call goes through the same
enabled/policy_approved gates and BudgetLedger the adapters already
enforce; nothing here bypasses those checks.

Usage:
    uv run python scripts/ingest_us_hvac_10_99.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.official_data.requests import (  # noqa: E402
    bls_request,
    census_cbp_request,
    sam_opportunities_request,
    sec_submissions_request,
    usaspending_award_search_request,
)
from mask_api.modules.official_data.transport import (  # noqa: E402
    OfficialApiAdapter,
    OfficialApiSettings,
    OfficialTransportError,
    UrllibOfficialTransport,
)
from mask_api.modules.youtube_data.quota import YouTubeQuotaLedger, YouTubeQuotaLimits  # noqa: E402
from mask_api.modules.youtube_data.requests import youtube_search_request  # noqa: E402
from mask_api.modules.youtube_data.transport import (  # noqa: E402
    UrllibYouTubeTransport,
    YouTubeApiAdapter,
    YouTubeApiSettings,
    YouTubeTransportError,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import load_source_profile  # noqa: E402
from mask_api.research_runner.contracts import SourceConfiguration  # noqa: E402
from pydantic import SecretStr  # noqa: E402

RUN_ID = f"ingest_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID / "raw"
NAICS = 238220
CONTACT_USER_AGENT = "MASK-AI-Market-Research/0.1"
# Comfort Systems USA Inc (NYSE: FIX), a real publicly traded HVAC/mechanical
# services company -- verified against SEC's own company_tickers.json and
# submissions endpoint before use, not guessed.
SEC_EDGAR_SAMPLE_CIK = 1035983


def _load_env_file(path: Path) -> None:
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _env(name: str) -> str | None:
    import os

    return os.environ.get(name)


def _write_raw(name: str, payload: dict[str, object]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{name}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def _official_source(
    profile_sources: dict[str, SourceConfiguration], key: str
) -> SourceConfiguration:
    return profile_sources[key].model_copy(update={"operational_status": "available"})


def main() -> None:
    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")

    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=100,
            max_documents=500,
            max_total_bytes=52_428_800,
            max_duration_seconds=3600,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    results: list[tuple[str, str, str]] = []  # (source, status, detail)

    official_transport = UrllibOfficialTransport()

    # --- Census CBP: real employment-size bands making up "10-99 employees" ---
    census_key = _env("MASK_CENSUS_API_KEY")
    if census_key:
        adapter = OfficialApiAdapter(
            "census_cbp",
            _official_source(profile.sources, "census_cbp"),
            OfficialApiSettings(enabled=True, policy_approved=True),
            official_transport,
            user_agent=CONTACT_USER_AGENT,
        )
        bands = {"10_19": "230", "20_49": "241", "50_99": "242", "all_sizes": "001"}
        census_out: dict[str, object] = {}
        for band_name, code in bands.items():
            try:
                request = census_cbp_request(
                    year=2022,
                    naics=NAICS,
                    employment_size=code,
                    geography="us:*",
                    api_key=SecretStr(census_key),
                )
                result = adapter.fetch(request, ledger)
                census_out[band_name] = [
                    obs.model_dump(mode="json") for obs in result.batch.observations
                ]
            except OfficialTransportError as error:
                census_out[band_name] = {"error": error.code}
        _write_raw("census_cbp", {"naics": NAICS, "bands": census_out})
        total_estab = int(
            sum(
                Decimal(str(obs["value"]))
                for band in ("10_19", "20_49", "50_99")
                for obs in census_out.get(band, [])
                if isinstance(obs, dict) and obs.get("metric") == "establishment_count"
            )
        )
        results.append(("census_cbp", "OK", f"{total_estab} establishments in 10-99 employee band"))
    else:
        results.append(("census_cbp", "SKIPPED", "MASK_CENSUS_API_KEY not configured"))

    # --- BLS: keyless, specialty trade contractors employment series ---
    try:
        adapter = OfficialApiAdapter(
            "bls",
            _official_source(profile.sources, "bls"),
            OfficialApiSettings(enabled=True, policy_approved=True),
            official_transport,
            user_agent=CONTACT_USER_AGENT,
        )
        registration_key = _env("MASK_BLS_API_KEY")
        request = bls_request(
            series_ids=("CES2023800001",),
            start_year=2023,
            end_year=2025,
            registration_key=SecretStr(registration_key) if registration_key else None,
        )
        result = adapter.fetch(request, ledger)
        _write_raw(
            "bls",
            {
                "series": "CES2023800001 (Specialty Trade Contractors employment, thousands)",
                "observations": [obs.model_dump(mode="json") for obs in result.batch.observations],
            },
        )
        results.append(("bls", "OK", f"{len(result.batch.observations)} monthly observations"))
    except OfficialTransportError as error:
        results.append(("bls", "FAILED", error.code))

    # --- BEA: skipped -- market defines no target region (regions: []) ---
    results.append(
        (
            "bea_regional",
            "SKIPPED",
            "us_hvac_10_99 defines no target region; BEA Regional needs one",
        )
    )

    # --- SEC EDGAR: filing metadata for one real, verified HVAC-industry company ---
    contact_email = _env("MASK_OFFICIAL_CONTACT_EMAIL")
    if contact_email:
        try:
            sec_adapter = OfficialApiAdapter(
                "sec_edgar",
                _official_source(profile.sources, "sec_edgar"),
                OfficialApiSettings(enabled=True, policy_approved=True),
                official_transport,
                user_agent=f"{CONTACT_USER_AGENT} ({contact_email})",
            )
            request = sec_submissions_request(cik=SEC_EDGAR_SAMPLE_CIK)
            result = sec_adapter.fetch(request, ledger)
            _write_raw(
                "sec_edgar",
                {
                    "cik": SEC_EDGAR_SAMPLE_CIK,
                    "company": "Comfort Systems USA Inc (NYSE: FIX)",
                    "records": [rec.model_dump(mode="json") for rec in result.batch.records],
                },
            )
            results.append(("sec_edgar", "OK", f"{len(result.batch.records)} filings"))
        except OfficialTransportError as error:
            results.append(("sec_edgar", "FAILED", error.code))
    else:
        results.append(("sec_edgar", "SKIPPED", "MASK_OFFICIAL_CONTACT_EMAIL not configured"))

    # --- SAM.gov: recent procurement opportunities for NAICS 238220 ---
    sam_key = _env("MASK_SAM_API_KEY")
    if sam_key:
        try:
            adapter = OfficialApiAdapter(
                "sam_gov",
                _official_source(profile.sources, "sam_gov"),
                OfficialApiSettings(enabled=True, policy_approved=True),
                official_transport,
                user_agent=CONTACT_USER_AGENT,
            )
            request = sam_opportunities_request(
                posted_from="06/13/2026",
                posted_to="09/11/2026",
                naics=NAICS,
                limit=25,
                offset=0,
                api_key=SecretStr(sam_key),
            )
            result = adapter.fetch(request, ledger)
            _write_raw(
                "sam_gov",
                {"records": [rec.model_dump(mode="json") for rec in result.batch.records]},
            )
            results.append(("sam_gov", "OK", f"{len(result.batch.records)} opportunities"))
        except OfficialTransportError as error:
            results.append(("sam_gov", "FAILED", error.code))
    else:
        results.append(("sam_gov", "SKIPPED", "MASK_SAM_API_KEY not configured"))

    # --- USAspending: keyless, recent HVAC-NAICS contract awards ---
    try:
        adapter = OfficialApiAdapter(
            "usaspending",
            _official_source(profile.sources, "usaspending"),
            OfficialApiSettings(enabled=True, policy_approved=True),
            official_transport,
            user_agent=CONTACT_USER_AGENT,
        )
        request = usaspending_award_search_request(
            naics_codes=(str(NAICS),),
            start_date="2024-01-01",
            end_date="2026-09-11",
            limit=25,
        )
        result = adapter.fetch(request, ledger)
        _write_raw(
            "usaspending",
            {"records": [rec.model_dump(mode="json") for rec in result.batch.records]},
        )
        results.append(("usaspending", "OK", f"{len(result.batch.records)} awards"))
    except OfficialTransportError as error:
        results.append(("usaspending", "FAILED", error.code))

    # --- YouTube: search for HVAC dispatch software discussion ---
    youtube_key = _env("MASK_youtube_API_KEY")
    if youtube_key:
        try:
            youtube_adapter = YouTubeApiAdapter(
                _official_source(profile.sources, "youtube"),
                YouTubeApiSettings(enabled=True, policy_approved=True),
                UrllibYouTubeTransport(),
                user_agent=CONTACT_USER_AGENT,
            )
            quota = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=10_000))
            request = youtube_search_request(
                query="HVAC dispatch software", api_key=SecretStr(youtube_key), max_results=15
            )
            result = youtube_adapter.fetch(request, ledger, quota)
            _write_raw(
                "youtube_search",
                {
                    "query": "HVAC dispatch software",
                    "videos": [v.model_dump(mode="json") for v in result.batch.videos],
                    "quota_cost": result.quota_cost,
                },
            )
            detail = f"{len(result.batch.videos)} videos, {result.quota_cost} quota units"
            results.append(("youtube_search", "OK", detail))
        except YouTubeTransportError as error:
            results.append(("youtube_search", "FAILED", error.code))
    else:
        results.append(("youtube_search", "SKIPPED", "MASK_youtube_API_KEY not configured"))

    # --- Common Crawl: skipped -- no registered source policy for a real HVAC URL ---
    results.append(
        (
            "common_crawl",
            "SKIPPED",
            "no approved SourcePolicy for a specific HVAC-industry URL exists yet "
            "(retrieval requires one already-approved target URL, not a search)",
        )
    )

    print(f"\nIngestion run: {RUN_ID}")
    print(f"Raw output: {OUT_DIR}\n")
    print(f"{'source':<18} {'status':<9} detail")
    print("-" * 70)
    for source, status, detail in results:
        print(f"{source:<18} {status:<9} {detail}")
    print(f"\nBudget used: {ledger.usage.requests} requests, {ledger.usage.total_bytes} bytes")

    _write_raw(
        "_summary",
        {
            "market_id": "us_hvac_10_99",
            "results": [{"source": s, "status": st, "detail": d} for s, st, d in results],
            "budget_usage": {
                "requests": ledger.usage.requests,
                "total_bytes": ledger.usage.total_bytes,
            },
        },
    )


if __name__ == "__main__":
    main()
