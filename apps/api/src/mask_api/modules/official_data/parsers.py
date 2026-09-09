"""Deterministic parsers for bounded official API JSON responses."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from mask_api.modules.official_data.contracts import (
    OfficialBatch,
    OfficialObservation,
    OfficialParseIssue,
    OfficialRecord,
    OfficialSourceId,
)
from mask_api.modules.official_data.errors import OfficialDataError


def parse_census_cbp(body: bytes) -> OfficialBatch:
    raw = _json(body, "census.response_invalid")
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], list):
        raise OfficialDataError("census.response_shape_invalid")
    headers = _string_list(raw[0], "census.headers_invalid")
    required = {"NAME", "ESTAB", "EMP", "PAYANN"}
    if not required <= set(headers):
        raise OfficialDataError("census.required_fields_missing")
    observations: list[OfficialObservation] = []
    issues: list[OfficialParseIssue] = []
    for row_number, values in enumerate(raw[1:], start=1):
        if not isinstance(values, list) or len(values) != len(headers):
            issues.append(OfficialParseIssue(code="census.row_shape_invalid"))
            continue
        row = dict(zip(headers, (str(value) for value in values), strict=True))
        industry = row.get("NAICS2022") or row.get("NAICS2017")
        record_id = ":".join(
            value
            for value in (
                row.get("us"),
                row.get("state"),
                row.get("county"),
                industry,
                row.get("EMPSZES"),
            )
            if value
        )
        if not record_id:
            record_id = f"row-{row_number}"
        for field, metric, unit, multiplier in (
            ("ESTAB", "establishment_count", "establishments", Decimal("1")),
            ("EMP", "employment", "employees", Decimal("1")),
            ("PAYANN", "annual_payroll_usd", "USD", Decimal("1000")),
        ):
            value = _decimal(row[field])
            if value is None:
                issues.append(
                    OfficialParseIssue(code="census.value_unknown", source_record_id=record_id)
                )
                continue
            observations.append(
                OfficialObservation(
                    source_id=OfficialSourceId.CENSUS_CBP,
                    source_record_id=record_id,
                    metric=metric,
                    value=value * multiplier,
                    unit=unit,
                    geography=row["NAME"],
                    industry_code=industry,
                    label=row.get("NAICS2022_LABEL") or row.get("NAICS2017_LABEL"),
                )
            )
    return _batch(OfficialSourceId.CENSUS_CBP, "census-cbp-v1", body, observations, (), issues)


def parse_bls(body: bytes) -> OfficialBatch:
    raw = _object(_json(body, "bls.response_invalid"), "bls.response_shape_invalid")
    if raw.get("status") != "REQUEST_SUCCEEDED":
        raise OfficialDataError("bls.request_not_successful")
    results = raw.get("Results")
    if isinstance(results, list) and results:
        results = results[0]
    result_object = _object(results, "bls.results_invalid")
    series_values = result_object.get("series")
    if not isinstance(series_values, list):
        raise OfficialDataError("bls.series_invalid")
    observations: list[OfficialObservation] = []
    issues: list[OfficialParseIssue] = []
    for series in series_values:
        if not isinstance(series, dict) or not isinstance(series.get("seriesID"), str):
            issues.append(OfficialParseIssue(code="bls.series_record_invalid"))
            continue
        series_id = series["seriesID"]
        data = series.get("data")
        if not isinstance(data, list):
            issues.append(
                OfficialParseIssue(code="bls.series_data_invalid", source_record_id=series_id)
            )
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            year, period = item.get("year"), item.get("period")
            value = _decimal(item.get("value"))
            if not isinstance(year, str) or not isinstance(period, str) or value is None:
                issues.append(
                    OfficialParseIssue(code="bls.value_unknown", source_record_id=series_id)
                )
                continue
            observations.append(
                OfficialObservation(
                    source_id=OfficialSourceId.BLS,
                    source_record_id=f"{series_id}:{year}:{period}",
                    metric="series_value",
                    value=value,
                    unit="series_native_unit",
                    period=f"{year}-{period}",
                    label=series_id,
                )
            )
    return _batch(OfficialSourceId.BLS, "bls-v2-v1", body, observations, (), issues)


def parse_bea(body: bytes) -> OfficialBatch:
    raw = _object(_json(body, "bea.response_invalid"), "bea.response_shape_invalid")
    api = _object(raw.get("BEAAPI"), "bea.api_object_invalid")
    if api.get("Error") is not None:
        raise OfficialDataError("bea.request_not_successful")
    results = _object(api.get("Results"), "bea.results_invalid")
    if results.get("Error") is not None:
        raise OfficialDataError("bea.request_not_successful")
    data = results.get("Data")
    if not isinstance(data, list):
        raise OfficialDataError("bea.data_invalid")
    observations: list[OfficialObservation] = []
    issues: list[OfficialParseIssue] = []
    for row in data:
        if not isinstance(row, dict):
            issues.append(OfficialParseIssue(code="bea.row_invalid"))
            continue
        record_id = ":".join(
            str(row.get(key, "")) for key in ("TableName", "LineCode", "GeoFIPS", "TimePeriod")
        )
        value = _decimal(row.get("DataValue"))
        if value is None:
            issues.append(OfficialParseIssue(code="bea.value_unknown", source_record_id=record_id))
            continue
        observations.append(
            OfficialObservation(
                source_id=OfficialSourceId.BEA,
                source_record_id=record_id,
                metric="regional_value",
                value=value,
                unit=str(row.get("UNIT_MULT", row.get("Unit", "source_native_unit"))),
                period=str(row.get("TimePeriod", "")) or None,
                geography=str(row.get("GeoName", "")) or None,
                industry_code=str(row.get("IndustryClassification", "")) or None,
                label=str(row.get("LineDescription", "")) or None,
            )
        )
    return _batch(OfficialSourceId.BEA, "bea-regional-v1", body, observations, (), issues)


def parse_sec_submissions(body: bytes) -> OfficialBatch:
    raw = _object(_json(body, "sec.response_invalid"), "sec.response_shape_invalid")
    cik = str(raw.get("cik", "")).zfill(10)
    filings = _object(raw.get("filings"), "sec.filings_invalid")
    recent = _object(filings.get("recent"), "sec.recent_invalid")
    columns = {
        key: recent.get(key)
        for key in ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    }
    if any(not isinstance(values, list) for values in columns.values()):
        raise OfficialDataError("sec.columns_invalid")
    lengths = {len(values) for values in columns.values() if isinstance(values, list)}
    if len(lengths) != 1:
        raise OfficialDataError("sec.column_lengths_invalid")
    records: list[OfficialRecord] = []
    issues: list[OfficialParseIssue] = []
    for index in range(next(iter(lengths), 0)):
        accession = str(columns["accessionNumber"][index]).strip()  # type: ignore[index]
        form = str(columns["form"][index]).strip()  # type: ignore[index]
        filing_date = str(columns["filingDate"][index]).strip()  # type: ignore[index]
        if not accession or not form or not filing_date:
            issues.append(OfficialParseIssue(code="sec.identity_missing"))
            continue
        records.append(
            OfficialRecord(
                source_id=OfficialSourceId.SEC_EDGAR,
                source_record_id=accession,
                title=f"{form} filing for {raw.get('name', cik)}",
                published_date=filing_date,
                attributes={
                    "cik": cik,
                    "form": form,
                    "report_date": str(columns["reportDate"][index]),  # type: ignore[index]
                    "primary_document": str(columns["primaryDocument"][index]),  # type: ignore[index]
                },
            )
        )
    return _batch(OfficialSourceId.SEC_EDGAR, "sec-submissions-v1", body, (), records, issues)


def parse_sam_opportunities(body: bytes) -> OfficialBatch:
    raw = _object(_json(body, "sam.response_invalid"), "sam.response_shape_invalid")
    values = raw.get("opportunitiesData")
    if not isinstance(values, list):
        raise OfficialDataError("sam.opportunities_invalid")
    records: list[OfficialRecord] = []
    issues: list[OfficialParseIssue] = []
    for row in values:
        if not isinstance(row, dict):
            issues.append(OfficialParseIssue(code="sam.row_invalid"))
            continue
        notice_id = str(row.get("noticeId", "")).strip()
        solicitation = str(row.get("solicitationNumber", "")).strip()
        title = str(row.get("title", "")).strip()
        if not notice_id or not title:
            issues.append(OfficialParseIssue(code="sam.identity_missing"))
            continue
        records.append(
            OfficialRecord(
                source_id=OfficialSourceId.SAM_GOV,
                source_record_id=notice_id,
                title=title,
                published_date=str(row.get("postedDate", "")) or None,
                attributes={
                    "naics_code": _json_value(row.get("naicsCode")),
                    "notice_id": _json_value(row.get("noticeId")),
                    "solicitation_number": solicitation or None,
                    "response_deadline": _json_value(
                        row.get("responseDeadLine", row.get("reponseDeadLine"))
                    ),
                    "type": _json_value(row.get("type")),
                    "base_type": _json_value(row.get("baseType")),
                    "active": _json_value(row.get("active")),
                    "set_aside": _json_value(row.get("typeOfSetAsideDescription")),
                    "set_aside_code": _json_value(row.get("typeOfSetAside")),
                    "organization_name": _json_value(row.get("fullParentPathName")),
                    "state": _json_value(row.get("state")),
                    "description_url": _json_value(row.get("description")),
                    "award_amount": _json_value(_nested(row, "award", "amount")),
                    "award_date": _json_value(_nested(row, "award", "date")),
                    "award_number": _json_value(_nested(row, "award", "number")),
                    "awardee_name": _json_value(_nested(row, "award", "awardee", "name")),
                },
            )
        )
    return _batch(OfficialSourceId.SAM_GOV, "sam-opportunities-v2-v1", body, (), records, issues)


def _batch(
    source: OfficialSourceId,
    version: str,
    body: bytes,
    observations: tuple[OfficialObservation, ...] | list[OfficialObservation],
    records: tuple[OfficialRecord, ...] | list[OfficialRecord],
    issues: tuple[OfficialParseIssue, ...] | list[OfficialParseIssue],
) -> OfficialBatch:
    unique_observations, observation_duplicates = _dedupe_values(observations)
    unique_records, record_duplicates = _dedupe_values(records)
    duplicate_issues = [
        *(
            OfficialParseIssue(code="official.duplicate_observation")
            for _ in observation_duplicates
        ),
        *(OfficialParseIssue(code="official.duplicate_record") for _ in record_duplicates),
    ]
    return OfficialBatch(
        source_id=source,
        parser_version=version,
        response_sha256=hashlib.sha256(body).hexdigest(),
        raw_response=body,
        observations=unique_observations,
        records=unique_records,
        issues=(*issues, *duplicate_issues),
    )


def _json(body: bytes, code: str) -> Any:
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OfficialDataError(code) from error


def _object(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OfficialDataError(code)
    return value


def _string_list(value: object, code: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OfficialDataError(code)
    return value


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    normalized = str(value).strip().replace(",", "")
    if not normalized or normalized.casefold() in {"(na)", "n/a", "null", "none", "--"}:
        return None
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _json_value(value: object) -> str | int | float | bool | None:
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def _nested(value: dict[str, Any], *path: str) -> object:
    current: object = value
    for name in path:
        if not isinstance(current, dict):
            return None
        current = current.get(name)
    return current


def _dedupe_values[T: OfficialObservation | OfficialRecord](
    values: tuple[T, ...] | list[T],
) -> tuple[tuple[T, ...], tuple[T, ...]]:
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
    return tuple(unique), tuple(duplicates)
