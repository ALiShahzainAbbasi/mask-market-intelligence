"""Source-neutral records produced from the YouTube Data API v3."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class YouTubeEndpoint(StrEnum):
    SEARCH = "search"
    COMMENT_THREADS = "comment_threads"


class YouTubeValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class YouTubeVideoResult(YouTubeValue):
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{6,20}$")
    title: str = Field(min_length=1, max_length=2000)
    description: str = Field(max_length=10_000)
    channel_id: str | None = Field(default=None, max_length=100)
    channel_title: str | None = Field(default=None, max_length=500)
    published_at: str | None = Field(default=None, max_length=50)


class YouTubeCommentResult(YouTubeValue):
    comment_id: str = Field(min_length=1, max_length=200)
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{6,20}$")
    text: str = Field(min_length=1, max_length=10_000)
    author_display_name: str | None = Field(default=None, max_length=500)
    published_at: str | None = Field(default=None, max_length=50)
    like_count: int | None = Field(default=None, ge=0)
    reply_count: int | None = Field(default=None, ge=0)


class YouTubeParseIssue(YouTubeValue):
    code: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    item_id: str | None = None


class YouTubeBatch(YouTubeValue):
    endpoint: YouTubeEndpoint
    parser_version: str
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response: bytes = Field(repr=False)
    videos: tuple[YouTubeVideoResult, ...] = ()
    comments: tuple[YouTubeCommentResult, ...] = ()
    issues: tuple[YouTubeParseIssue, ...] = ()
    # Verified live against the real API: commentThreads.list's nextPageToken
    # can exceed 200 characters (unlike search.list's shorter tokens), so the
    # original 200-char bound -- built and tested only against fixtures --
    # was too tight for real data. 2000 is a generous, safe bound.
    next_page_token: str | None = Field(default=None, max_length=2000)


class YouTubeRequestProvenance(YouTubeValue):
    endpoint: YouTubeEndpoint
    query: dict[str, str] = Field(default_factory=dict)
    credential_fields: tuple[str, ...] = ()


class YouTubeFetchResult(YouTubeValue):
    retrieved_at: AwareDatetime
    request: YouTubeRequestProvenance
    quota_cost: int = Field(ge=0)
    batch: YouTubeBatch
