"""Parse one decompressed WARC record into its embedded HTTP response.

Structure verified against a real Common Crawl WARC record: WARC header
lines, a blank line, then (for `WARC-Type: response`) an embedded HTTP
response -- status line, headers, a blank line, and the body -- all
inside the single record. Common Crawl WARC files are concatenations of
independently gzip-compressed records, so decompressing exactly the bytes
named by one CDX row's offset/length yields exactly one such record.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass

from mask_api.modules.common_crawl_data.errors import CommonCrawlError

_MAX_HEADER_BYTES = 65_536


@dataclass(frozen=True)
class WarcHttpRecord:
    warc_type: str
    target_uri: str
    warc_date: str | None
    http_status: int
    http_content_type: str
    body: bytes


def parse_warc_gzip_member(gzip_bytes: bytes) -> WarcHttpRecord:
    try:
        decompressed = gzip.decompress(gzip_bytes)
    except OSError as error:
        raise CommonCrawlError("common_crawl.warc_not_gzip") from error
    return _parse_warc_record(decompressed)


def _parse_warc_record(data: bytes) -> WarcHttpRecord:
    warc_head, _, payload = _split_once(data)
    warc_fields = _parse_header_block(warc_head)
    warc_type = warc_fields.get("warc-type")
    target_uri = warc_fields.get("warc-target-uri")
    if warc_type is None or target_uri is None:
        raise CommonCrawlError("common_crawl.warc_headers_invalid")
    if warc_type != "response":
        raise CommonCrawlError("common_crawl.warc_type_not_response")
    # The WARC record's own Content-Length bounds the embedded HTTP
    # response; anything after it is the mandatory trailing WARC record
    # terminator (CRLF CRLF), not part of the HTTP body.
    block_length = _parse_block_length(warc_fields)
    if block_length is not None:
        payload = payload[:block_length]
    http_head, _, body = _split_once(payload)
    status = _parse_http_status(http_head)
    http_fields = _parse_header_block(http_head, skip_first_line=True)
    content_type = http_fields.get("content-type")
    if content_type is None:
        raise CommonCrawlError("common_crawl.http_headers_invalid")
    return WarcHttpRecord(
        warc_type=warc_type,
        target_uri=target_uri,
        warc_date=warc_fields.get("warc-date"),
        http_status=status,
        http_content_type=content_type,
        body=body,
    )


def _parse_block_length(warc_fields: dict[str, str]) -> int | None:
    value = warc_fields.get("content-length")
    return int(value) if value is not None and value.isdigit() else None


def _split_once(data: bytes) -> tuple[bytes, bytes, bytes]:
    for separator in (b"\r\n\r\n", b"\n\n"):
        index = data.find(separator, 0, _MAX_HEADER_BYTES)
        if index != -1:
            return data[:index], separator, data[index + len(separator) :]
    raise CommonCrawlError("common_crawl.warc_headers_invalid")


def _parse_header_block(block: bytes, *, skip_first_line: bool = False) -> dict[str, str]:
    try:
        text = block.decode("ascii")
    except UnicodeDecodeError as error:
        raise CommonCrawlError("common_crawl.warc_headers_invalid") from error
    lines = text.replace("\r\n", "\n").split("\n")
    if skip_first_line:
        lines = lines[1:]
    fields: dict[str, str] = {}
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    return fields


def _parse_http_status(http_head: bytes) -> int:
    try:
        status_line = http_head.decode("ascii").split("\n", maxsplit=1)[0].strip()
    except UnicodeDecodeError as error:
        raise CommonCrawlError("common_crawl.http_status_line_invalid") from error
    parts = status_line.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise CommonCrawlError("common_crawl.http_status_line_invalid")
    return int(parts[1])
