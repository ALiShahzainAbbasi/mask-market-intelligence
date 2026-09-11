from __future__ import annotations

import gzip
from collections.abc import Callable

import pytest
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.warc import parse_warc_gzip_member


def test_parses_target_uri_date_status_content_type_and_exact_body(
    warc_gzip_member: Callable[..., bytes],
) -> None:
    record = parse_warc_gzip_member(warc_gzip_member())

    assert record.warc_type == "response"
    assert record.target_uri == "https://research.example.test/articles/example"
    assert record.warc_date == "2026-01-15T10:00:00Z"
    assert record.http_status == 200
    assert record.http_content_type == "text/html"
    assert record.body == (
        b"<html><body><p>Fixture archived page describing dispatch "
        b"delays and manual rescheduling pain.</p></body></html>"
    )


def test_body_excludes_the_trailing_warc_record_terminator(
    warc_gzip_member: Callable[..., bytes],
) -> None:
    record = parse_warc_gzip_member(warc_gzip_member(body=b"exact-body"))

    assert record.body == b"exact-body"


def test_rejects_a_non_gzip_payload() -> None:
    with pytest.raises(CommonCrawlError) as captured:
        parse_warc_gzip_member(b"not gzip data")

    assert captured.value.code == "common_crawl.warc_not_gzip"


def test_rejects_a_non_response_warc_type(warc_gzip_member: Callable[..., bytes]) -> None:
    gzip_bytes = warc_gzip_member(warc_type="warcinfo", http_status=None)

    with pytest.raises(CommonCrawlError) as captured:
        parse_warc_gzip_member(gzip_bytes)

    assert captured.value.code == "common_crawl.warc_type_not_response"


def test_rejects_a_record_missing_target_uri(warc_gzip_member: Callable[..., bytes]) -> None:
    gzip_bytes = warc_gzip_member(include_target_uri=False)

    with pytest.raises(CommonCrawlError) as captured:
        parse_warc_gzip_member(gzip_bytes)

    assert captured.value.code == "common_crawl.warc_headers_invalid"


def test_rejects_a_malformed_http_status_line() -> None:
    http_block = b"NOT-AN-HTTP-STATUS\r\n\r\nbody"
    record = (
        b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: https://x.test/\r\n"
        b"Content-Length: "
        + str(len(http_block)).encode("ascii")
        + b"\r\n\r\n"
        + http_block
        + b"\r\n\r\n"
    )
    gzip_bytes = gzip.compress(record)

    with pytest.raises(CommonCrawlError) as captured:
        parse_warc_gzip_member(gzip_bytes)

    assert captured.value.code == "common_crawl.http_status_line_invalid"


def test_rejects_a_response_missing_content_type(warc_gzip_member: Callable[..., bytes]) -> None:
    gzip_bytes = warc_gzip_member(content_type=None)

    with pytest.raises(CommonCrawlError) as captured:
        parse_warc_gzip_member(gzip_bytes)

    assert captured.value.code == "common_crawl.http_headers_invalid"
