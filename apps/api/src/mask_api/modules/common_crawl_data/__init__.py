"""Targeted Common Crawl retrieval: CDX lookup, one ranged WARC-record fetch,
and reuse of the existing static-HTML parse/normalize pipeline."""

from mask_api.modules.common_crawl_data.cdx import build_cdx_request, parse_cdx_response
from mask_api.modules.common_crawl_data.contracts import CommonCrawlCapture, CommonCrawlProvenance
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.integration import (
    to_normalized_document,
    to_parsed_document,
)
from mask_api.modules.common_crawl_data.retriever import CommonCrawlRetriever, CommonCrawlSettings
from mask_api.modules.common_crawl_data.transport import (
    CommonCrawlTransport,
    UrllibCommonCrawlTransport,
)
from mask_api.modules.common_crawl_data.warc import WarcHttpRecord, parse_warc_gzip_member

__all__ = [
    "CommonCrawlCapture",
    "CommonCrawlError",
    "CommonCrawlProvenance",
    "CommonCrawlRetriever",
    "CommonCrawlSettings",
    "CommonCrawlTransport",
    "UrllibCommonCrawlTransport",
    "WarcHttpRecord",
    "build_cdx_request",
    "parse_cdx_response",
    "parse_warc_gzip_member",
    "to_normalized_document",
    "to_parsed_document",
]
