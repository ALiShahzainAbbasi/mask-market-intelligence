from __future__ import annotations

import json

import pytest
from mask_api.modules.common_crawl_data.cdx import build_cdx_request, parse_cdx_response
from mask_api.modules.common_crawl_data.errors import CommonCrawlError

COLLECTION = "CC-MAIN-2026-34"


def test_build_cdx_request_shapes_the_exact_index_query() -> None:
    request = build_cdx_request(
        "https://research.example.test/articles/example", COLLECTION, limit=3
    )

    assert request.collection_id == COLLECTION
    assert request.endpoint == "https://index.commoncrawl.org/CC-MAIN-2026-34-index"
    assert request.query["url"] == "https://research.example.test/articles/example"
    assert request.query["output"] == "json"
    assert request.query["matchType"] == "exact"
    assert request.query["limit"] == "3"


@pytest.mark.parametrize(
    ("collection_id", "url", "limit"),
    [
        ("bad-collection", "https://x.test/", 5),
        (COLLECTION, "", 5),
        (COLLECTION, "not-a-url", 5),
        (COLLECTION, "https://x.test/", 0),
        (COLLECTION, "https://x.test/", 101),
    ],
)
def test_build_cdx_request_rejects_invalid_input(collection_id: str, url: str, limit: int) -> None:
    with pytest.raises(ValueError):
        build_cdx_request(url, collection_id, limit=limit)


def test_parse_cdx_response_reads_newline_delimited_json() -> None:
    row_one = {
        "urlkey": "com,example)/",
        "timestamp": "20260807104456",
        "url": "https://example.com/",
        "mime": "text/html",
        "status": "200",
        "digest": "FIXTUREDIGEST",
        "length": "953",
        "offset": "177253384",
        "filename": "crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00162.warc.gz",
    }
    row_two = {**row_one, "timestamp": "20260807131537", "offset": "600744784"}
    body = (json.dumps(row_one) + "\n" + json.dumps(row_two) + "\n").encode("utf-8")

    captures = parse_cdx_response(body, COLLECTION)

    assert len(captures) == 2
    assert captures[0].collection_id == COLLECTION
    assert captures[0].warc_offset == 177253384
    assert captures[0].warc_length == 953
    assert captures[0].status == 200
    assert captures[1].timestamp == "20260807131537"


def test_parse_cdx_response_ignores_blank_lines() -> None:
    row = {
        "url": "https://example.com/",
        "timestamp": "20260807104456",
        "filename": "crawl-data/x.warc.gz",
        "offset": "1",
        "length": "10",
    }
    body = ("\n" + json.dumps(row) + "\n\n").encode("utf-8")

    captures = parse_cdx_response(body, COLLECTION)

    assert len(captures) == 1


def test_parse_cdx_response_rejects_malformed_json_line() -> None:
    with pytest.raises(CommonCrawlError) as captured:
        parse_cdx_response(b"not-json\n", COLLECTION)

    assert captured.value.code == "common_crawl.cdx_response_invalid"


def test_parse_cdx_response_rejects_a_row_missing_required_fields() -> None:
    body = json.dumps({"url": "https://example.com/"}).encode("utf-8") + b"\n"

    with pytest.raises(CommonCrawlError) as captured:
        parse_cdx_response(body, COLLECTION)

    assert captured.value.code == "common_crawl.cdx_row_invalid"


def test_parse_cdx_response_returns_empty_tuple_for_no_lines() -> None:
    assert parse_cdx_response(b"", COLLECTION) == ()
