from __future__ import annotations

import pytest
from mask_api.modules.youtube_data.contracts import YouTubeEndpoint
from mask_api.modules.youtube_data.requests import (
    youtube_comment_threads_request,
    youtube_search_request,
)
from pydantic import SecretStr

KEY = SecretStr("fixture-not-a-real-key")


def test_search_request_builds_expected_query_and_hides_credential() -> None:
    built = youtube_search_request(query="HVAC dispatch software", api_key=KEY)

    assert built.endpoint_id == YouTubeEndpoint.SEARCH
    assert built.url == "https://www.googleapis.com/youtube/v3/search"
    assert built.query["q"] == "HVAC dispatch software"
    assert built.query["type"] == "video"
    provenance = built.provenance()
    assert provenance.credential_fields == ("key",)
    assert "fixture-not-a-real-key" not in provenance.model_dump_json()


def test_search_request_accepts_published_after_and_page_token() -> None:
    built = youtube_search_request(
        query="dispatch pain",
        api_key=KEY,
        published_after="2026-01-01T00:00:00Z",
        page_token="CAUQAA",
    )

    assert built.query["publishedAfter"] == "2026-01-01T00:00:00Z"
    assert built.query["pageToken"] == "CAUQAA"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"query": "   "}, "query"),
        ({"query": "x" * 201}, "query"),
        ({"max_results": 0}, "max results"),
        ({"max_results": 51}, "max results"),
        ({"region_code": "usa"}, "region code"),
        ({"published_after": "2026-01-01"}, "publishedAfter"),
        ({"page_token": "not valid!"}, "page token"),
    ],
)
def test_search_request_rejects_invalid_input(changes: dict[str, object], match: str) -> None:
    values: dict[str, object] = {"query": "dispatch", "api_key": KEY}
    values.update(changes)
    with pytest.raises(ValueError, match=match):
        youtube_search_request(**values)  # type: ignore[arg-type]


def test_search_request_requires_a_nonempty_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        youtube_search_request(query="dispatch", api_key=SecretStr(""))


def test_comment_threads_request_builds_expected_query() -> None:
    built = youtube_comment_threads_request(video_id="dQw4w9WgXcQ", api_key=KEY)

    assert built.endpoint_id == YouTubeEndpoint.COMMENT_THREADS
    assert built.query["videoId"] == "dQw4w9WgXcQ"
    assert built.query["textFormat"] == "plainText"
    assert built.provenance().credential_fields == ("key",)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"video_id": "bad id"}, "video ID"),
        ({"max_results": 0}, "max results"),
        ({"max_results": 101}, "max results"),
        ({"page_token": "not valid!"}, "page token"),
    ],
)
def test_comment_threads_request_rejects_invalid_input(
    changes: dict[str, object], match: str
) -> None:
    values: dict[str, object] = {"video_id": "dQw4w9WgXcQ", "api_key": KEY}
    values.update(changes)
    with pytest.raises(ValueError, match=match):
        youtube_comment_threads_request(**values)  # type: ignore[arg-type]
