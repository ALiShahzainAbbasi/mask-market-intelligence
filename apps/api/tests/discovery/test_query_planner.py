import hashlib
from pathlib import Path

import pytest
from mask_api.modules.discovery.query_planner import build_discovery_plan
from mask_api.research_runner.configuration import load_market_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).resolve().parents[4]


def market():
    return load_market_configuration(ROOT / "configs/markets/us_hvac_10_99.yaml").value


def test_query_plan_is_deterministic_bounded_and_source_traceable() -> None:
    first = build_discovery_plan(market(), (MethodId.M2, MethodId.M5), max_queries=7)
    second = build_discovery_plan(market(), (MethodId.M5, MethodId.M2), max_queries=7)

    assert first == second
    assert len(first.queries) == 7
    assert first.queries[0].query == (
        '"technician scheduling and dispatch" complaints challenges US'
    )
    assert first.queries[0].source_terms == ("technician scheduling and dispatch",)
    assert (
        first.queries[0].query_id
        == hashlib.sha256(
            b"discovery-query-v1\0M2\0pain_frequency\0"
            b'"technician scheduling and dispatch" complaints challenges US'
        ).hexdigest()
    )
    assert all(len(item.query) <= 600 and len(item.query.split()) <= 75 for item in first.queries)


def test_methods_without_public_search_templates_create_no_queries() -> None:
    plan = build_discovery_plan(market(), (MethodId.M8, MethodId.M10))

    assert plan.queries == ()


def test_method_order_is_canonical_and_duplicates_do_not_duplicate_queries() -> None:
    plan = build_discovery_plan(market(), (MethodId.M9, MethodId.M1, MethodId.M1))

    assert plan.queries[0].method_id == MethodId.M1
    assert plan.queries[-1].method_id == MethodId.M9
    assert len({item.query.casefold() for item in plan.queries}) == len(plan.queries)


@pytest.mark.parametrize("limit", [0, 501])
def test_query_plan_limit_is_validated(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 500"):
        build_discovery_plan(market(), (MethodId.M1,), max_queries=limit)
