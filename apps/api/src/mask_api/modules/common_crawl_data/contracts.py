"""Typed records for targeted Common Crawl CDX lookup and WARC retrieval."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class CommonCrawlValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CommonCrawlCapture(CommonCrawlValue):
    """One CDX index row: where in one WARC file an archived page lives."""

    collection_id: str = Field(pattern=r"^CC-MAIN-[0-9]{4}-[0-9]{2}$")
    url: str = Field(min_length=8, max_length=2048)
    timestamp: str = Field(pattern=r"^[0-9]{14}$")
    status: int | None = Field(default=None, ge=100, le=599)
    mime: str | None = Field(default=None, max_length=200)
    warc_filename: str = Field(min_length=1, max_length=500)
    warc_offset: int = Field(ge=0)
    warc_length: int = Field(gt=0)


class CommonCrawlProvenance(CommonCrawlValue):
    """Exactly what the owner's directive requires retained per retrieval:
    original URL, crawl index/timestamp, WARC filename/offset/length, and
    our own retrieval timestamp -- never a full archive download."""

    collection_id: str = Field(pattern=r"^CC-MAIN-[0-9]{4}-[0-9]{2}$")
    original_url: str = Field(min_length=8, max_length=2048)
    capture_timestamp: str = Field(pattern=r"^[0-9]{14}$")
    warc_filename: str = Field(min_length=1, max_length=500)
    warc_offset: int = Field(ge=0)
    warc_length: int = Field(gt=0)
    retrieved_at: AwareDatetime
