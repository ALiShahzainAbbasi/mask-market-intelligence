"""Deterministic parsers for bounded YouTube Data API v3 JSON responses."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from mask_api.modules.youtube_data.contracts import (
    YouTubeBatch,
    YouTubeCommentResult,
    YouTubeEndpoint,
    YouTubeParseIssue,
    YouTubeVideoResult,
)
from mask_api.modules.youtube_data.errors import YouTubeDataError


def parse_youtube_search(body: bytes) -> YouTubeBatch:
    raw = _object(_json(body, "youtube.search.response_invalid"), "youtube.search.shape_invalid")
    items = raw.get("items")
    if not isinstance(items, list):
        raise YouTubeDataError("youtube.search.items_invalid")
    videos: list[YouTubeVideoResult] = []
    issues: list[YouTubeParseIssue] = []
    for item in items:
        if not isinstance(item, dict):
            issues.append(YouTubeParseIssue(code="youtube.search.item_invalid"))
            continue
        video_id = _nested(item, "id", "videoId")
        snippet = item.get("snippet")
        if not isinstance(video_id, str) or not isinstance(snippet, dict):
            issues.append(YouTubeParseIssue(code="youtube.search.item_shape_invalid"))
            continue
        title = snippet.get("title")
        if not isinstance(title, str) or not title.strip():
            issues.append(YouTubeParseIssue(code="youtube.search.title_missing", item_id=video_id))
            continue
        videos.append(
            YouTubeVideoResult(
                video_id=video_id,
                title=title,
                description=_string_or_empty(snippet.get("description")),
                channel_id=_string_or_none(snippet.get("channelId")),
                channel_title=_string_or_none(snippet.get("channelTitle")),
                published_at=_string_or_none(snippet.get("publishedAt")),
            )
        )
    return _batch(
        YouTubeEndpoint.SEARCH,
        "youtube-search-v1",
        body,
        videos=videos,
        comments=(),
        issues=issues,
        next_page_token=_string_or_none(raw.get("nextPageToken")),
    )


def parse_youtube_comment_threads(body: bytes) -> YouTubeBatch:
    raw = _object(
        _json(body, "youtube.comment_threads.response_invalid"),
        "youtube.comment_threads.shape_invalid",
    )
    items = raw.get("items")
    if not isinstance(items, list):
        raise YouTubeDataError("youtube.comment_threads.items_invalid")
    comments: list[YouTubeCommentResult] = []
    issues: list[YouTubeParseIssue] = []
    for item in items:
        if not isinstance(item, dict):
            issues.append(YouTubeParseIssue(code="youtube.comment_threads.item_invalid"))
            continue
        thread_id = item.get("id")
        top_level = _nested(item, "snippet", "topLevelComment")
        comment_snippet = top_level.get("snippet") if isinstance(top_level, dict) else None
        video_id = item.get("videoId") or (
            _nested(item, "snippet", "videoId") if isinstance(item.get("snippet"), dict) else None
        )
        if (
            not isinstance(thread_id, str)
            or not isinstance(comment_snippet, dict)
            or not isinstance(video_id, str)
        ):
            issues.append(YouTubeParseIssue(code="youtube.comment_threads.item_shape_invalid"))
            continue
        text = comment_snippet.get("textDisplay") or comment_snippet.get("textOriginal")
        if not isinstance(text, str) or not text.strip():
            issues.append(
                YouTubeParseIssue(code="youtube.comment_threads.text_missing", item_id=thread_id)
            )
            continue
        comments.append(
            YouTubeCommentResult(
                comment_id=thread_id,
                video_id=video_id,
                text=text,
                author_display_name=_string_or_none(comment_snippet.get("authorDisplayName")),
                published_at=_string_or_none(comment_snippet.get("publishedAt")),
                like_count=_nonnegative_int_or_none(comment_snippet.get("likeCount")),
                reply_count=_nonnegative_int_or_none(_nested(item, "snippet", "totalReplyCount")),
            )
        )
    return _batch(
        YouTubeEndpoint.COMMENT_THREADS,
        "youtube-comment-threads-v1",
        body,
        videos=(),
        comments=comments,
        issues=issues,
        next_page_token=_string_or_none(raw.get("nextPageToken")),
    )


def _batch(
    endpoint: YouTubeEndpoint,
    version: str,
    body: bytes,
    *,
    videos: tuple[YouTubeVideoResult, ...] | list[YouTubeVideoResult],
    comments: tuple[YouTubeCommentResult, ...] | list[YouTubeCommentResult],
    issues: tuple[YouTubeParseIssue, ...] | list[YouTubeParseIssue],
    next_page_token: str | None,
) -> YouTubeBatch:
    unique_videos, video_duplicates = _dedupe(videos)
    unique_comments, comment_duplicates = _dedupe(comments)
    duplicate_issues = [
        *(YouTubeParseIssue(code="youtube.duplicate_video") for _ in video_duplicates),
        *(YouTubeParseIssue(code="youtube.duplicate_comment") for _ in comment_duplicates),
    ]
    return YouTubeBatch(
        endpoint=endpoint,
        parser_version=version,
        response_sha256=hashlib.sha256(body).hexdigest(),
        raw_response=body,
        videos=unique_videos,
        comments=unique_comments,
        issues=(*issues, *duplicate_issues),
        next_page_token=next_page_token,
    )


def _json(body: bytes, code: str) -> Any:
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise YouTubeDataError(code) from error


def _object(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise YouTubeDataError(code)
    return value


def _nested(value: dict[str, Any], *path: str) -> object:
    current: object = value
    for name in path:
        if not isinstance(current, dict):
            return None
        current = current.get(name)
    return current


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


def _nonnegative_int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _dedupe[T: YouTubeVideoResult | YouTubeCommentResult](
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
