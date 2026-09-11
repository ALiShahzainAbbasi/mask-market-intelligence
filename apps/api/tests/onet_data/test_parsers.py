from __future__ import annotations

from pathlib import Path

import pytest
from mask_api.modules.onet_data.contracts import OnetTaskType
from mask_api.modules.onet_data.errors import OnetDataError
from mask_api.modules.onet_data.parsers import parse_occupation_data, parse_task_statements

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_occupation_data_keeps_valid_rows_and_flags_missing_description() -> None:
    occupations, issues = parse_occupation_data(fixture("occupation_data.csv"))

    assert len(occupations) == 1
    occupation = occupations[0]
    assert occupation.onet_soc_code == "49-9021.00"
    assert occupation.title == "Heating and Air Conditioning Mechanics"
    assert any(issue.code == "onet.occupation_data.row_invalid" for issue in issues)


def test_parse_occupation_data_rejects_malformed_header() -> None:
    with pytest.raises(OnetDataError) as captured:
        parse_occupation_data(b"Wrong,Header\nfoo,bar\n")

    assert captured.value.code == "onet.occupation_data.header_invalid"


def test_parse_task_statements_keeps_blank_type_and_incumbents_as_unknown() -> None:
    statements, issues = parse_task_statements(fixture("task_statements.csv"))

    by_id = {statement.task_id: statement for statement in statements}
    assert by_id[10001].task_type == OnetTaskType.CORE
    assert by_id[10001].incumbents_responding == 42
    assert by_id[10002].task_type == OnetTaskType.SUPPLEMENTAL
    assert by_id[10002].incumbents_responding is None
    assert by_id[10004].task_type is None
    assert by_id[10004].incumbents_responding == 15
    assert 10003 not in by_id
    assert any(issue.code == "onet.task_statements.row_invalid" for issue in issues)


def test_parse_task_statements_rejects_malformed_header() -> None:
    with pytest.raises(OnetDataError) as captured:
        parse_task_statements(b"Wrong,Header\nfoo,bar\n")

    assert captured.value.code == "onet.task_statements.header_invalid"


def test_exact_duplicate_rows_do_not_inflate_records() -> None:
    duplicate_row = (
        b"49-9021.00,Heating and Air Conditioning Mechanics,"
        b'"Install or repair heating, central air conditioning, HVAC, or refrigeration '
        b'systems, including oil burners, hot-air furnaces, and heating stoves."\n'
    )
    body = fixture("occupation_data.csv") + duplicate_row

    occupations, issues = parse_occupation_data(body)

    assert len(occupations) == 1
    assert any(issue.code == "onet.duplicate_occupation" for issue in issues)


def test_empty_valid_responses_remain_empty_instead_of_inventing_data() -> None:
    occupations, occupation_issues = parse_occupation_data(b"O*NET-SOC Code,Title,Description\n")
    statements, statement_issues = parse_task_statements(
        b"O*NET-SOC Code,Title,Task ID,Task,Task Type,Incumbents Responding,Date,Domain Source\n"
    )

    assert not occupations
    assert not occupation_issues
    assert not statements
    assert not statement_issues
