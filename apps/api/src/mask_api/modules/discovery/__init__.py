"""Deterministic query planning and optional search-provider adapters."""

from mask_api.modules.discovery.contracts import DiscoveryPlan, DiscoveryQuery, SearchResult
from mask_api.modules.discovery.query_planner import build_discovery_plan

__all__ = ["DiscoveryPlan", "DiscoveryQuery", "SearchResult", "build_discovery_plan"]
