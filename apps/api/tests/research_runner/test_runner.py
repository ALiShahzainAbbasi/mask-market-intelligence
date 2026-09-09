from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mask_api.research_runner.__main__ import main
from mask_api.research_runner.artifacts import ArtifactKind
from mask_api.research_runner.budgets import BudgetCharge
from mask_api.research_runner.configuration import (
    LoadedConfiguration,
    load_formula_configuration,
    load_market_configuration,
    load_source_profile,
)
from mask_api.research_runner.contracts import (
    FormulaConfiguration,
    MarketConfiguration,
    MethodId,
    SourceProfile,
)
from mask_api.research_runner.execution import (
    MethodExecutionContext,
    MethodExecutionResult,
    MethodRunStatus,
    ResearchRunStatus,
)
from mask_api.research_runner.local_artifacts import LocalArtifactStore
from mask_api.research_runner.runner import ResearchRunner, ResearchRunnerError

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@dataclass
class SuccessfulExecutor:
    method_id: MethodId
    version: str = "fixture-v1"
    calls: int = 0

    def execute(self, context: MethodExecutionContext) -> MethodExecutionResult:
        self.calls += 1
        context.budget.consume(BudgetCharge(requests=1, documents=1, total_bytes=4))
        return MethodExecutionResult(
            status=MethodRunStatus.SUCCEEDED,
            reason_code="method.completed",
            payload={"documents": 1},
        )


@dataclass
class FailedExecutor:
    method_id: MethodId
    version: str = "fixture-v1"

    def execute(self, _context: MethodExecutionContext) -> MethodExecutionResult:
        raise RuntimeError("sensitive synthetic detail")


@dataclass
class BudgetBreakingExecutor:
    method_id: MethodId
    version: str = "fixture-v1"

    def execute(self, context: MethodExecutionContext) -> MethodExecutionResult:
        context.budget.consume(BudgetCharge(requests=101))
        raise AssertionError("budget consume must stop first")


@dataclass
class InterruptingExecutor:
    method_id: MethodId
    version: str = "fixture-v1"

    def execute(self, _context: MethodExecutionContext) -> MethodExecutionResult:
        raise KeyboardInterrupt


def configurations() -> tuple[
    LoadedConfiguration[MarketConfiguration],
    LoadedConfiguration[FormulaConfiguration],
    LoadedConfiguration[SourceProfile],
]:
    return (
        load_market_configuration(ROOT / "configs/markets/us_hvac_10_99.yaml"),
        load_formula_configuration(ROOT / "configs/formulas/v1.yaml"),
        load_source_profile(ROOT / "configs/sources/default_us_public.yaml"),
    )


def runner(
    tmp_path: Path,
    *executors: SuccessfulExecutor | FailedExecutor | BudgetBreakingExecutor | InterruptingExecutor,
    now: datetime = NOW,
    market: LoadedConfiguration[MarketConfiguration] | None = None,
) -> tuple[ResearchRunner, LocalArtifactStore]:
    configured_market, formula, sources = configurations()
    store = LocalArtifactStore(tmp_path / "run-001")
    instance = ResearchRunner(
        run_id="run-001",
        market=market or configured_market,
        formula=formula,
        sources=sources,
        artifacts=store,
        executors=executors,
        now=lambda: now,
    )
    return instance, store


def test_runner_executes_selected_methods_in_canonical_order(tmp_path: Path) -> None:
    m2 = SuccessfulExecutor(MethodId.M2)
    m1 = SuccessfulExecutor(MethodId.M1)
    instance, store = runner(tmp_path, m2, m1)

    summary = instance.run((MethodId.M2, MethodId.M1))

    assert summary.manifest.status == ResearchRunStatus.COMPLETED
    assert summary.manifest.selected_methods == (MethodId.M1, MethodId.M2)
    assert list(summary.manifest.methods) == [MethodId.M1, MethodId.M2]
    assert summary.manifest.budget.requests == 2
    assert summary.manifest.budget.documents == 2
    assert summary.manifest.budget.total_bytes == 8
    assert len(store.list_artifacts(ArtifactKind.LINEAGE)) == 3
    assert len(store.list_artifacts(ArtifactKind.MANIFESTS)) == 4


def test_terminal_run_is_idempotently_resumed_without_executor_calls(tmp_path: Path) -> None:
    executor = SuccessfulExecutor(MethodId.M1)
    instance, store = runner(tmp_path, executor)
    first = instance.run((MethodId.M1,))
    before = store.list_artifacts()

    second = instance.run((MethodId.M1,))

    assert second.resumed is True
    assert second.manifest == first.manifest
    assert executor.calls == 1
    assert store.list_artifacts() == before


def test_interrupted_run_resumes_from_append_only_manifest(tmp_path: Path) -> None:
    interrupted, store = runner(tmp_path, InterruptingExecutor(MethodId.M1))
    with pytest.raises(KeyboardInterrupt):
        interrupted.run((MethodId.M1,))
    assert len(store.list_artifacts(ArtifactKind.MANIFESTS)) == 1

    market, formula, sources = configurations()
    executor = SuccessfulExecutor(MethodId.M1)
    resumed = ResearchRunner(
        run_id="run-001",
        market=market,
        formula=formula,
        sources=sources,
        artifacts=store,
        executors=(executor,),
        now=lambda: NOW,
    ).run((MethodId.M1,))

    assert resumed.resumed is True
    assert resumed.manifest.status == ResearchRunStatus.COMPLETED
    assert executor.calls == 1


def test_executor_failure_is_safe_and_does_not_stop_other_methods(tmp_path: Path) -> None:
    successful = SuccessfulExecutor(MethodId.M2)
    instance, store = runner(tmp_path, FailedExecutor(MethodId.M1), successful)

    summary = instance.run((MethodId.M1, MethodId.M2))

    assert summary.manifest.status == ResearchRunStatus.PARTIAL
    assert summary.manifest.methods[MethodId.M1].reason_code == "method.executor_failed"
    assert summary.manifest.methods[MethodId.M2].status == MethodRunStatus.SUCCEEDED
    assert successful.calls == 1
    all_content = b"".join(
        store.read_bytes(item.kind, item.relative_path) for item in store.list_artifacts()
    )
    assert b"sensitive synthetic detail" not in all_content


def test_budget_failure_stops_later_method_dispatch(tmp_path: Path) -> None:
    later = SuccessfulExecutor(MethodId.M2)
    instance, _store = runner(tmp_path, BudgetBreakingExecutor(MethodId.M1), later)

    summary = instance.run((MethodId.M1, MethodId.M2))

    assert summary.manifest.methods[MethodId.M1].reason_code == "budget.requests_limit_reached"
    assert summary.manifest.methods[MethodId.M2].reason_code == "budget.requests_limit_reached"
    assert later.calls == 0
    assert summary.manifest.budget.requests == 0


def test_disabled_validation_methods_remain_unknown(tmp_path: Path) -> None:
    executor = SuccessfulExecutor(MethodId.M8)
    instance, _store = runner(tmp_path, executor)

    summary = instance.run((MethodId.M8, MethodId.M10))

    assert all(
        result.status == MethodRunStatus.UNKNOWN for result in summary.manifest.methods.values()
    )
    assert all(
        result.reason_code == "validation.disabled" for result in summary.manifest.methods.values()
    )
    assert executor.calls == 0


def test_uninstalled_method_remains_unknown(tmp_path: Path) -> None:
    instance, _store = runner(tmp_path)

    summary = instance.run((MethodId.M9,))

    assert summary.manifest.status == ResearchRunStatus.PARTIAL
    assert summary.manifest.methods[MethodId.M9].reason_code == "method.executor_unavailable"


def test_duration_limit_prevents_method_dispatch(tmp_path: Path) -> None:
    loaded_market, _formula, _sources = configurations()
    assert isinstance(loaded_market, LoadedConfiguration)
    market_value = loaded_market.value.model_copy(
        update={
            "run_budget": loaded_market.value.run_budget.model_copy(
                update={"max_duration_seconds": 1}
            )
        }
    )
    market = LoadedConfiguration(
        path=loaded_market.path,
        value=market_value,
        sha256=loaded_market.sha256,
    )
    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return NOW if clock_calls <= 2 else NOW + timedelta(seconds=2)

    executor = SuccessfulExecutor(MethodId.M1)
    configured_market, formula, sources = configurations()
    store = LocalArtifactStore(tmp_path / "run-001")
    instance = ResearchRunner(
        run_id="run-001",
        market=market,
        formula=formula,
        sources=sources,
        artifacts=store,
        executors=(executor,),
        now=clock,
    )

    summary = instance.run((MethodId.M1,))

    assert configured_market is not None
    assert summary.manifest.methods[MethodId.M1].reason_code == "budget.duration_limit_reached"
    assert executor.calls == 0


def test_incompatible_resume_is_rejected(tmp_path: Path) -> None:
    instance, _store = runner(tmp_path, SuccessfulExecutor(MethodId.M1))
    instance.run((MethodId.M1,))

    with pytest.raises(ResearchRunnerError, match="incompatible"):
        instance.run((MethodId.M2,))


def test_nonempty_artifact_directory_without_manifest_is_rejected(tmp_path: Path) -> None:
    instance, store = runner(tmp_path)
    store.write_text(ArtifactKind.LOGS, "existing.jsonl", "event")

    with pytest.raises(ResearchRunnerError, match="no run manifest"):
        instance.run((MethodId.M1,))


def test_cli_creates_partial_honest_run_and_resumes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli-run"
    arguments = [
        "run",
        str(ROOT / "configs/markets/us_hvac_10_99.yaml"),
        "--methods",
        "M1,M9",
        "--output",
        str(output),
    ]

    assert main(arguments) == 2
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "partial"
    assert first["resumed"] is False
    assert main(arguments) == 2
    second = json.loads(capsys.readouterr().out)
    assert second["resumed"] is True
    assert second["manifest"] == first["manifest"]
    assert (output / "lineage/configuration/market.json").exists()


def test_duplicate_executor_and_invalid_run_id_are_rejected(tmp_path: Path) -> None:
    market, formula, sources = configurations()
    executor = SuccessfulExecutor(MethodId.M1)
    with pytest.raises(ResearchRunnerError, match="one executor"):
        ResearchRunner(
            run_id="run-001",
            market=market,
            formula=formula,
            sources=sources,
            artifacts=LocalArtifactStore(tmp_path / "duplicate"),
            executors=(executor, executor),
        )
    with pytest.raises(ResearchRunnerError, match="safe Windows"):
        ResearchRunner(
            run_id="../unsafe",
            market=market,
            formula=formula,
            sources=sources,
            artifacts=LocalArtifactStore(tmp_path / "invalid"),
        )
