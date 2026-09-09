"""Bounded deterministic source-discovery query generation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

from mask_api.modules.discovery.contracts import DiscoveryPlan, DiscoveryQuery
from mask_api.research_runner.contracts import MarketConfiguration, MethodId

_SPACE = re.compile(r"\s+")
_TEMPLATES: dict[MethodId, tuple[tuple[str, str], ...]] = {
    MethodId.M1: (
        ("market_size", '"{term}" NAICS establishments employment payroll'),
        ("market_growth", '"{term}" industry growth statistics'),
    ),
    MethodId.M2: (
        ("pain_frequency", '"{problem}" complaints challenges'),
        ("purchase_intent", '"{problem}" software recommendations alternatives'),
    ),
    MethodId.M3: (
        ("workflow", '"{problem}" workflow manual process bottleneck'),
        ("failure", '"{problem}" errors delays rework'),
    ),
    MethodId.M4: (
        ("economic_burden", '"{problem}" cost labor hours revenue loss'),
        ("existing_spend", '"{term}" software pricing budget'),
    ),
    MethodId.M5: (
        ("competitors", '"{term}" software alternatives competitors'),
        ("pricing", '"{term}" software pricing reviews'),
    ),
    MethodId.M6: (
        ("commercial_search", '"{term}" software pricing demo buy'),
        ("switching", '"{term}" alternative replacement'),
    ),
    MethodId.M7: (
        ("buyer_access", '"{buyer}" "{term}" association directory'),
        ("procurement", '"{term}" procurement buying process'),
    ),
    MethodId.M9: (
        ("integration", '"{term}" API integration automation'),
        ("productization", '"{problem}" standardized workflow software'),
    ),
}


def build_discovery_plan(
    market: MarketConfiguration,
    methods: Iterable[MethodId],
    *,
    max_queries: int = 80,
) -> DiscoveryPlan:
    if max_queries < 1 or max_queries > 500:
        raise ValueError("max_queries must be between 1 and 500")
    selected = set(methods)
    geography = _geography(market)
    terms = tuple(_clean(value) for value in market.seed_terms)
    problems = tuple(_clean(value) for value in market.seed_problems)
    buyers = tuple(_clean(value) for value in market.buyer_titles)
    candidates: list[DiscoveryQuery] = []
    seen: set[str] = set()
    for method in MethodId:
        if method not in selected:
            continue
        for intent, template in _TEMPLATES.get(method, ()):
            values = _values_for(template, terms, problems, buyers)
            for substitutions, source_terms in values:
                query = _clean(f"{template.format(**substitutions)} {geography}")
                if len(query) > 600 or len(query.split()) > 75:
                    continue
                canonical = query.casefold()
                if canonical in seen:
                    continue
                seen.add(canonical)
                candidates.append(
                    DiscoveryQuery(
                        query_id=hashlib.sha256(
                            f"discovery-query-v1\0{method.value}\0{intent}\0{query}".encode()
                        ).hexdigest(),
                        method_id=method,
                        intent=intent,
                        query=query,
                        source_terms=source_terms,
                    )
                )
                if len(candidates) >= max_queries:
                    return DiscoveryPlan(market_id=market.market_id, queries=tuple(candidates))
    return DiscoveryPlan(market_id=market.market_id, queries=tuple(candidates))


def _values_for(
    template: str,
    terms: tuple[str, ...],
    problems: tuple[str, ...],
    buyers: tuple[str, ...],
) -> tuple[tuple[dict[str, str], tuple[str, ...]], ...]:
    needs_term = "{term}" in template
    needs_problem = "{problem}" in template
    needs_buyer = "{buyer}" in template
    selected_terms = terms if needs_term else ("",)
    selected_problems = problems if needs_problem else ("",)
    selected_buyers = buyers if needs_buyer else ("",)
    values: list[tuple[dict[str, str], tuple[str, ...]]] = []
    for term in selected_terms:
        for problem in selected_problems:
            for buyer in selected_buyers:
                substitutions = {"term": term, "problem": problem, "buyer": buyer}
                source_terms = tuple(value for value in (term, problem, buyer) if value)
                values.append((substitutions, source_terms))
    return tuple(values)


def _geography(market: MarketConfiguration) -> str:
    regions = " ".join(_clean(value) for value in market.geography.regions)
    return _clean(f"{market.geography.country} {regions}")


def _clean(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _SPACE.sub(" ", normalized).strip()
