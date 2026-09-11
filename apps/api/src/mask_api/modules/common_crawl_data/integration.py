"""Feed a Common Crawl retrieval into the *existing* evidence pipeline.

`fetch_resource()` produces a plain `FetchedResource` -- the same contract
a live static-HTML fetch produces -- specifically so this module reuses
`StaticHtmlCollector.parse()` and `evidence.normalization.normalize_document`
unchanged rather than duplicating HTML extraction or normalization/lineage
logic. This module only adds the Common Crawl provenance record into the
resulting document's `metadata`.
"""

from __future__ import annotations

from datetime import datetime

from mask_api.modules.common_crawl_data.contracts import CommonCrawlProvenance
from mask_api.modules.evidence.collectors.static_html import StaticHtmlCollector
from mask_api.modules.evidence.contracts import (
    CollectionRequest,
    FetchedResource,
    NormalizedDocument,
    ParsedDocument,
    SourcePolicy,
)
from mask_api.modules.evidence.domain import CollectorKind
from mask_api.modules.evidence.normalization import normalize_document

COLLECTOR_VERSION = "common-crawl-targeted-v1"


def to_parsed_document(
    resource: FetchedResource, provenance: CommonCrawlProvenance, policy: SourcePolicy
) -> ParsedDocument:
    """Extract text the same way a live static-HTML fetch would, then stamp
    the result with Common Crawl provenance the caller must not discard."""
    parsed = StaticHtmlCollector().parse(resource, policy)[0]
    return parsed.model_copy(
        update={
            "metadata": {
                **parsed.metadata,
                "common_crawl": provenance.model_dump(mode="json"),
            }
        }
    )


def to_normalized_document(
    resource: FetchedResource,
    provenance: CommonCrawlProvenance,
    policy: SourcePolicy,
    request: CollectionRequest,
    collected_at: datetime,
) -> NormalizedDocument:
    parsed = to_parsed_document(resource, provenance, policy)
    return normalize_document(
        parsed,
        policy,
        request,
        CollectorKind.COMMON_CRAWL,
        COLLECTOR_VERSION,
        StaticHtmlCollector.parser_version,
        collected_at,
    )
