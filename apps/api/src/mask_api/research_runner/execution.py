"""Typed application contracts for method execution and run checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from mask_api.research_runner.budgets import BudgetLedger
from mask_api.research_runner.configuration import LoadedConfiguration
from mask_api.research_runner.contracts import (
    FormulaConfiguration,
    MarketConfiguration,
    MethodId,
    SourceProfile,
)
from mask_api.research_runner.ports import ArtifactStore

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class MethodRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ResearchRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"


class MethodExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: MethodRunStatus
    reason_code: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class MethodCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method_id: MethodId
    status: MethodRunStatus
    reason_code: str
    executor_version: str | None = None
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunBudgetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requests: int = Field(ge=0)
    documents: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    paid_cost_usd: str


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "run-manifest-v1"
    run_id: str
    market_id: str
    selected_methods: tuple[MethodId, ...]
    configuration_hashes: dict[str, str]
    status: ResearchRunStatus
    checkpoint: int = Field(ge=1)
    started_at: str
    updated_at: str
    methods: dict[MethodId, MethodCheckpoint]
    budget: RunBudgetSnapshot


@dataclass(frozen=True)
class MethodExecutionContext:
    run_id: str
    market: LoadedConfiguration[MarketConfiguration]
    formula: LoadedConfiguration[FormulaConfiguration]
    sources: LoadedConfiguration[SourceProfile]
    artifacts: ArtifactStore
    budget: BudgetLedger
    deadline: datetime


class MethodExecutor(Protocol):
    method_id: MethodId
    version: str

    def execute(self, context: MethodExecutionContext) -> MethodExecutionResult: ...


@dataclass(frozen=True)
class RunSummary:
    manifest: RunManifest
    resumed: bool
