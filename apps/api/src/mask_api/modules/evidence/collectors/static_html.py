from mask_api.modules.evidence.collectors.base import bounded_unique_start_urls
from mask_api.modules.evidence.collectors.html_text import VisibleHtmlParser
from mask_api.modules.evidence.collectors.parsing import decode_resource
from mask_api.modules.evidence.contracts import (
    CollectionRequest,
    DiscoveredResource,
    FetchedResource,
    ParsedDocument,
    SourcePolicy,
)
from mask_api.modules.evidence.domain import CollectorKind
from mask_api.modules.evidence.errors import ParseFailure
from mask_api.modules.evidence.normalization import normalize_text
from mask_api.modules.evidence.policy import require_safe_reference_url


class StaticHtmlCollector:
    kind = CollectorKind.STATIC_HTML
    collector_version = "static-html-v1"
    parser_version = "stdlib-html-v1"

    def discover(
        self, request: CollectionRequest, policy: SourcePolicy
    ) -> tuple[DiscoveredResource, ...]:
        return bounded_unique_start_urls(request, policy)

    def parse(self, resource: FetchedResource, policy: SourcePolicy) -> tuple[ParsedDocument, ...]:
        html = decode_resource(resource)
        parser = VisibleHtmlParser()
        try:
            parser.feed(html)
            parser.close()
        except (ValueError, AssertionError) as exc:
            raise ParseFailure(
                "collection.malformed_html",
                "The HTML response could not be parsed safely.",
            ) from exc
        text = normalize_text("".join(parser.text_parts))
        if not text:
            raise ParseFailure(
                "collection.empty_document",
                "The HTML response contained no usable visible text.",
            )
        canonical_url = require_safe_reference_url(
            parser.canonical_url or resource.final_url, resource.final_url
        )
        return (
            ParsedDocument(
                source_url=canonical_url,
                external_id=canonical_url,
                title=(normalize_text("".join(parser.title_parts))[:1000] or None),
                author_persona_hint=(normalize_text(parser.author or "")[:500] or None),
                raw_content=resource.body,
                raw_content_type=resource.content_type,
                text=text,
                metadata={
                    "fetched_url": resource.final_url,
                    "parser_family": "generic_static_html",
                    "excluded_fields": [
                        "scripts",
                        "styles",
                        "forms",
                        "response_cookies",
                        "response_headers_except_lineage",
                    ],
                },
            ),
        )
