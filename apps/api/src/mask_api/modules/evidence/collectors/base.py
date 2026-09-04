from typing import Protocol

from mask_api.modules.evidence.contracts import (
    CollectionRequest,
    DiscoveredResource,
    FetchedResource,
    ParsedDocument,
    SourcePolicy,
)
from mask_api.modules.evidence.domain import CollectorKind


class Collector(Protocol):
    kind: CollectorKind
    collector_version: str
    parser_version: str

    def discover(
        self, request: CollectionRequest, policy: SourcePolicy
    ) -> tuple[DiscoveredResource, ...]: ...

    def parse(
        self, resource: FetchedResource, policy: SourcePolicy
    ) -> tuple[ParsedDocument, ...]: ...


def bounded_unique_start_urls(
    request: CollectionRequest, policy: SourcePolicy
) -> tuple[DiscoveredResource, ...]:
    seen: set[str] = set()
    resources: list[DiscoveredResource] = []
    for url in request.start_urls:
        if url in seen:
            continue
        seen.add(url)
        resources.append(DiscoveredResource(url=url))
        if len(resources) == policy.max_discovered_urls:
            break
    return tuple(resources)
