"""Pure discovery contracts; search transports remain edge adapters."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from mask_api.research_runner.contracts import MethodId


class DiscoveryValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class DiscoveryQuery(DiscoveryValue):
    query_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    method_id: MethodId
    intent: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=600)
    source_terms: tuple[str, ...] = Field(min_length=1, max_length=10)


class DiscoveryPlan(DiscoveryValue):
    version: str = "discovery-query-v1"
    market_id: str
    queries: tuple[DiscoveryQuery, ...]


class SearchResult(DiscoveryValue):
    provider: str
    query_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    rank: int = Field(ge=1)
    url: str = Field(min_length=8, max_length=2048)
    title: str = Field(min_length=1, max_length=1000)
    description: str | None = Field(default=None, max_length=4000)
    page_age: str | None = Field(default=None, max_length=100)
    page_fetched: AwareDatetime | None = None


class SearchPage(DiscoveryValue):
    provider: str
    endpoint: str
    query_id: str
    query: str
    offset: int = Field(ge=0, le=9)
    retrieved_at: AwareDatetime
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response: bytes = Field(repr=False)
    results: tuple[SearchResult, ...]
    more_results_available: bool


class DiscoveryBatch(DiscoveryValue):
    provider: str
    plan_version: str
    retrieved_at: AwareDatetime
    pages: tuple[SearchPage, ...]
    results: tuple[SearchResult, ...]
