"""Validated request builders for the five approved official APIs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import SecretStr

from mask_api.modules.official_data.contracts import OfficialRequestProvenance, OfficialSourceId


@dataclass(frozen=True)
class OfficialRequest:
    source_id: OfficialSourceId
    method: Literal["GET", "POST"]
    endpoint: str
    query: dict[str, str] = field(default_factory=dict)
    secret_query: dict[str, SecretStr] = field(default_factory=dict, repr=False)
    json_body: dict[str, object] | None = None
    secret_body: dict[str, SecretStr] = field(default_factory=dict, repr=False)

    def provenance(self) -> OfficialRequestProvenance:
        return OfficialRequestProvenance(
            source_id=self.source_id,
            method=self.method,
            endpoint=self.endpoint,
            query=dict(sorted(self.query.items())),
            body=self.json_body,
            credential_fields=tuple(sorted((*self.secret_query, *self.secret_body))),
        )


def census_cbp_request(
    *,
    year: int,
    naics: int,
    employment_size: str,
    geography: str,
    api_key: SecretStr,
    naics_field: Literal["NAICS2017", "NAICS2022"] = "NAICS2017",
) -> OfficialRequest:
    if year < 2017 or year > 2100:
        raise ValueError("unsupported Census CBP year")
    _require_secret(api_key, "Census API key")
    if naics < 11 or naics > 999_999:
        raise ValueError("NAICS must contain two to six digits")
    if not re.fullmatch(r"[0-9]{3}", employment_size):
        raise ValueError("employment size must be a three-digit Census code")
    if not re.fullmatch(
        r"(?:us|state|county"
        r"|metropolitan statistical area/micropolitan statistical area):[0-9*]{1,3}",
        geography,
    ):
        raise ValueError("unsupported Census geography")
    return OfficialRequest(
        source_id=OfficialSourceId.CENSUS_CBP,
        method="GET",
        endpoint=f"https://api.census.gov/data/{year}/cbp",
        query={
            "get": f"NAME,{naics_field},{naics_field}_LABEL,EMPSZES,ESTAB,EMP,PAYANN",
            naics_field: str(naics),
            "EMPSZES": employment_size,
            "for": geography,
        },
        secret_query={"key": api_key},
    )


def bls_request(
    *,
    series_ids: tuple[str, ...],
    start_year: int,
    end_year: int,
    registration_key: SecretStr | None = None,
) -> OfficialRequest:
    series_limit = 50 if registration_key is not None else 25
    year_limit = 19 if registration_key is not None else 9
    if not series_ids or len(series_ids) > series_limit:
        raise ValueError(f"BLS requires between 1 and {series_limit} series IDs")
    if any(not re.fullmatch(r"[A-Z0-9_#-]+", value) for value in series_ids):
        raise ValueError("BLS series IDs contain unsupported characters")
    if start_year < 1900 or end_year < start_year or end_year - start_year > year_limit:
        raise ValueError(
            f"BLS year range must be ordered and no longer than {year_limit + 1} years"
        )
    if registration_key is not None:
        _require_secret(registration_key, "BLS registration key")
    return OfficialRequest(
        source_id=OfficialSourceId.BLS,
        method="POST",
        endpoint="https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json_body={
            "seriesid": list(series_ids),
            "startyear": str(start_year),
            "endyear": str(end_year),
            "catalog": False,
            "calculations": False,
            "annualaverage": registration_key is not None,
            "aspects": False,
        },
        secret_body={} if registration_key is None else {"registrationkey": registration_key},
    )


def bea_regional_request(
    *,
    table_name: str,
    line_code: int,
    geography: str,
    year: int,
    api_key: SecretStr,
) -> OfficialRequest:
    if not re.fullmatch(r"[A-Z0-9]{2,30}", table_name):
        raise ValueError("BEA table name is invalid")
    if line_code < 1 or year < 1900 or year > 2100:
        raise ValueError("BEA line code or year is invalid")
    if not re.fullmatch(r"[A-Z0-9,*]{2,100}", geography):
        raise ValueError("BEA geography is invalid")
    _require_secret(api_key, "BEA API key")
    return OfficialRequest(
        source_id=OfficialSourceId.BEA,
        method="GET",
        endpoint="https://apps.bea.gov/api/data/",
        query={
            "method": "GetData",
            "datasetname": "Regional",
            "TableName": table_name,
            "LineCode": str(line_code),
            "GeoFIPS": geography,
            "Year": str(year),
            "ResultFormat": "JSON",
        },
        secret_query={"UserID": api_key},
    )


def sec_submissions_request(*, cik: int) -> OfficialRequest:
    if cik < 1 or cik > 9_999_999_999:
        raise ValueError("SEC CIK is invalid")
    return OfficialRequest(
        source_id=OfficialSourceId.SEC_EDGAR,
        method="GET",
        endpoint=f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
    )


def sam_opportunities_request(
    *,
    posted_from: str,
    posted_to: str,
    naics: int,
    limit: int,
    offset: int,
    api_key: SecretStr,
) -> OfficialRequest:
    try:
        start = datetime.strptime(posted_from, "%m/%d/%Y")
        end = datetime.strptime(posted_to, "%m/%d/%Y")
    except ValueError as error:
        raise ValueError("SAM dates must use MM/DD/YYYY") from error
    if len(posted_from) != 10 or len(posted_to) != 10:
        raise ValueError("SAM dates must use MM/DD/YYYY")
    if start > end or (end - start).days > 366:
        raise ValueError("SAM posted date range must be ordered and no longer than one year")
    if naics < 11 or naics > 999_999 or limit < 1 or limit > 1000 or offset < 0:
        raise ValueError("SAM query limits or NAICS are invalid")
    _require_secret(api_key, "SAM API key")
    return OfficialRequest(
        source_id=OfficialSourceId.SAM_GOV,
        method="GET",
        endpoint="https://api.sam.gov/opportunities/v2/search",
        query={
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "ncode": str(naics),
            "limit": str(limit),
            "offset": str(offset),
        },
        secret_query={"api_key": api_key},
    )


def usaspending_award_search_request(
    *,
    naics_codes: tuple[str, ...],
    start_date: str,
    end_date: str,
    limit: int = 10,
    page: int = 1,
) -> OfficialRequest:
    if not naics_codes or len(naics_codes) > 10:
        raise ValueError("USAspending requires between 1 and 10 NAICS codes")
    if any(not re.fullmatch(r"[0-9]{2,6}", code) for code in naics_codes):
        raise ValueError("USAspending NAICS codes must contain two to six digits")
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("USAspending dates must use YYYY-MM-DD") from error
    if start > end or (end - start).days > 366 * 5:
        raise ValueError("USAspending date range must be ordered and no longer than five years")
    if limit < 1 or limit > 100 or page < 1:
        raise ValueError("USAspending limit or page is invalid")
    return OfficialRequest(
        source_id=OfficialSourceId.USASPENDING,
        method="POST",
        endpoint="https://api.usaspending.gov/api/v2/search/spending_by_award/",
        json_body={
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [{"start_date": start_date, "end_date": end_date}],
                "naics_codes": {"require": list(naics_codes)},
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Start Date",
                "End Date",
                "Description",
                "NAICS",
                "Awarding Agency",
                "generated_internal_id",
            ],
            "limit": limit,
            "page": page,
            "sort": "Award Amount",
            "order": "desc",
            "subawards": False,
            "spending_level": "awards",
        },
    )


def _require_secret(value: SecretStr, name: str) -> None:
    if not value.get_secret_value().strip():
        raise ValueError(f"{name} cannot be empty")
