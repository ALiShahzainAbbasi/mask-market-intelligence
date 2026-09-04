from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mask_api.modules.evidence.collectors.rss_atom import RssAtomCollector
from mask_api.modules.evidence.collectors.static_html import StaticHtmlCollector
from mask_api.modules.evidence.contracts import CollectionRequest, FetchedResource
from mask_api.modules.evidence.domain import CollectorKind
from mask_api.modules.evidence.errors import ParseFailure

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = datetime(2026, 9, 4, tzinfo=UTC)


def fetched(name: str, content_type: str, url: str) -> FetchedResource:
    return FetchedResource(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        body=(FIXTURES / name).read_bytes(),
        fetched_at=FETCHED_AT,
    )


def test_rss_parser_preserves_raw_provenance_and_excludes_unapproved_author(
    source_policy,
) -> None:
    resource = fetched(
        "rss_success.xml",
        "application/rss+xml; charset=utf-8",
        "https://research.example.test/feeds/rss",
    )
    documents = RssAtomCollector().parse(resource, source_policy)

    assert len(documents) == 2
    assert documents[0].external_id == "fixture-1"
    assert documents[0].source_url.endswith("/articles/scheduling")
    assert documents[0].text == "Dispatch teams lose four hours."
    assert documents[0].author_persona_hint is None
    assert documents[0].published_at == datetime(2026, 9, 2, 10, tzinfo=UTC)
    assert documents[0].raw_content.startswith(b"<item")
    assert documents[0].metadata["feed_url"] == resource.final_url


def test_atom_parser_handles_namespaces_and_iso_timestamp(source_policy) -> None:
    resource = fetched(
        "atom_success.xml",
        "application/atom+xml; charset=utf-8",
        "https://research.example.test/feeds/atom",
    )
    documents = RssAtomCollector().parse(resource, source_policy)

    assert len(documents) == 1
    assert documents[0].external_id == "urn:fixture:atom:1"
    assert documents[0].text == "Teams re-enter invoice data every week."
    assert documents[0].published_at == datetime(2026, 9, 2, 11, 30, tzinfo=UTC)


def test_empty_feed_is_a_valid_zero_document_result(source_policy) -> None:
    resource = fetched(
        "rss_empty.xml",
        "application/rss+xml",
        "https://research.example.test/feeds/empty",
    )
    assert RssAtomCollector().parse(resource, source_policy) == ()


def test_malformed_and_unsafe_feeds_are_rejected(source_policy) -> None:
    malformed = fetched(
        "feed_malformed.xml",
        "application/rss+xml",
        "https://research.example.test/feeds/broken",
    )
    with pytest.raises(ParseFailure) as failure:
        RssAtomCollector().parse(malformed, source_policy)
    assert failure.value.code == "collection.malformed_feed"

    unsafe = malformed.model_copy(update={"body": b'<!DOCTYPE rss [<!ENTITY x "unsafe">]><rss />'})
    with pytest.raises(ParseFailure) as failure:
        RssAtomCollector().parse(unsafe, source_policy)
    assert failure.value.code == "collection.unsafe_xml"


def test_static_html_parser_extracts_visible_text_and_preserves_raw(source_policy) -> None:
    policy = source_policy.model_copy(
        update={"collector_kind": CollectorKind.STATIC_HTML, "capture_author": True}
    )
    resource = fetched(
        "html_success.html",
        "text/html; charset=utf-8",
        "https://research.example.test/articles/field-service",
    )
    document = StaticHtmlCollector().parse(resource, policy)[0]

    assert document.title == "Field Service Research"
    assert document.author_persona_hint == "Fixture Author"
    assert "Operators copy job details into three systems." in document.text
    assert "secretRuntimeValue" not in document.text
    assert "Private form field" not in document.text
    assert document.raw_content == resource.body
    assert document.metadata["fetched_url"] == resource.final_url


def test_static_html_parser_survives_changed_layout_and_rejects_empty(source_policy) -> None:
    policy = source_policy.model_copy(update={"collector_kind": CollectorKind.STATIC_HTML})
    changed = fetched(
        "html_changed_layout.html",
        "text/html",
        "https://research.example.test/articles/changed",
    )
    assert (
        "Useful evidence remains visible." in StaticHtmlCollector().parse(changed, policy)[0].text
    )

    empty = fetched(
        "html_empty.html",
        "text/html",
        "https://research.example.test/articles/empty",
    )
    with pytest.raises(ParseFailure) as failure:
        StaticHtmlCollector().parse(empty, policy)
    assert failure.value.code == "collection.empty_document"


def test_discovery_is_ordered_deduplicated_and_capped(source_policy) -> None:
    policy = source_policy.model_copy(update={"max_discovered_urls": 2})
    first = "https://research.example.test/feeds/one"
    second = "https://research.example.test/feeds/two"
    request = CollectionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        organization_id=uuid4(),
        market_id=uuid4(),
        market_definition_version_id=uuid4(),
        source_policy_version_id=policy.id,
        collector_kind=CollectorKind.RSS_ATOM,
        start_urls=(first, first, second, "https://research.example.test/feeds/three"),
    )
    assert [resource.url for resource in RssAtomCollector().discover(request, policy)] == [
        first,
        second,
    ]
