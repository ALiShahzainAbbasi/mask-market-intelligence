"""Source-neutral records produced from official API responses."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue


class OfficialSourceId(StrEnum):
    CENSUS_CBP = "census_cbp"
    BLS = "bls"
    BEA = "bea"
    SEC_EDGAR = "sec_edgar"
    SAM_GOV = "sam_gov"


class OfficialValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class OfficialObservation(OfficialValue):
    source_id: OfficialSourceId
    source_record_id: str = Field(min_length=1, max_length=500)
    metric: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    value: Decimal
    unit: str = Field(min_length=1, max_length=100)
    period: str | None = Field(default=None, max_length=100)
    geography: str | None = Field(default=None, max_length=500)
    industry_code: str | None = Field(default=None, max_length=20)
    label: str | None = Field(default=None, max_length=1000)


class OfficialRecord(OfficialValue):
    source_id: OfficialSourceId
    source_record_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=2000)
    published_date: str | None = Field(default=None, max_length=50)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class OfficialParseIssue(OfficialValue):
    code: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    source_record_id: str | None = None


class OfficialBatch(OfficialValue):
    source_id: OfficialSourceId
    parser_version: str
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response: bytes = Field(repr=False)
    observations: tuple[OfficialObservation, ...] = ()
    records: tuple[OfficialRecord, ...] = ()
    issues: tuple[OfficialParseIssue, ...] = ()


class OfficialRequestProvenance(OfficialValue):
    source_id: OfficialSourceId
    method: str = Field(pattern=r"^(GET|POST)$")
    endpoint: str = Field(min_length=8, max_length=2048)
    query: dict[str, str] = Field(default_factory=dict)
    body: dict[str, JsonValue] | None = None
    credential_fields: tuple[str, ...] = ()


class OfficialFetchResult(OfficialValue):
    retrieved_at: AwareDatetime
    request: OfficialRequestProvenance
    batch: OfficialBatch
