from __future__ import annotations

from dataclasses import dataclass

import pytest
from mask_api.modules.common_crawl_data.cdx import CdxRequest, build_cdx_request
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.transport import UrllibCommonCrawlTransport


class FakeCdxResponse:
    status = 200
    headers = {"Content-Type": "text/x-ndjson"}

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._position = 0

    def read(self, limit: int) -> bytes:
        chunk = self._body[self._position : self._position + limit]
        self._position += len(chunk)
        return chunk

    def close(self) -> None:
        return None


class FakeWarcResponse(FakeCdxResponse):
    status = 206
    headers = {"Content-Type": "binary/octet-stream"}


@dataclass
class FakeOpener:
    response: object

    def open(self, request: object, timeout: float) -> object:
        self.last_request = request
        self.last_timeout = timeout
        return self.response


def transport(response: object) -> tuple[UrllibCommonCrawlTransport, FakeOpener]:
    edge = UrllibCommonCrawlTransport()
    opener = FakeOpener(response)
    edge._opener = opener  # type: ignore[assignment]
    return edge, opener


def test_query_cdx_sends_a_get_to_the_index_host_with_the_encoded_query() -> None:
    edge, opener = transport(FakeCdxResponse(b'{"url": "https://x.test/"}\n'))
    request = build_cdx_request("https://research.example.test/articles/x", "CC-MAIN-2026-34")

    result = edge.query_cdx(request, timeout_seconds=10, max_bytes=100_000)

    assert result.status_code == 200
    assert result.content_type == "text/x-ndjson"
    sent = opener.last_request
    assert sent.full_url.startswith(  # type: ignore[attr-defined]
        "https://index.commoncrawl.org/CC-MAIN-2026-34-index?"
    )
    assert sent.get_method() == "GET"  # type: ignore[attr-defined]


def test_query_cdx_rejects_a_non_cdx_host_endpoint() -> None:
    edge, _ = transport(FakeCdxResponse(b""))
    forged = CdxRequest(
        collection_id="CC-MAIN-2026-34",
        endpoint="https://evil.test/CC-MAIN-2026-34-index",
        query={"url": "https://x.test/"},
    )

    with pytest.raises(CommonCrawlError) as captured:
        edge.query_cdx(forged, timeout_seconds=10, max_bytes=100_000)

    assert captured.value.code == "common_crawl.cdx_endpoint_invalid"


def test_fetch_warc_range_sends_the_exact_byte_range_header() -> None:
    edge, opener = transport(FakeWarcResponse(b"fixture warc bytes"))

    result = edge.fetch_warc_range(
        "crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00162.warc.gz",
        177253384,
        953,
        timeout_seconds=10,
        max_bytes=100_000,
    )

    assert result.status_code == 206
    assert result.body == b"fixture warc bytes"
    sent = opener.last_request
    headers = {key.casefold(): value for key, value in sent.header_items()}  # type: ignore[attr-defined]
    assert headers["range"] == "bytes=177253384-177254336"
    assert sent.full_url == (  # type: ignore[attr-defined]
        "https://data.commoncrawl.org/crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00162.warc.gz"
    )


@pytest.mark.parametrize(
    ("filename", "offset", "length"),
    [
        ("../escape.warc.gz", 0, 10),
        ("\\escape.warc.gz", 0, 10),
        ("/absolute.warc.gz", 0, 10),
        ("valid.warc.gz", -1, 10),
        ("valid.warc.gz", 0, 0),
        ("valid.warc.gz", 0, 200_000_000),
    ],
)
def test_fetch_warc_range_rejects_unsafe_or_invalid_input(
    filename: str, offset: int, length: int
) -> None:
    edge, _ = transport(FakeWarcResponse(b""))

    with pytest.raises(CommonCrawlError):
        edge.fetch_warc_range(filename, offset, length, timeout_seconds=10, max_bytes=100_000)
