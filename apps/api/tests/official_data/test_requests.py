from __future__ import annotations

from collections.abc import Callable

import pytest
from mask_api.modules.official_data.contracts import OfficialSourceId
from mask_api.modules.official_data.requests import (
    bea_regional_request,
    bls_request,
    census_cbp_request,
    sam_opportunities_request,
    sec_submissions_request,
)
from pydantic import SecretStr

KEY = SecretStr("fixture-not-a-real-key")


def test_census_request_pins_dataset_vintage_and_redacts_key_from_provenance() -> None:
    request = census_cbp_request(
        year=2022,
        naics=238220,
        employment_size="242",
        geography="us:*",
        api_key=KEY,
    )

    assert request.endpoint == "https://api.census.gov/data/2022/cbp"
    assert request.query["NAICS2017"] == "238220"
    assert "NAICS2022" not in request.query
    provenance = request.provenance()
    assert provenance.source_id == OfficialSourceId.CENSUS_CBP
    assert provenance.credential_fields == ("key",)
    assert "fixture-not-a-real-key" not in provenance.model_dump_json()


def test_bls_unregistered_and_registered_limits_are_explicit() -> None:
    unregistered = bls_request(
        series_ids=("CES2023800001",),
        start_year=2016,
        end_year=2025,
    )
    registered = bls_request(
        series_ids=tuple(f"SERIES{index}" for index in range(50)),
        start_year=2006,
        end_year=2025,
        registration_key=KEY,
    )

    assert unregistered.json_body is not None
    assert unregistered.json_body["annualaverage"] is False
    assert registered.json_body is not None
    assert registered.json_body["annualaverage"] is True
    assert registered.provenance().credential_fields == ("registrationkey",)


def test_other_builders_use_only_documented_fixed_endpoints() -> None:
    bea = bea_regional_request(
        table_name="CAEMP25N",
        line_code=10,
        geography="COUNTY",
        year=2023,
        api_key=KEY,
    )
    sec = sec_submissions_request(cik=320193)
    sam = sam_opportunities_request(
        posted_from="01/01/2024",
        posted_to="01/31/2024",
        naics=238220,
        limit=10,
        offset=0,
        api_key=KEY,
    )

    assert bea.endpoint == "https://apps.bea.gov/api/data/"
    assert bea.query["method"] == "GetData"
    assert sec.endpoint.endswith("CIK0000320193.json")
    assert sam.endpoint == "https://api.sam.gov/opportunities/v2/search"
    assert sam.query["limit"] == "10"


@pytest.mark.parametrize(
    "call",
    [
        lambda: census_cbp_request(
            year=2022,
            naics=238220,
            employment_size="242",
            geography="us:*",
            api_key=SecretStr(""),
        ),
        lambda: bls_request(
            series_ids=tuple(f"SERIES{index}" for index in range(26)),
            start_year=2025,
            end_year=2025,
        ),
        lambda: bls_request(
            series_ids=("lowercase",),
            start_year=2025,
            end_year=2025,
        ),
        lambda: bls_request(
            series_ids=("SERIES1",),
            start_year=2015,
            end_year=2025,
        ),
        lambda: sam_opportunities_request(
            posted_from="02/30/2024",
            posted_to="03/01/2024",
            naics=238220,
            limit=10,
            offset=0,
            api_key=KEY,
        ),
        lambda: sam_opportunities_request(
            posted_from="01/01/2023",
            posted_to="01/03/2024",
            naics=238220,
            limit=10,
            offset=0,
            api_key=KEY,
        ),
    ],
)
def test_invalid_or_overbroad_official_requests_are_rejected(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        call()
