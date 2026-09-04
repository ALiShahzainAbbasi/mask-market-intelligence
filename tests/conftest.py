import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--integration", action="store_true", help="Require real running services")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(
            reason="Run explicitly with --integration and provisioned local services"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
