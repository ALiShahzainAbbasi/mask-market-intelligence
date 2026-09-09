"""Deterministic exact and embedding-assisted near deduplication."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.pain_intelligence.contracts import (
    DeduplicationResult,
    DuplicateKind,
    EmbeddingVector,
    PainDuplicateLink,
    PainMention,
)


class DeduplicationError(ValueError):
    """Mention/vector lineage is inconsistent."""


def exact_deduplicate(mentions: tuple[PainMention, ...]) -> DeduplicationResult:
    retained: list[PainMention] = []
    links: list[PainDuplicateLink] = []
    by_key: dict[tuple[str, str, str], PainMention] = {}
    for mention in sorted(mentions, key=lambda item: item.mention_id):
        key = (
            mention.persona.value,
            mention.normalized_document_sha256,
            mention.normalized_pain_sha256,
        )
        canonical = by_key.get(key)
        if canonical is None:
            by_key[key] = mention
            retained.append(mention)
        else:
            links.append(
                PainDuplicateLink(
                    duplicate_kind=DuplicateKind.EXACT,
                    retained_mention_id=canonical.mention_id,
                    duplicate_mention_id=mention.mention_id,
                    similarity=Decimal("1"),
                )
            )
    return DeduplicationResult(retained_mentions=tuple(retained), links=tuple(links))


def near_deduplicate(
    mentions: tuple[PainMention, ...],
    vectors: tuple[EmbeddingVector, ...],
    *,
    threshold: Decimal,
) -> DeduplicationResult:
    if threshold < 0 or threshold > 1:
        raise DeduplicationError("near-duplicate threshold must be within 0 and 1")
    by_id = _vectors_by_mention(mentions, vectors)
    retained: list[PainMention] = []
    links: list[PainDuplicateLink] = []
    for mention in sorted(mentions, key=lambda item: item.mention_id):
        candidates: list[tuple[Decimal, PainMention]] = []
        for canonical in retained:
            if canonical.persona != mention.persona:
                continue
            similarity = cosine_similarity(by_id[mention.mention_id], by_id[canonical.mention_id])
            if similarity >= threshold:
                candidates.append((similarity, canonical))
        if not candidates:
            retained.append(mention)
            continue
        similarity, canonical = min(
            candidates,
            key=lambda item: (-item[0], item[1].mention_id),
        )
        links.append(
            PainDuplicateLink(
                duplicate_kind=DuplicateKind.NEAR,
                retained_mention_id=canonical.mention_id,
                duplicate_mention_id=mention.mention_id,
                similarity=similarity,
            )
        )
    return DeduplicationResult(retained_mentions=tuple(retained), links=tuple(links))


def cosine_similarity(left: EmbeddingVector, right: EmbeddingVector) -> Decimal:
    if left.dimensions != right.dimensions:
        raise DeduplicationError("embedding dimensions must match")
    dot = sum(
        left_value * right_value
        for left_value, right_value in zip(left.values, right.values, strict=True)
    )
    left_norm = sum(value * value for value in left.values) ** 0.5
    right_norm = sum(value * value for value in right.values) ** 0.5
    if left_norm == 0 or right_norm == 0:
        raise DeduplicationError("embedding vector cannot have zero norm")
    similarity = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
    return Decimal(f"{max(0.0, similarity):.12f}")


def _vectors_by_mention(
    mentions: tuple[PainMention, ...],
    vectors: tuple[EmbeddingVector, ...],
) -> dict[str, EmbeddingVector]:
    mention_ids = {item.mention_id for item in mentions}
    vector_ids = {item.mention_id for item in vectors}
    if len(vector_ids) != len(vectors) or mention_ids != vector_ids:
        raise DeduplicationError("mentions and embeddings must match exactly")
    return {item.mention_id: item for item in vectors}
