from mask_api.modules.evidence.collectors.base import Collector
from mask_api.modules.evidence.collectors.rss_atom import RssAtomCollector
from mask_api.modules.evidence.collectors.static_html import StaticHtmlCollector
from mask_api.modules.evidence.http_fetcher import (
    SafeHttpFetcher,
    SystemHostResolver,
    UrllibHttpTransport,
)


def default_collectors() -> tuple[Collector, ...]:
    collectors: tuple[Collector, ...] = (RssAtomCollector(), StaticHtmlCollector())
    return collectors


def default_http_fetcher() -> SafeHttpFetcher:
    return SafeHttpFetcher(SystemHostResolver(), UrllibHttpTransport())
