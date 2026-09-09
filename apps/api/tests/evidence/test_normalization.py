from datetime import UTC, datetime
from uuid import uuid4

from mask_api.modules.evidence.contracts import CollectionRequest, ParsedDocument
from mask_api.modules.evidence.domain import CollectorKind
from mask_api.modules.evidence.normalization import (
    NORMALIZER_VERSION,
    PERSONA_NORMALIZER_VERSION,
    classify_declared_persona,
    exact_deduplicate,
    normalize_document,
    normalize_text,
)


def test_text_normalization_is_deterministic_and_versioned() -> None:
    value = "  Full-width: Ａ\r\n\r\n\r\nHours:\t  four\x00  "
    assert normalize_text(value) == "Full-width: A\n\nHours: four"
    assert NORMALIZER_VERSION == "text-nfkc-v1"


def test_exact_duplicates_keep_occurrences_but_one_canonical(source_policy) -> None:
    collected_at = datetime(2026, 9, 4, tzinfo=UTC)
    first = ParsedDocument(
        source_url="https://research.example.test/articles/one",
        external_id="one",
        raw_content=b"first raw form",
        raw_content_type="text/html",
        text="Same   operational pain",
        author_persona_hint="Unneeded Person",
    )
    second = first.model_copy(
        update={
            "source_url": "https://research.example.test/articles/two",
            "external_id": "two",
            "raw_content": b"second raw form",
            "text": "Same operational pain",
        }
    )
    request = CollectionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        organization_id=uuid4(),
        market_id=uuid4(),
        market_definition_version_id=uuid4(),
        source_policy_version_id=source_policy.id,
        collector_kind=CollectorKind.RSS_ATOM,
        start_urls=("https://research.example.test/feeds/rss",),
    )
    normalized = tuple(
        normalize_document(
            document,
            source_policy,
            request,
            CollectorKind.RSS_ATOM,
            "collector-v1",
            "parser-v1",
            collected_at,
        )
        for document in (first, second)
    )

    canonical, duplicate_links = exact_deduplicate(normalized)

    assert len(normalized) == 2
    assert len(canonical) == 1
    assert len(duplicate_links) == 1
    assert duplicate_links[0].canonical_occurrence_key == normalized[0].occurrence_key
    assert duplicate_links[0].duplicate_occurrence_key == normalized[1].occurrence_key
    assert duplicate_links[0].duplicate_source_family == "published_feeds"
    assert normalized[0].raw_content != normalized[1].raw_content
    assert normalized[0].author_persona_hint is None
    assert normalized[0].author_persona == "unknown"
    assert normalized[0].source_family == "published_feeds"


def test_declared_persona_is_conservative_and_versioned(source_policy) -> None:
    assert PERSONA_NORMALIZER_VERSION == "declared-persona-v1"
    assert classify_declared_persona("HVAC business owner") == "owner"
    assert classify_declared_persona("customer and vendor") == "unknown"
    assert classify_declared_persona("Jordan Smith") == "unknown"

    document = ParsedDocument(
        source_url="https://research.example.test/articles/owner",
        raw_content=b"owner statement",
        raw_content_type="text/html",
        text="Scheduling is taking too long.",
        author_persona_hint="HVAC business owner",
    )
    request = CollectionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        organization_id=uuid4(),
        market_id=uuid4(),
        market_definition_version_id=uuid4(),
        source_policy_version_id=source_policy.id,
        collector_kind=CollectorKind.RSS_ATOM,
        start_urls=("https://research.example.test/feeds/rss",),
    )
    normalized = normalize_document(
        document,
        source_policy.model_copy(update={"capture_author": True}),
        request,
        CollectorKind.RSS_ATOM,
        "collector-v1",
        "parser-v1",
        datetime(2026, 9, 4, tzinfo=UTC),
    )

    assert normalized.author_persona_hint == "HVAC business owner"
    assert normalized.author_persona == "owner"
