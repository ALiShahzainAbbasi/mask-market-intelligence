from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from mask_api.modules.evidence.collectors.base import bounded_unique_start_urls
from mask_api.modules.evidence.collectors.html_text import visible_html_text
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

_FORBIDDEN_XML_MARKERS = ("<!DOCTYPE", "<!ENTITY")
_MAX_XML_ELEMENTS = 5000


class RssAtomCollector:
    kind = CollectorKind.RSS_ATOM
    collector_version = "rss-atom-v1"
    parser_version = "stdlib-xml-v1"

    def discover(
        self, request: CollectionRequest, policy: SourcePolicy
    ) -> tuple[DiscoveredResource, ...]:
        return bounded_unique_start_urls(request, policy)

    def parse(self, resource: FetchedResource, policy: SourcePolicy) -> tuple[ParsedDocument, ...]:
        xml = decode_resource(resource)
        upper_xml = xml.upper()
        if any(marker in upper_xml for marker in _FORBIDDEN_XML_MARKERS):
            raise ParseFailure(
                "collection.unsafe_xml",
                "The feed contains a prohibited XML declaration.",
            )
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ParseFailure(
                "collection.malformed_feed",
                "The feed response is not valid RSS or Atom XML.",
            ) from exc
        elements = list(root.iter())
        if len(elements) > _MAX_XML_ELEMENTS:
            raise ParseFailure(
                "collection.feed_too_complex",
                "The feed contains too many XML elements.",
            )
        root_name = _local_name(root.tag).lower()
        if root_name == "feed":
            return self._parse_atom(root, resource, policy)
        if root_name in {"rss", "rdf"}:
            return self._parse_rss(root, resource, policy)
        raise ParseFailure(
            "collection.unsupported_feed",
            "The XML response is not a supported RSS or Atom feed.",
        )

    def _parse_rss(
        self, root: Element, resource: FetchedResource, policy: SourcePolicy
    ) -> tuple[ParsedDocument, ...]:
        documents: list[ParsedDocument] = []
        for item in (element for element in root.iter() if _local_name(element.tag) == "item"):
            title = _child_text(item, "title")
            link = _child_text(item, "link") or resource.final_url
            external_id = _child_text(item, "guid") or link
            raw_text = _child_text(item, "encoded") or _child_text(item, "description") or ""
            text = normalize_text(visible_html_text(raw_text) or raw_text)
            if not text:
                continue
            documents.append(
                ParsedDocument(
                    source_url=require_safe_reference_url(link, resource.final_url),
                    external_id=external_id[:500] if external_id else None,
                    title=normalize_text(title or "")[:1000] or None,
                    author_persona_hint=_permitted_author(item, policy),
                    published_at=_parse_timestamp(
                        _child_text(item, "pubDate") or _child_text(item, "date")
                    ),
                    raw_content=ElementTree.tostring(item, encoding="utf-8"),
                    raw_content_type="application/xml",
                    text=text,
                    metadata={
                        "feed_type": "rss",
                        "feed_url": resource.final_url,
                        "categories": _child_texts(item, "category", limit=20),
                    },
                )
            )
        return tuple(documents)

    def _parse_atom(
        self, root: Element, resource: FetchedResource, policy: SourcePolicy
    ) -> tuple[ParsedDocument, ...]:
        documents: list[ParsedDocument] = []
        for entry in (element for element in root if _local_name(element.tag) == "entry"):
            title = _child_text(entry, "title")
            link = _atom_link(entry) or resource.final_url
            external_id = _child_text(entry, "id") or link
            content = _child(entry, "content")
            if content is None:
                content = _child(entry, "summary")
            raw_text = "" if content is None else "".join(content.itertext())
            text = normalize_text(visible_html_text(raw_text) or raw_text)
            if not text:
                continue
            documents.append(
                ParsedDocument(
                    source_url=require_safe_reference_url(link, resource.final_url),
                    external_id=external_id[:500] if external_id else None,
                    title=normalize_text(title or "")[:1000] or None,
                    author_persona_hint=_permitted_atom_author(entry, policy),
                    published_at=_parse_timestamp(
                        _child_text(entry, "published") or _child_text(entry, "updated")
                    ),
                    raw_content=ElementTree.tostring(entry, encoding="utf-8"),
                    raw_content_type="application/xml",
                    text=text,
                    metadata={
                        "feed_type": "atom",
                        "feed_url": resource.final_url,
                        "categories": _atom_categories(entry),
                    },
                )
            )
        return tuple(documents)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _child(parent: Element, name: str) -> Element | None:
    for child in parent:
        if _local_name(child.tag) == name:
            return child
    return None


def _child_text(parent: Element, name: str) -> str | None:
    child = _child(parent, name)
    if child is None:
        return None
    value = "".join(child.itertext()).strip()
    return value or None


def _child_texts(parent: Element, name: str, limit: int) -> list[str]:
    values: list[str] = []
    for child in parent:
        if _local_name(child.tag) != name:
            continue
        value = "".join(child.itertext()).strip()
        if value:
            values.append(value[:200])
        if len(values) == limit:
            break
    return values


def _atom_link(entry: Element) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if not href:
            continue
        fallback = fallback or href
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
    return fallback


def _atom_categories(entry: Element) -> list[str]:
    values: list[str] = []
    for child in entry:
        if _local_name(child.tag) == "category" and child.attrib.get("term"):
            values.append(child.attrib["term"][:200])
        if len(values) == 20:
            break
    return values


def _permitted_author(item: Element, policy: SourcePolicy) -> str | None:
    if not policy.capture_author:
        return None
    value = _child_text(item, "creator") or _child_text(item, "author")
    return normalize_text(value or "")[:500] or None


def _permitted_atom_author(entry: Element, policy: SourcePolicy) -> str | None:
    if not policy.capture_author:
        return None
    author = _child(entry, "author")
    value = None if author is None else _child_text(author, "name")
    return normalize_text(value or "")[:500] or None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
