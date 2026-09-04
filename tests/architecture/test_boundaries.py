import pytest

from scripts.check_architecture import check_repository, cycles, imports, violations


def test_repository_boundaries() -> None:
    assert check_repository() == []


@pytest.mark.parametrize(
    "module,dependency",
    [
        ("mask_api.modules.markets.domain", "sqlalchemy"),
        ("mask_api.modules.smoke.services", "mask_api.database"),
        ("mask_api.modules.smoke.services", "mask_api.modules.smoke.repository"),
        ("mask_api.modules.markets.domain", "mask_api.modules.markets.wiring"),
        ("mask_api.modules.markets.router", "mask_api.modules.markets.repository"),
        ("mask_api.modules.markets.models", "mask_api.modules.identity.models"),
        ("workers.smoke_handler", "sqlalchemy.orm"),
        ("mask_api.modules.smoke.services", "mask_api.job_queue.repository"),
    ],
)
def test_forbidden_edges_are_detected(module: str, dependency: str) -> None:
    assert violations(module, {dependency})


def test_public_contract_edges_are_allowed() -> None:
    assert not violations("mask_api.modules.markets.services", {"mask_api.modules.identity.domain"})


def test_cycle_detection() -> None:
    assert cycles({"a": {"b"}, "b": {"a"}}) == ["a -> b -> a"]
    assert cycles({"a": {"b"}, "b": set()}) == []


def test_import_parser_handles_from_and_plain_imports() -> None:
    assert {"mask_api.database", "mask_api.database.Base", "sqlalchemy"} <= imports(
        "from mask_api.database import Base\nimport sqlalchemy"
    )
