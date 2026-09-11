from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from mask_api.modules.common_crawl_data.contracts import CommonCrawlProvenance
from mask_api.modules.common_crawl_data.integration import (
    to_normalized_document,
    to_parsed_document,
)
from mask_api.modules.evidence.contracts import CollectionRequest, FetchedResource, SourcePolicy
from mask_api.modules.evidence.domain import CollectorKind

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def resource(**changes: object) -> FetchedResource:
    values: dict[str, object] = {
        "requested_url": "https://research.example.test/articles/example",
        "final_url": "https://research.example.test/articles/example",
        "status_code": 200,
        "content_type": "text/html",
        "body": (
            b"<html><head><title>Dispatch delays</title></head>"
            b"<body><p>Contractors report losing two hours a day to manual "
            b"rescheduling.</p></body></html>"
        ),
        "fetched_at": NOW,
    }
    values.update(changes)
    return FetchedResource(**values)  # type: ignore[arg-type]


def provenance(**changes: object) -> CommonCrawlProvenance:
    values: dict[str, object] = {
        "collection_id": "CC-MAIN-2026-34",
        "original_url": "https://research.example.test/articles/example",
        "capture_timestamp": "20260115100000",
        "warc_filename": "crawl-data/CC-MAIN-2026-34/segments/x/warc/file-00001.warc.gz",
        "warc_offset": 1000,
        "warc_length": 500,
        "retrieved_at": NOW,
    }
    values.update(changes)
    return CommonCrawlProvenance(**values)  # type: ignore[arg-type]


def test_to_parsed_document_extracts_text_via_the_existing_static_html_parser(
    source_policy: SourcePolicy,
) -> None:
    document = to_parsed_document(resource(), provenance(), source_policy)

    assert document.title == "Dispatch delays"
    assert "losing two hours a day" in document.text
    assert document.source_url == "https://research.example.test/articles/example"


def test_to_parsed_document_stamps_common_crawl_provenance_into_metadata(
    source_policy: SourcePolicy,
) -> None:
    record = provenance(capture_timestamp="20250601120000")

    document = to_parsed_document(resource(), record, source_policy)

    stamped = document.metadata["common_crawl"]
    assert isinstance(stamped, dict)
    assert stamped["capture_timestamp"] == "20250601120000"
    assert stamped["warc_filename"] == record.warc_filename
    assert stamped["warc_offset"] == 1000
    assert stamped["warc_length"] == 500
    # the underlying static-HTML parser's own metadata is preserved, not replaced
    assert document.metadata["parser_family"] == "generic_static_html"


def test_to_normalized_document_uses_the_common_crawl_collector_kind(
    source_policy: SourcePolicy,
) -> None:
    request = CollectionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        organization_id=uuid4(),
        market_id=uuid4(),
        market_definition_version_id=uuid4(),
        source_policy_version_id=source_policy.id,
        collector_kind=CollectorKind.COMMON_CRAWL,
        start_urls=("https://research.example.test/articles/example",),
    )

    normalized = to_normalized_document(
        resource(), provenance(), source_policy, request, collected_at=NOW
    )

    assert normalized.collector_kind == CollectorKind.COMMON_CRAWL
    assert normalized.collected_at == NOW
    assert normalized.metadata["common_crawl"]["collection_id"] == "CC-MAIN-2026-34"
    assert "losing two hours a day" in normalized.normalized_text
