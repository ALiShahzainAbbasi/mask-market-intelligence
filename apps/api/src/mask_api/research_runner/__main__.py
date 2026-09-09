"""Windows-native command line entry point for autonomous research runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mask_api.research_runner.artifacts import ArtifactStoreError
from mask_api.research_runner.configuration import (
    ConfigurationError,
    load_formula_configuration,
    load_market_configuration,
    load_source_profile,
)
from mask_api.research_runner.contracts import MethodId
from mask_api.research_runner.local_artifacts import LocalArtifactStore
from mask_api.research_runner.runner import ResearchRunner, ResearchRunnerError

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def _methods(value: str) -> tuple[MethodId, ...]:
    if value.casefold() == "all":
        return tuple(MethodId)
    requested = [item.strip().upper() for item in value.split(",") if item.strip()]
    try:
        methods = tuple(MethodId(item) for item in requested)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "methods must be all or a comma-separated M1-M10 list"
        ) from error
    if not methods:
        raise argparse.ArgumentTypeError("at least one method must be selected")
    if len(methods) != len(set(methods)):
        raise argparse.ArgumentTypeError("selected methods must be unique")
    return methods


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mask_api.research_runner")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run or safely resume a market research job")
    run.add_argument("market", type=Path)
    run.add_argument("--methods", type=_methods, default=tuple(MethodId))
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    if args.command != "run":
        return 1
    try:
        market = load_market_configuration(args.market)
        formula = load_formula_configuration(
            PROJECT_ROOT / "configs/formulas" / f"{market.value.formula_version}.yaml"
        )
        sources = load_source_profile(
            PROJECT_ROOT / "configs/sources" / f"{market.value.source_policy_profile}.yaml"
        )
        store = LocalArtifactStore(args.output)
        runner = ResearchRunner(
            run_id=args.output.name,
            market=market,
            formula=formula,
            sources=sources,
            artifacts=store,
        )
        summary = runner.run(args.methods)
    except (ConfigurationError, ResearchRunnerError, ArtifactStoreError) as error:
        print(f"Research run could not proceed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "checkpoint": summary.manifest.checkpoint,
                "manifest": f"manifests/run-{summary.manifest.checkpoint:06d}.json",
                "resumed": summary.resumed,
                "run_id": summary.manifest.run_id,
                "status": summary.manifest.status,
            },
            sort_keys=True,
        )
    )
    return 0 if summary.manifest.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
