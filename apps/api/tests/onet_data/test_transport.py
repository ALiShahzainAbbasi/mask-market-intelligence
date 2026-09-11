from __future__ import annotations

from dataclasses import dataclass

import pytest
from mask_api.modules.onet_data.transport import OnetTransportError, UrllibOnetTransport

URL = "https://www.onetcenter.org/dl_files/database/db_31_0_csv.zip"


class FakeHeadResponse:
    status = 200
    headers = {
        "Content-Length": "16237378",
        "Content-Type": "application/zip",
        "ETag": '"fixture-etag"',
        "Last-Modified": "Tue, 25 Aug 2026 03:47:42 GMT",
    }

    def close(self) -> None:
        return None


class FakeDownloadResponse:
    """Simulates a real stream: each read() call advances a cursor and
    returns b"" at EOF, matching http.client.HTTPResponse's contract --
    unlike returning the whole body on every call, which would hide a
    _read_fully loop bug that never terminates."""

    status = 200
    headers = {"Content-Type": "application/zip"}

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._position = 0

    def read(self, limit: int) -> bytes:
        chunk = self._body[self._position : self._position + limit]
        self._position += len(chunk)
        return chunk

    def close(self) -> None:
        return None


@dataclass
class FakeOpener:
    response: object

    def open(self, request: object, timeout: float) -> object:
        self.last_request = request
        self.last_timeout = timeout
        return self.response


def transport(response: object) -> tuple[UrllibOnetTransport, FakeOpener]:
    edge = UrllibOnetTransport()
    opener = FakeOpener(response)
    edge._opener = opener  # type: ignore[assignment]
    return edge, opener


def test_head_maps_content_length_etag_and_last_modified() -> None:
    edge, opener = transport(FakeHeadResponse())

    result = edge.head(URL, timeout_seconds=10)

    assert result.status_code == 200
    assert result.content_length == 16237378
    assert result.etag == '"fixture-etag"'
    assert result.last_modified == "Tue, 25 Aug 2026 03:47:42 GMT"
    assert opener.last_request.get_method() == "HEAD"  # type: ignore[attr-defined]


def test_download_returns_full_body_within_the_byte_cap() -> None:
    body = b"fixture zip bytes"
    edge, _ = transport(FakeDownloadResponse(body))

    result = edge.download(URL, timeout_seconds=10, max_bytes=1_000_000)

    assert result.status_code == 200
    assert result.body == body


def test_download_reassembles_a_body_delivered_across_many_small_reads() -> None:
    body = b"fixture zip bytes " * 10_000  # far bigger than one 65536-byte read chunk
    edge, _ = transport(FakeDownloadResponse(body))

    result = edge.download(URL, timeout_seconds=10, max_bytes=len(body) + 1)

    assert result.body == body


def test_download_rejects_a_body_larger_than_the_byte_cap() -> None:
    edge, _ = transport(FakeDownloadResponse(b"x" * 20))

    with pytest.raises(OnetTransportError) as captured:
        edge.download(URL, timeout_seconds=10, max_bytes=10)

    assert captured.value.code == "onet.response_too_large"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://example.com/dl_files/database/db_31_0_csv.zip",
        "http://www.onetcenter.org/dl_files/database/db_31_0_csv.zip",
        "https://www.onetcenter.org/dl_files/other/db_31_0_csv.zip",
        "https://www.onetcenter.org/dl_files/database/db_31_0_csv.tar",
    ],
)
def test_only_the_exact_onet_database_zip_origin_is_allowed(invalid_url: str) -> None:
    edge, _ = transport(FakeHeadResponse())

    with pytest.raises(OnetTransportError) as captured:
        edge.head(invalid_url, timeout_seconds=10)

    assert captured.value.code == "onet.endpoint_invalid"
