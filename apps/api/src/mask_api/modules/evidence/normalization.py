import hashlib
import re
import unicodedata
from datetime import datetime
from uuid import UUID

from mask_api.modules.evidence.contracts import (
    CollectionRequest,
    DuplicateLink,
    NormalizedDocument,
    ParsedDocument,
    SourcePolicy,
)
from mask_api.modules.evidence.domain import CollectorKind

NORMALIZER_VERSION = "text-nfkc-v1"
_HORIZONTAL_SPACE = re.compile(r"[^\S\r\n]+")
_EXCESS_NEWLINES = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        for character in normalized
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    normalized = "\n".join(
        _HORIZONTAL_SPACE.sub(" ", line).strip() for line in normalized.split("\n")
    )
    return _EXCESS_NEWLINES.sub("\n\n", normalized).strip()


def normalize_document(
    document: ParsedDocument,
    policy: SourcePolicy,
    request: CollectionRequest,
    collector_kind: CollectorKind,
    collector_version: str,
    parser_version: str,
    collected_at: datetime,
) -> NormalizedDocument:
    text = normalize_text(document.text)
    raw_hash = hashlib.sha256(document.raw_content).hexdigest()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    occurrence_material = "\x1f".join(
        (
            str(policy.source_id),
            str(policy.id),
            document.source_url,
            document.external_id or "",
            raw_hash,
        )
    )
    occurrence_key = hashlib.sha256(occurrence_material.encode("utf-8")).hexdigest()
    author = normalize_text(document.author_persona_hint or "") or None
    return NormalizedDocument(
        occurrence_key=occurrence_key,
        organization_id=request.organization_id,
        market_id=request.market_id,
        market_definition_version_id=request.market_definition_version_id,
        source_id=policy.source_id,
        source_policy_version_id=policy.id,
        source_policy_version=policy.version,
        source_url=document.source_url,
        external_id=document.external_id,
        title=normalize_text(document.title or "") or None,
        author_persona_hint=author if policy.capture_author else None,
        published_at=document.published_at,
        collected_at=collected_at,
        raw_content=document.raw_content,
        raw_content_type=document.raw_content_type,
        raw_content_sha256=raw_hash,
        normalized_text=text,
        language=document.language,
        content_hash=content_hash,
        metadata=document.metadata,
        access_class=policy.access_class,
        raw_retention_days=policy.raw_retention_days,
        collector_kind=collector_kind,
        collector_version=collector_version,
        parser_version=parser_version,
        normalizer_version=NORMALIZER_VERSION,
    )


def exact_deduplicate(
    documents: tuple[NormalizedDocument, ...],
) -> tuple[tuple[NormalizedDocument, ...], tuple[DuplicateLink, ...]]:
    canonical_by_hash: dict[str, NormalizedDocument] = {}
    canonical: list[NormalizedDocument] = []
    duplicates: list[DuplicateLink] = []
    for document in documents:
        first = canonical_by_hash.get(document.content_hash)
        if first is None:
            canonical_by_hash[document.content_hash] = document
            canonical.append(document)
            continue
        duplicates.append(
            DuplicateLink(
                duplicate_occurrence_key=document.occurrence_key,
                canonical_occurrence_key=first.occurrence_key,
                content_hash=document.content_hash,
            )
        )
    return tuple(canonical), tuple(duplicates)


def batch_idempotency_key(run_id: UUID, policy_version_id: UUID) -> str:
    return hashlib.sha256(f"{run_id}\x1f{policy_version_id}".encode()).hexdigest()
