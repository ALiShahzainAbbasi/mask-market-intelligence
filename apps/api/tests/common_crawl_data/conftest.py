"""Build a WARC gzip member byte-for-byte the way a real one is structured.

The layout (WARC header block, blank line, embedded HTTP status line,
headers, blank line, body, then a trailing WARC record terminator) was
verified against one real record downloaded from Common Crawl -- see
warc.py's module docstring.
"""

from __future__ import annotations

import gzip
from collections.abc import Callable

import pytest


def _build_warc_gzip_member(
    *,
    warc_type: str = "response",
    target_uri: str = "https://research.example.test/articles/example",
    warc_date: str | None = "2026-01-15T10:00:00Z",
    http_status: int | None = 200,
    content_type: str | None = "text/html",
    body: bytes = (
        b"<html><body><p>Fixture archived page describing dispatch "
        b"delays and manual rescheduling pain.</p></body></html>"
    ),
    include_warc_content_length: bool = True,
    include_target_uri: bool = True,
) -> bytes:
    if http_status is None:
        http_block = b""
    else:
        header_lines = [f"HTTP/1.1 {http_status} OK"]
        if content_type is not None:
            header_lines.append(f"content-type: {content_type}")
        header_lines.append(f"content-length: {len(body)}")
        http_block = "\r\n".join(header_lines).encode("ascii") + b"\r\n\r\n" + body

    warc_lines = ["WARC/1.0", f"WARC-Type: {warc_type}"]
    if warc_date is not None:
        warc_lines.append(f"WARC-Date: {warc_date}")
    if include_target_uri:
        warc_lines.append(f"WARC-Target-URI: {target_uri}")
    if include_warc_content_length:
        warc_lines.append(f"Content-Length: {len(http_block)}")
    warc_lines.append("Content-Type: application/http; msgtype=response")
    warc_head = "\r\n".join(warc_lines).encode("ascii")

    record = warc_head + b"\r\n\r\n" + http_block + b"\r\n\r\n"
    return gzip.compress(record)


@pytest.fixture
def warc_gzip_member() -> Callable[..., bytes]:
    return _build_warc_gzip_member
