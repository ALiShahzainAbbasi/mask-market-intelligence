"""Validated request builders for the two approved YouTube Data API v3 endpoints."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import SecretStr

from mask_api.modules.youtube_data.contracts import YouTubeEndpoint, YouTubeRequestProvenance

_SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
_COMMENT_THREADS_ENDPOINT = "https://www.googleapis.com/youtube/v3/commentThreads"
_MAX_QUERY_LENGTH = 200
_MAX_RESULTS_CEILING = 50


@dataclass(frozen=True)
class YouTubeRequest:
    endpoint_id: YouTubeEndpoint
    url: str
    query: dict[str, str] = field(default_factory=dict)
    secret_query: dict[str, SecretStr] = field(default_factory=dict, repr=False)

    def provenance(self) -> YouTubeRequestProvenance:
        return YouTubeRequestProvenance(
            endpoint=self.endpoint_id,
            query=dict(sorted(self.query.items())),
            credential_fields=tuple(sorted(self.secret_query)),
        )


def youtube_search_request(
    *,
    query: str,
    api_key: SecretStr,
    max_results: int = 25,
    published_after: str | None = None,
    region_code: str = "US",
    page_token: str | None = None,
) -> YouTubeRequest:
    query = query.strip()
    if not query or len(query) > _MAX_QUERY_LENGTH:
        raise ValueError("YouTube search query must be 1-200 characters")
    if max_results < 1 or max_results > _MAX_RESULTS_CEILING:
        raise ValueError("YouTube search max results must be 1-50")
    if not re.fullmatch(r"[A-Z]{2}", region_code):
        raise ValueError("YouTube region code must be a two-letter ISO code")
    _require_secret(api_key, "YouTube API key")
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": str(max_results),
        "regionCode": region_code,
        "safeSearch": "none",
        "order": "relevance",
    }
    if published_after is not None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", published_after):
            raise ValueError("YouTube publishedAfter must be RFC 3339 UTC (YYYY-MM-DDTHH:MM:SSZ)")
        params["publishedAfter"] = published_after
    if page_token is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", page_token):
            raise ValueError("YouTube page token is invalid")
        params["pageToken"] = page_token
    return YouTubeRequest(
        endpoint_id=YouTubeEndpoint.SEARCH,
        url=_SEARCH_ENDPOINT,
        query=params,
        secret_query={"key": api_key},
    )


def youtube_comment_threads_request(
    *,
    video_id: str,
    api_key: SecretStr,
    max_results: int = 50,
    page_token: str | None = None,
) -> YouTubeRequest:
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        raise ValueError("YouTube video ID is invalid")
    if max_results < 1 or max_results > 100:
        raise ValueError("YouTube commentThreads max results must be 1-100")
    _require_secret(api_key, "YouTube API key")
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": str(max_results),
        "order": "relevance",
        "textFormat": "plainText",
    }
    if page_token is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", page_token):
            raise ValueError("YouTube page token is invalid")
        params["pageToken"] = page_token
    return YouTubeRequest(
        endpoint_id=YouTubeEndpoint.COMMENT_THREADS,
        url=_COMMENT_THREADS_ENDPOINT,
        query=params,
        secret_query={"key": api_key},
    )


def _require_secret(value: SecretStr, name: str) -> None:
    if not value.get_secret_value().strip():
        raise ValueError(f"{name} cannot be empty")
