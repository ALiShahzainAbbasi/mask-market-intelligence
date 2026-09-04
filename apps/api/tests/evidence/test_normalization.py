from datetime import UTC, datetime
from uuid import uuid4

from mask_api.modules.evidence.contracts import CollectionRequest, ParsedDocument
from mask_api.modules.evidence.domain import CollectorKind
from mask_api.modules.evidence.normalization import (
    NORMALIZER_VERSION,
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
    assert normalized[0].raw_content != normalized[1].raw_content
    assert normalized[0].author_persona_hint is None
