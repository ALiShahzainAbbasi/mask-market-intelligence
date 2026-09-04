from mask_api.modules.evidence.collectors.base import Collector
from mask_api.modules.evidence.collectors.rss_atom import RssAtomCollector
from mask_api.modules.evidence.collectors.static_html import StaticHtmlCollector

__all__ = ["Collector", "RssAtomCollector", "StaticHtmlCollector"]
