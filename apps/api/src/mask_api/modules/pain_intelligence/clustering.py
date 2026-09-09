"""Deterministic complete-linkage cosine clustering with persona isolation."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter
from decimal import Decimal

from mask_api.modules.pain_intelligence.contracts import (
    ClusteringConfiguration,
    ClusteringResult,
    ClusterMembership,
    EmbeddingVector,
    PainCluster,
    PainMention,
)
from mask_api.modules.pain_intelligence.deduplication import cosine_similarity


class ClusteringError(ValueError):
    """Clustering inputs or lineage are inconsistent."""


def cluster_mentions(
    mentions: tuple[PainMention, ...],
    vectors: tuple[EmbeddingVector, ...],
    configuration: ClusteringConfiguration,
) -> ClusteringResult:
    if len(mentions) > configuration.max_mentions:
        raise ClusteringError("clustering mention limit exceeded")
    if len({item.mention_id for item in mentions}) != len(mentions):
        raise ClusteringError("clustering mention IDs must be unique")
    market_ids = {item.market_id for item in mentions}
    if len(market_ids) > 1:
        raise ClusteringError("one clustering run cannot mix markets")
    vector_map = _vector_map(mentions, vectors)
    output: list[PainCluster] = []
    personas = sorted({mention.persona for mention in mentions}, key=lambda item: item.value)
    for persona in personas:
        group = tuple(
            sorted(
                (mention for mention in mentions if mention.persona == persona),
                key=lambda item: item.mention_id,
            )
        )
        components = _complete_linkage_components(
            group, vector_map, configuration.similarity_threshold
        )
        for component in components:
            output.append(_build_cluster(component, vector_map, configuration))
    output.sort(key=lambda item: (item.persona.value, item.cluster_id))
    return ClusteringResult(
        clustering_version=configuration.clustering_version,
        algorithm=configuration.algorithm,
        algorithm_version=configuration.algorithm_version,
        input_sha256=_input_hash(mentions, vectors, configuration),
        clusters=tuple(output),
    )


def _complete_linkage_components(
    mentions: tuple[PainMention, ...],
    vectors: dict[str, EmbeddingVector],
    threshold: Decimal,
) -> list[tuple[PainMention, ...]]:
    active: dict[str, tuple[PainMention, ...]] = {
        mention.mention_id: (mention,) for mention in mentions
    }
    similarities: dict[tuple[str, str], Decimal] = {}
    candidates: list[tuple[Decimal, tuple[str, ...], str, str]] = []
    keys = sorted(active)
    for left_index, left in enumerate(keys):
        for right in keys[left_index + 1 :]:
            similarity = cosine_similarity(vectors[left], vectors[right])
            similarities[(left, right)] = similarity
            if similarity >= threshold:
                heapq.heappush(
                    candidates,
                    (-similarity, tuple(sorted((left, right))), left, right),
                )
    while candidates:
        negative_similarity, _, left, right = heapq.heappop(candidates)
        if left not in active or right not in active:
            continue
        pair = _pair(left, right)
        if similarities.get(pair) != -negative_similarity:
            continue
        merged_mentions = tuple(
            sorted((*active.pop(left), *active.pop(right)), key=lambda item: item.mention_id)
        )
        merged_key = hashlib.sha256(
            "\x1f".join(item.mention_id for item in merged_mentions).encode("ascii")
        ).hexdigest()
        others = sorted(active)
        active[merged_key] = merged_mentions
        for other in others:
            similarity = min(
                similarities[_pair(left, other)],
                similarities[_pair(right, other)],
            )
            similarities[_pair(merged_key, other)] = similarity
            if similarity >= threshold:
                identity = tuple(
                    sorted(item.mention_id for item in (*merged_mentions, *active[other]))
                )
                first, second = _pair(merged_key, other)
                heapq.heappush(candidates, (-similarity, identity, first, second))
    return sorted(
        active.values(),
        key=lambda component: tuple(item.mention_id for item in component),
    )


def _pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _build_cluster(
    mentions: tuple[PainMention, ...],
    vectors: dict[str, EmbeddingVector],
    configuration: ClusteringConfiguration,
) -> PainCluster:
    is_outlier = len(mentions) < configuration.min_cluster_size
    ids = tuple(item.mention_id for item in mentions)
    cluster_payload = json.dumps(
        [
            configuration.model_dump(mode="json"),
            mentions[0].persona.value,
            ids,
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    cluster_id = hashlib.sha256(cluster_payload.encode("utf-8")).hexdigest()
    memberships = tuple(
        ClusterMembership(
            mention_id=mention.mention_id,
            membership_score=_membership_score(mention, mentions, vectors),
            is_outlier=is_outlier,
        )
        for mention in mentions
    )
    categories = Counter(item.pain_category for item in mentions if item.pain_category)
    if categories:
        highest = max(categories.values())
        label = min(name for name, count in categories.items() if count == highest)
    else:
        label = "Uncategorized pain"
    return PainCluster(
        cluster_id=cluster_id,
        persona=mentions[0].persona,
        display_label=label,
        memberships=memberships,
        is_outlier=is_outlier,
    )


def _membership_score(
    mention: PainMention,
    cluster: tuple[PainMention, ...],
    vectors: dict[str, EmbeddingVector],
) -> Decimal:
    peers = tuple(item for item in cluster if item.mention_id != mention.mention_id)
    if not peers:
        return Decimal("1")
    similarities = tuple(
        cosine_similarity(vectors[mention.mention_id], vectors[peer.mention_id]) for peer in peers
    )
    return sum(similarities, Decimal("0")) / Decimal(len(similarities))


def _vector_map(
    mentions: tuple[PainMention, ...],
    vectors: tuple[EmbeddingVector, ...],
) -> dict[str, EmbeddingVector]:
    mention_ids = {item.mention_id for item in mentions}
    vector_ids = {item.mention_id for item in vectors}
    if mention_ids != vector_ids or len(vector_ids) != len(vectors):
        raise ClusteringError("clustering mentions and embeddings must match exactly")
    dimensions = {item.dimensions for item in vectors}
    lineage = {(item.provider, item.model_reference, item.embedding_version) for item in vectors}
    if len(dimensions) > 1 or len(lineage) > 1:
        raise ClusteringError("one clustering run requires one embedding lineage")
    return {item.mention_id: item for item in vectors}


def _input_hash(
    mentions: tuple[PainMention, ...],
    vectors: tuple[EmbeddingVector, ...],
    configuration: ClusteringConfiguration,
) -> str:
    payload = {
        "configuration": configuration.model_dump(mode="json"),
        "mentions": [
            item.model_dump(mode="json")
            for item in sorted(mentions, key=lambda value: value.mention_id)
        ],
        "vectors": [
            item.model_dump(mode="json")
            for item in sorted(vectors, key=lambda value: value.mention_id)
        ],
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
