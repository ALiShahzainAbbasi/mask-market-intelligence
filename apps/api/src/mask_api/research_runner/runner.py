"""Fail-soft orchestration for a versioned autonomous research run."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mask_api.research_runner.artifacts import ArtifactKind
from mask_api.research_runner.budgets import (
    BudgetLedger,
    BudgetLimitExceeded,
    BudgetUsage,
    RunBudgetLimits,
)
from mask_api.research_runner.configuration import LoadedConfiguration
from mask_api.research_runner.contracts import (
    FormulaConfiguration,
    MarketConfiguration,
    MethodId,
    SourceProfile,
)
from mask_api.research_runner.execution import (
    MethodCheckpoint,
    MethodExecutionContext,
    MethodExecutionResult,
    MethodExecutor,
    MethodRunStatus,
    ResearchRunStatus,
    RunBudgetSnapshot,
    RunManifest,
    RunSummary,
)
from mask_api.research_runner.ports import ArtifactStore

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MANIFEST = re.compile(r"^run-(\d{6})\.json$")


class ResearchRunnerError(RuntimeError):
    """A run cannot start or resume safely."""


class ResearchRunner:
    def __init__(
        self,
        *,
        run_id: str,
        market: LoadedConfiguration[MarketConfiguration],
        formula: LoadedConfiguration[FormulaConfiguration],
        sources: LoadedConfiguration[SourceProfile],
        artifacts: ArtifactStore,
        executors: Iterable[MethodExecutor] = (),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise ResearchRunnerError("run id must be a safe Windows filename component")
        executor_items = tuple(executors)
        executor_map = {executor.method_id: executor for executor in executor_items}
        if len(executor_map) != len(executor_items):
            raise ResearchRunnerError("only one executor may be registered per method")
        if market.value.formula_version != formula.value.formula_version:
            raise ResearchRunnerError("market and formula versions do not match")
        if market.value.source_policy_profile != sources.value.profile_id:
            raise ResearchRunnerError("market and source profile do not match")
        self._run_id = run_id
        self._market = market
        self._formula = formula
        self._sources = sources
        self._artifacts = artifacts
        self._executors = executor_map
        self._now = now or (lambda: datetime.now(UTC))

    def run(self, selected_methods: tuple[MethodId, ...]) -> RunSummary:
        methods = self._validate_methods(selected_methods)
        latest = self._latest_manifest()
        resumed = latest is not None
        if latest is not None:
            self._require_compatible(latest, methods)
            if latest.status != ResearchRunStatus.RUNNING:
                return RunSummary(manifest=latest, resumed=True)
            checkpoints = dict(latest.methods)
            ledger = BudgetLedger(self._budget_limits(), self._usage(latest.budget))
            checkpoint_number = latest.checkpoint
            started_at = self._parse_timestamp(latest.started_at)
        else:
            if self._artifacts.list_artifacts():
                raise ResearchRunnerError("output directory contains artifacts but no run manifest")
            self._write_configuration_lineage()
            checkpoints = {}
            ledger = BudgetLedger(self._budget_limits())
            checkpoint_number = 0
            started_at = self._timestamp()
            initial = self._manifest(
                methods,
                ResearchRunStatus.RUNNING,
                checkpoint_number + 1,
                checkpoints,
                ledger,
                started_at,
            )
            self._write_manifest(initial)
            checkpoint_number += 1

        stop_reason: str | None = None
        deadline = started_at + timedelta(seconds=self._budget_limits().max_duration_seconds)
        context = MethodExecutionContext(
            run_id=self._run_id,
            market=self._market,
            formula=self._formula,
            sources=self._sources,
            artifacts=self._artifacts,
            budget=ledger,
            deadline=deadline,
        )
        for method in methods:
            if method in checkpoints:
                continue
            if stop_reason is None and self._timestamp() >= deadline:
                stop_reason = "budget.duration_limit_reached"
            if stop_reason is not None:
                result = MethodExecutionResult(
                    status=MethodRunStatus.UNKNOWN,
                    reason_code=stop_reason,
                )
                executor_version = None
            elif (
                method in {MethodId.M8, MethodId.M10} and not self._market.value.validation.enabled
            ):
                result = MethodExecutionResult(
                    status=MethodRunStatus.UNKNOWN,
                    reason_code="validation.disabled",
                )
                executor_version = None
            else:
                executor = self._executors.get(method)
                executor_version = executor.version if executor is not None else None
                if executor is None:
                    result = MethodExecutionResult(
                        status=MethodRunStatus.UNKNOWN,
                        reason_code="method.executor_unavailable",
                    )
                else:
                    try:
                        result = executor.execute(context)
                    except BudgetLimitExceeded as error:
                        stop_reason = f"budget.{error.dimension}_limit_reached"
                        result = MethodExecutionResult(
                            status=MethodRunStatus.PARTIAL,
                            reason_code=stop_reason,
                        )
                    except Exception:
                        result = MethodExecutionResult(
                            status=MethodRunStatus.FAILED,
                            reason_code="method.executor_failed",
                        )
            artifact_path = f"methods/{method.value}/attempt-000001.json"
            receipt = self._artifacts.write_bytes(
                ArtifactKind.METRICS,
                artifact_path,
                self._json_bytes(
                    {
                        "executor_version": executor_version,
                        "method_id": method.value,
                        **result.model_dump(mode="json"),
                    }
                ),
            )
            checkpoints[method] = MethodCheckpoint(
                method_id=method,
                status=result.status,
                reason_code=result.reason_code,
                executor_version=executor_version,
                artifact_path=receipt.relative_path,
                artifact_sha256=receipt.sha256,
            )
            checkpoint_number += 1
            self._write_manifest(
                self._manifest(
                    methods,
                    ResearchRunStatus.RUNNING,
                    checkpoint_number,
                    checkpoints,
                    ledger,
                    started_at,
                )
            )

        status = (
            ResearchRunStatus.COMPLETED
            if all(item.status == MethodRunStatus.SUCCEEDED for item in checkpoints.values())
            else ResearchRunStatus.PARTIAL
        )
        checkpoint_number += 1
        final = self._manifest(methods, status, checkpoint_number, checkpoints, ledger, started_at)
        self._write_manifest(final)
        return RunSummary(manifest=final, resumed=resumed)

    def _validate_methods(self, methods: tuple[MethodId, ...]) -> tuple[MethodId, ...]:
        if not methods:
            raise ResearchRunnerError("at least one method must be selected")
        if len(methods) != len(set(methods)):
            raise ResearchRunnerError("selected methods must be unique")
        selected = set(methods)
        return tuple(method for method in MethodId if method in selected)

    def _configuration_hashes(self) -> dict[str, str]:
        return {
            "formula": self._formula.sha256,
            "market": self._market.sha256,
            "sources": self._sources.sha256,
        }

    def _write_configuration_lineage(self) -> None:
        configurations = {
            "formula.json": self._formula.value.model_dump(mode="json"),
            "market.json": self._market.value.model_dump(mode="json"),
            "sources.json": self._sources.value.model_dump(mode="json"),
        }
        for name, content in configurations.items():
            self._artifacts.write_bytes(
                ArtifactKind.LINEAGE,
                f"configuration/{name}",
                self._json_bytes(content),
            )

    def _latest_manifest(self) -> RunManifest | None:
        candidates: list[tuple[int, str]] = []
        for receipt in self._artifacts.list_artifacts(ArtifactKind.MANIFESTS):
            matched = _MANIFEST.fullmatch(receipt.relative_path)
            if matched:
                candidates.append((int(matched.group(1)), receipt.relative_path))
        if not candidates:
            return None
        _, path = max(candidates)
        try:
            return RunManifest.model_validate_json(
                self._artifacts.read_bytes(ArtifactKind.MANIFESTS, path)
            )
        except Exception as error:
            raise ResearchRunnerError("latest run manifest is invalid") from error

    def _require_compatible(self, manifest: RunManifest, methods: tuple[MethodId, ...]) -> None:
        if (
            manifest.run_id != self._run_id
            or manifest.market_id != self._market.value.market_id
            or manifest.selected_methods != methods
            or manifest.configuration_hashes != self._configuration_hashes()
        ):
            raise ResearchRunnerError("existing run output is incompatible with this request")

    def _budget_limits(self) -> RunBudgetLimits:
        budget = self._market.value.run_budget
        return RunBudgetLimits(
            max_requests=budget.max_requests,
            max_documents=budget.max_documents,
            max_total_bytes=budget.max_total_bytes,
            max_duration_seconds=budget.max_duration_seconds,
            max_paid_cost_usd=budget.max_paid_cost_usd,
        )

    @staticmethod
    def _usage(snapshot: RunBudgetSnapshot) -> BudgetUsage:
        return BudgetUsage(
            requests=snapshot.requests,
            documents=snapshot.documents,
            total_bytes=snapshot.total_bytes,
            paid_cost_usd=Decimal(snapshot.paid_cost_usd),
        )

    def _manifest(
        self,
        methods: tuple[MethodId, ...],
        status: ResearchRunStatus,
        checkpoint: int,
        checkpoints: dict[MethodId, MethodCheckpoint],
        ledger: BudgetLedger,
        started_at: datetime,
    ) -> RunManifest:
        usage = ledger.usage
        return RunManifest(
            run_id=self._run_id,
            market_id=self._market.value.market_id,
            selected_methods=methods,
            configuration_hashes=self._configuration_hashes(),
            status=status,
            checkpoint=checkpoint,
            started_at=started_at.isoformat(),
            updated_at=self._timestamp().isoformat(),
            methods=checkpoints,
            budget=RunBudgetSnapshot(
                requests=usage.requests,
                documents=usage.documents,
                total_bytes=usage.total_bytes,
                paid_cost_usd=str(usage.paid_cost_usd),
            ),
        )

    def _write_manifest(self, manifest: RunManifest) -> None:
        self._artifacts.write_bytes(
            ArtifactKind.MANIFESTS,
            f"run-{manifest.checkpoint:06d}.json",
            self._json_bytes(manifest.model_dump(mode="json")),
        )

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ResearchRunnerError("runner clock must return a timezone-aware timestamp")
        return value.astimezone(UTC)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ResearchRunnerError("run manifest contains an invalid timestamp") from error
        if parsed.tzinfo is None:
            raise ResearchRunnerError("run manifest timestamp must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _json_bytes(content: object) -> bytes:
        return (
            json.dumps(
                content,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                separators=(",", ": "),
            )
            + "\n"
        ).encode("utf-8")
