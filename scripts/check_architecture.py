"""Static Python boundary checks. No application imports or runtime I/O."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/api/src/mask_api"
FRAMEWORKS = {"fastapi", "starlette", "sqlalchemy", "httpx", "requests"}
INFRASTRUCTURE = {
    "mask_api.config",
    "mask_api.database",
    "mask_api.job_queue.models",
    "mask_api.job_queue.repository",
    "mask_api.job_queue.wiring",
    "mask_api.health",
    "mask_api.main",
    "mask_api.models",
    "mask_api.jobs",
    "mask_api.persistence",
    "mask_api.transport",
}
PURE_LAYERS = {"domain", "contracts", "ports", "services", "errors"}


def imports(source: str) -> set[str]:
    result = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
            result.update(node.module + "." + alias.name for alias in node.names)
    return result


def violations(module: str, dependencies: set[str]) -> list[str]:
    errors = []
    parts = module.split(".")
    feature = parts[2] if module.startswith("mask_api.modules.") else None
    layer = parts[3] if feature and len(parts) > 3 else None
    for dependency in sorted(dependencies):
        private_feature_adapter = (
            dependency.startswith("mask_api.modules.")
            and len(dependency.split(".")) > 3
            and dependency.split(".")[3] in {"models", "repository", "wiring", "router"}
        )
        if layer in PURE_LAYERS and (
            dependency.split(".")[0] in FRAMEWORKS
            or private_feature_adapter
            or any(
                dependency == name or dependency.startswith(name + ".") for name in INFRASTRUCTURE
            )
        ):
            errors.append(f"{module}: pure {layer} imports infrastructure {dependency}")
        if layer == "router" and (
            dependency.startswith("sqlalchemy")
            or dependency
            in {
                "mask_api.database",
                "mask_api.models",
                "mask_api.jobs",
                "mask_api.job_queue.repository",
                "mask_api.job_queue.wiring",
            }
            or ".repository" in dependency
            or ".models" in dependency
        ):
            errors.append(f"{module}: router imports persistence/queue {dependency}")
        if feature and dependency.startswith("mask_api.modules."):
            target = dependency.split(".")
            if (
                len(target) > 3
                and target[2] != feature
                and target[3] in {"models", "repository", "wiring"}
            ):
                errors.append(f"{module}: reaches another feature's private adapter {dependency}")
        if module.startswith("workers.") and (
            dependency.startswith("sqlalchemy")
            or ".models" in dependency
            or ".repository" in dependency
            or dependency in {"mask_api.database", "mask_api.jobs"}
        ):
            errors.append(f"{module}: worker bypasses service boundary via {dependency}")
    return errors


def cycles(graph: dict[str, set[str]]) -> list[str]:
    visited: set[str] = set()
    active: list[str] = []
    found = []

    def visit(node: str) -> None:
        if node in active:
            found.append(" -> ".join(active[active.index(node) :] + [node]))
            return
        if node in visited:
            return
        active.append(node)
        for target in sorted(graph[node]):
            if target in graph:
                visit(target)
        active.pop()
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return found


def check_repository() -> list[str]:
    graph = {}
    errors = []
    for base, prefix in ((PACKAGE, "mask_api"), (ROOT / "workers", "workers")):
        for path in base.rglob("*.py"):
            parts = list(path.relative_to(base).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            module = ".".join([prefix, *parts])
            source = path.read_text(encoding="utf-8")
            # Absolute internal imports make static ownership review predictable.
            if any(
                isinstance(node, ast.ImportFrom) and node.level
                for node in ast.walk(ast.parse(source))
            ):
                errors.append(f"{module}: use explicit absolute internal imports")
            graph[module] = imports(source)
            errors.extend(violations(module, graph[module]))
    errors.extend("Import cycle: " + cycle for cycle in cycles(graph))
    return errors


if __name__ == "__main__":
    failures = check_repository()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Architecture PASS: feature/transport/worker boundaries and import cycles.")
