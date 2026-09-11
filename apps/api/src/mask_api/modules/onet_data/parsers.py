"""Deterministic parsers for the two O*NET CSV tables this module imports.

Column names and formats were verified against the real O*NET 31.0 CSV
database release (`occupation_data.csv`, `task_statements.csv`), not
guessed: `O*NET-SOC Code,Title,Description` and `O*NET-SOC Code,Title,
Task ID,Task,Task Type,Incumbents Responding,Date,Domain Source`
respectively. `Task Type` and `Incumbents Responding` are sometimes blank
in the real data and must stay `None`, never a guessed default.
"""

from __future__ import annotations

import csv
import io
import re

from mask_api.modules.onet_data.contracts import (
    OnetOccupation,
    OnetParseIssue,
    OnetTaskStatement,
    OnetTaskType,
)
from mask_api.modules.onet_data.errors import OnetDataError

_SOC_CODE = re.compile(r"^[0-9]{2}-[0-9]{4}\.[0-9]{2}$")


def parse_occupation_data(
    csv_bytes: bytes,
) -> tuple[tuple[OnetOccupation, ...], tuple[OnetParseIssue, ...]]:
    rows = _rows(csv_bytes, {"O*NET-SOC Code", "Title", "Description"}, "onet.occupation_data")
    occupations: list[OnetOccupation] = []
    issues: list[OnetParseIssue] = []
    for row_number, row in rows:
        code = row["O*NET-SOC Code"].strip()
        title = row["Title"].strip()
        description = row["Description"].strip()
        if not _SOC_CODE.fullmatch(code) or not title or not description:
            issues.append(
                OnetParseIssue(code="onet.occupation_data.row_invalid", row_number=row_number)
            )
            continue
        occupations.append(OnetOccupation(onet_soc_code=code, title=title, description=description))
    unique, duplicates = _dedupe(occupations)
    issues.extend(OnetParseIssue(code="onet.duplicate_occupation") for _ in duplicates)
    return unique, tuple(issues)


def parse_task_statements(
    csv_bytes: bytes,
) -> tuple[tuple[OnetTaskStatement, ...], tuple[OnetParseIssue, ...]]:
    required = {
        "O*NET-SOC Code",
        "Task ID",
        "Task",
        "Task Type",
        "Incumbents Responding",
        "Date",
        "Domain Source",
    }
    rows = _rows(csv_bytes, required, "onet.task_statements")
    statements: list[OnetTaskStatement] = []
    issues: list[OnetParseIssue] = []
    for row_number, row in rows:
        code = row["O*NET-SOC Code"].strip()
        task = row["Task"].strip()
        task_id = _positive_int(row["Task ID"])
        if not _SOC_CODE.fullmatch(code) or not task or task_id is None:
            issues.append(
                OnetParseIssue(code="onet.task_statements.row_invalid", row_number=row_number)
            )
            continue
        statements.append(
            OnetTaskStatement(
                onet_soc_code=code,
                task_id=task_id,
                task=task,
                task_type=_task_type(row["Task Type"]),
                incumbents_responding=_nonnegative_int(row["Incumbents Responding"]),
                date=_string_or_none(row["Date"]),
                domain_source=_string_or_none(row["Domain Source"]),
            )
        )
    unique, duplicates = _dedupe(statements)
    issues.extend(OnetParseIssue(code="onet.duplicate_task_statement") for _ in duplicates)
    return unique, tuple(issues)


def _rows(
    csv_bytes: bytes, required_columns: set[str], code_prefix: str
) -> list[tuple[int, dict[str, str]]]:
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise OnetDataError(f"{code_prefix}.encoding_invalid") from error
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not required_columns <= set(reader.fieldnames):
        raise OnetDataError(f"{code_prefix}.header_invalid")
    rows: list[tuple[int, dict[str, str]]] = []
    for row_number, row in enumerate(reader, start=2):
        if any(value is None for value in row.values()):
            continue
        rows.append((row_number, row))
    return rows


def _task_type(value: str) -> OnetTaskType | None:
    stripped = value.strip()
    try:
        return OnetTaskType(stripped) if stripped else None
    except ValueError:
        return None


def _positive_int(value: str) -> int | None:
    stripped = value.strip()
    if not stripped.isdigit():
        return None
    parsed = int(stripped)
    return parsed if parsed > 0 else None


def _nonnegative_int(value: str) -> int | None:
    stripped = value.strip()
    return int(stripped) if stripped.isdigit() else None


def _string_or_none(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _dedupe[T: OnetOccupation | OnetTaskStatement](
    values: list[T],
) -> tuple[tuple[T, ...], list[T]]:
    unique: list[T] = []
    duplicates: list[T] = []
    seen: set[str] = set()
    for value in values:
        fingerprint = value.model_dump_json()
        if fingerprint in seen:
            duplicates.append(value)
            continue
        seen.add(fingerprint)
        unique.append(value)
    return tuple(unique), duplicates
