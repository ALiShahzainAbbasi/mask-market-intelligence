"""Narrow ports for analysis providers and deterministic result reuse."""

from __future__ import annotations

from typing import Protocol

from mask_api.modules.analysis.contracts import AnalysisRequest, AnalysisResult
from mask_api.modules.analysis.grounding_contracts import (
    HighImpactVerification,
    HighImpactVerificationRequest,
)
from mask_api.research_runner.budgets import BudgetLedger


class AnalysisProvider(Protocol):
    def analyze(self, request: AnalysisRequest, ledger: BudgetLedger) -> AnalysisResult: ...


class AnalysisCache(Protocol):
    def get(self, request: AnalysisRequest) -> AnalysisResult | None: ...

    def put(self, request: AnalysisRequest, result: AnalysisResult) -> None: ...


class HighImpactVerifier(Protocol):
    """Independent review edge; implementations must account for their own cost."""

    def verify(
        self,
        request: HighImpactVerificationRequest,
        ledger: BudgetLedger,
    ) -> tuple[HighImpactVerification, ...]: ...
