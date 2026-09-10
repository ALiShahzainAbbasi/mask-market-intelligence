from __future__ import annotations

import json
from pathlib import Path

import pytest
from mask_api.modules.youtube_data.errors import YouTubeDataError
from mask_api.modules.youtube_data.parsers import (
    parse_youtube_comment_threads,
    parse_youtube_search,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_search_extracts_videos_and_flags_missing_title() -> None:
    batch = parse_youtube_search((FIXTURES / "search.json").read_bytes())

    assert len(batch.videos) == 1
    video = batch.videos[0]
    assert video.video_id == "dQw4w9WgXcQ"
    assert "dispatch software" in video.title
    assert video.channel_title == "Fixture Trade Channel"
    assert batch.next_page_token == "CAUQAA"
    assert any(issue.code == "youtube.search.title_missing" for issue in batch.issues)


def test_parse_search_rejects_malformed_json() -> None:
    with pytest.raises(YouTubeDataError) as captured:
        parse_youtube_search(b"not-json")

    assert captured.value.code == "youtube.search.response_invalid"


def test_parse_search_rejects_missing_items_field() -> None:
    with pytest.raises(YouTubeDataError) as captured:
        parse_youtube_search(b'{"nextPageToken": null}')

    assert captured.value.code == "youtube.search.items_invalid"


def test_parse_comment_threads_extracts_comments_and_flags_empty_text() -> None:
    batch = parse_youtube_comment_threads((FIXTURES / "comment_threads.json").read_bytes())

    assert len(batch.comments) == 1
    comment = batch.comments[0]
    assert comment.comment_id == "UgxFixtureThread1"
    assert comment.video_id == "dQw4w9WgXcQ"
    assert "reschedul" in comment.text
    assert comment.like_count == 12
    assert comment.reply_count == 3
    assert any(issue.code == "youtube.comment_threads.text_missing" for issue in batch.issues)


def test_parse_comment_threads_deduplicates_identical_records() -> None:
    duplicated = (FIXTURES / "comment_threads.json").read_bytes()
    payload = json.loads(duplicated)
    payload["items"].append(payload["items"][0])
    body = json.dumps(payload).encode()

    batch = parse_youtube_comment_threads(body)

    assert len(batch.comments) == 1
    assert any(issue.code == "youtube.duplicate_comment" for issue in batch.issues)


def test_parse_comment_threads_rejects_malformed_json() -> None:
    with pytest.raises(YouTubeDataError) as captured:
        parse_youtube_comment_threads(b"not-json")

    assert captured.value.code == "youtube.comment_threads.response_invalid"
