import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.official_data.contracts import OfficialBatch, OfficialSourceId
from mask_api.modules.official_data.errors import OfficialDataError
from mask_api.modules.official_data.parsers import (
    parse_bea,
    parse_bls,
    parse_census_cbp,
    parse_sam_opportunities,
    parse_sec_submissions,
    parse_usaspending,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_census_cbp_normalizes_counts_and_thousand_dollar_payroll() -> None:
    body = fixture("census_cbp.json")
    batch = parse_census_cbp(body)

    assert batch.source_id == OfficialSourceId.CENSUS_CBP
    assert batch.raw_response == body
    assert batch.response_sha256 == hashlib.sha256(body).hexdigest()
    first = {item.metric: item for item in batch.observations[:3]}
    assert first["establishment_count"].value == Decimal("1200")
    assert first["employment"].value == Decimal("18000")
    assert first["annual_payroll_usd"].value == Decimal("950000000")
    assert first["annual_payroll_usd"].industry_code == "238220"
    assert len(batch.issues) == 1
    assert batch.issues[0].code == "census.value_unknown"


def test_bls_retains_series_and_period_without_inventing_units() -> None:
    batch = parse_bls(fixture("bls.json"))

    assert len(batch.observations) == 1
    observation = batch.observations[0]
    assert observation.source_record_id == "CES2023800001:2025:A01"
    assert observation.value == Decimal("125.5")
    assert observation.unit == "series_native_unit"
    assert batch.issues[0].code == "bls.value_unknown"


def test_bea_parses_comma_values_and_keeps_unknown_explicit() -> None:
    batch = parse_bea(fixture("bea.json"))

    assert len(batch.observations) == 1
    assert batch.observations[0].value == Decimal("1234.5")
    assert batch.observations[0].geography == "United States"
    assert batch.observations[0].industry_code == "238220"
    assert batch.issues[0].code == "bea.value_unknown"


def test_sec_columnar_submissions_become_lineage_records() -> None:
    batch = parse_sec_submissions(fixture("sec_submissions.json"))

    assert len(batch.records) == 2
    assert batch.records[0].source_record_id == "0000123456-25-000001"
    assert batch.records[0].attributes["cik"] == "0000123456"
    assert batch.records[0].attributes["form"] == "10-K"
    assert batch.records[1].published_date == "2024-11-05"


def test_sam_keeps_valid_public_opportunity_and_flags_missing_identity() -> None:
    batch = parse_sam_opportunities(fixture("sam_opportunities.json"))

    assert len(batch.records) == 1
    assert batch.records[0].source_record_id == "notice-1"
    assert batch.records[0].attributes["solicitation_number"] == "SOL-001"
    assert batch.records[0].attributes["naics_code"] == "238220"
    assert batch.issues[0].code == "sam.identity_missing"


def test_usaspending_keeps_valid_award_and_flags_missing_identity() -> None:
    batch = parse_usaspending(fixture("usaspending.json"))

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.source_record_id == "CONT_AWD_FIXTURE_0001"
    assert record.attributes["award_amount"] == 482500.0
    assert record.attributes["naics_code"] == "238220"
    assert record.attributes["recipient_name"] == "Fixture Field Services LLC"
    assert record.published_date == "2025-01-01"
    assert batch.issues[0].code == "usaspending.identity_missing"


def test_exact_duplicates_do_not_inflate_official_records() -> None:
    census = json.loads(fixture("census_cbp.json"))
    census.append(census[1])
    census_batch = parse_census_cbp(json.dumps(census).encode())

    sec = json.loads(fixture("sec_submissions.json"))
    recent = sec["filings"]["recent"]
    for column in recent.values():
        column.append(column[0])
    sec_batch = parse_sec_submissions(json.dumps(sec).encode())

    assert len(census_batch.observations) == 5
    assert census_batch.issues[-3].code == "official.duplicate_observation"
    assert len(sec_batch.records) == 2
    assert sec_batch.issues[-1].code == "official.duplicate_record"


def test_empty_valid_responses_remain_empty_instead_of_inventing_data() -> None:
    census = parse_census_cbp(b'[["NAME","NAICS2017","EMPSZES","ESTAB","EMP","PAYANN","us"]]')
    bls = parse_bls(b'{"status":"REQUEST_SUCCEEDED","Results":{"series":[]}}')
    bea = parse_bea(b'{"BEAAPI":{"Results":{"Data":[]}}}')
    sec = parse_sec_submissions(
        b'{"cik":"1","filings":{"recent":{"accessionNumber":[],"filingDate":[],'
        b'"reportDate":[],"form":[],"primaryDocument":[]}}}'
    )
    sam = parse_sam_opportunities(b'{"opportunitiesData":[]}')
    usaspending = parse_usaspending(b'{"results":[]}')

    assert not census.observations
    assert not bls.observations
    assert not bea.observations
    assert not sec.records
    assert not sam.records
    assert not usaspending.records


@pytest.mark.parametrize(
    ("parser", "body", "code"),
    [
        (parse_census_cbp, b"{}", "census.response_shape_invalid"),
        (parse_bls, b'{"status":"REQUEST_FAILED"}', "bls.request_not_successful"),
        (parse_bea, b'{"BEAAPI":{"Results":{"Error":{}}}}', "bea.request_not_successful"),
        (parse_bea, b'{"BEAAPI":{"Error":{}}}', "bea.request_not_successful"),
        (
            parse_sec_submissions,
            b'{"filings":{"recent":{"accessionNumber":[]}}}',
            "sec.columns_invalid",
        ),
        (parse_sam_opportunities, b"{}", "sam.opportunities_invalid"),
        (parse_census_cbp, b"not-json", "census.response_invalid"),
    ],
)
def test_malformed_source_payloads_fail_safely(
    parser: Callable[[bytes], OfficialBatch], body: bytes, code: str
) -> None:
    with pytest.raises(OfficialDataError) as captured:
        parser(body)

    assert captured.value.code == code
    assert body.decode(errors="ignore") not in str(captured.value)
