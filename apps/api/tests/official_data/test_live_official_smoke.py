from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.official_data.requests import (
    OfficialRequest,
    bea_regional_request,
    bls_request,
    census_cbp_request,
    sam_opportunities_request,
    sec_submissions_request,
)
from mask_api.modules.official_data.transport import (
    OfficialApiAdapter,
    OfficialApiSettings,
    UrllibOfficialTransport,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.configuration import load_source_profile
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[4]
PROFILE = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MASK_RUN_LIVE_OFFICIAL_SMOKE") != "1"
        or os.getenv("MASK_OFFICIAL_POLICY_APPROVED") != "1",
        reason="live official smoke requires explicit run and policy approval flags",
    ),
]


def _secret(name: str) -> SecretStr:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not configured")
    return SecretStr(value)


def _optional_secret(name: str) -> SecretStr | None:
    value = os.getenv(name)
    return SecretStr(value) if value else None


def _contact_user_agent() -> str:
    email = os.getenv("MASK_OFFICIAL_CONTACT_EMAIL")
    if not email:
        pytest.skip("MASK_OFFICIAL_CONTACT_EMAIL is not configured")
    return f"MASK-AI-Market-Research/0.1 {email}"


def _fetch(source_id: str, request: OfficialRequest) -> None:
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=1,
            max_documents=10,
            max_total_bytes=1_000_000,
            max_duration_seconds=30,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    adapter = OfficialApiAdapter(
        source_id,
        PROFILE.sources[source_id].model_copy(update={"operational_status": "available"}),
        OfficialApiSettings(
            enabled=True,
            policy_approved=True,
            timeout_seconds=10,
            max_response_bytes=1_000_000,
        ),
        UrllibOfficialTransport(),
        user_agent=_contact_user_agent(),
        now=lambda: datetime.now(UTC),
    )
    result = adapter.fetch(request, ledger)
    assert result.batch.source_id.value == source_id
    assert result.batch.raw_response
    assert ledger.usage.requests == 1


def test_live_census_cbp_single_query() -> None:
    _fetch(
        "census_cbp",
        census_cbp_request(
            year=2022,
            naics=238220,
            employment_size="001",
            geography="us:*",
            api_key=_secret("MASK_CENSUS_API_KEY"),
        ),
    )


def test_live_bls_single_series() -> None:
    _fetch(
        "bls",
        bls_request(
            series_ids=("CES2023800001",),
            start_year=2023,
            end_year=2023,
            registration_key=_optional_secret("MASK_BLS_API_KEY"),
        ),
    )


def test_live_bea_single_regional_query() -> None:
    _fetch(
        "bea",
        bea_regional_request(
            table_name="CAINC4",
            line_code=30,
            geography="06037",
            year=2023,
            api_key=_secret("MASK_BEA_API_KEY"),
        ),
    )


def test_live_sec_single_company_submissions_query() -> None:
    _fetch("sec_edgar", sec_submissions_request(cik=320193))


def test_live_sam_single_page_query() -> None:
    _fetch(
        "sam_gov",
        sam_opportunities_request(
            posted_from="01/01/2024",
            posted_to="01/02/2024",
            naics=238220,
            limit=1,
            offset=0,
            api_key=_secret("MASK_SAM_API_KEY"),
        ),
    )
