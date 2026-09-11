"""Typed records for the downloadable O*NET database (occupations and tasks)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class OnetValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class OnetTaskType(StrEnum):
    CORE = "Core"
    SUPPLEMENTAL = "Supplemental"


class OnetDatasetDescriptor(OnetValue):
    """What was actually downloaded, and how to tell if it changed.

    O*NET does not publish an independent checksum for its database
    releases, so `sha256` is self-computed over the downloaded bytes for
    local integrity verification (detecting on-disk corruption on a later
    read), not verification against a publisher-supplied value. `etag` and
    `content_length` are the server's own change signal, used to skip a
    redundant download when a cached copy already matches.
    """

    version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    source_url: str = Field(min_length=8, max_length=2048)
    content_length: int = Field(gt=0)
    etag: str | None = Field(default=None, max_length=200)
    last_modified: str | None = Field(default=None, max_length=100)
    retrieved_at: AwareDatetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_filename: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,200}$")


class OnetOccupation(OnetValue):
    onet_soc_code: str = Field(pattern=r"^[0-9]{2}-[0-9]{4}\.[0-9]{2}$")
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4_000)


class OnetTaskStatement(OnetValue):
    onet_soc_code: str = Field(pattern=r"^[0-9]{2}-[0-9]{4}\.[0-9]{2}$")
    task_id: int = Field(gt=0)
    task: str = Field(min_length=1, max_length=2_000)
    task_type: OnetTaskType | None = None
    incumbents_responding: int | None = Field(default=None, ge=0)
    date: str | None = Field(default=None, max_length=20)
    domain_source: str | None = Field(default=None, max_length=200)


class OnetParseIssue(OnetValue):
    code: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    row_number: int | None = Field(default=None, ge=1)


class OnetImportBatch(OnetValue):
    descriptor: OnetDatasetDescriptor
    occupations: tuple[OnetOccupation, ...] = ()
    task_statements: tuple[OnetTaskStatement, ...] = ()
    issues: tuple[OnetParseIssue, ...] = ()
