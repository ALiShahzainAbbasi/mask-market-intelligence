"""Deterministic v1 overall score, gate readiness, and immutable snapshot engine."""

from mask_api.modules.market_scoring.contracts import (
    AutomatedResearchScore,
    FinalValidatedScore,
    FinalValidatedScoreStatus,
    GateEvaluation,
    GateId,
    GateResultStatus,
    MarketScoreSnapshot,
    SnapshotCompatibilityKey,
    snapshots_are_comparable,
)
from mask_api.modules.market_scoring.gates import evaluate_all_gates, evaluate_gate
from mask_api.modules.market_scoring.scoring import (
    MarketScoringError,
    aggregate_confidence,
    calculate_automated_research_score,
    risk_adjusted_method_score,
)
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot

__all__ = [
    "AutomatedResearchScore",
    "FinalValidatedScore",
    "FinalValidatedScoreStatus",
    "GateEvaluation",
    "GateId",
    "GateResultStatus",
    "MarketScoreSnapshot",
    "MarketScoringError",
    "SnapshotCompatibilityKey",
    "aggregate_confidence",
    "build_market_score_snapshot",
    "calculate_automated_research_score",
    "evaluate_all_gates",
    "evaluate_gate",
    "risk_adjusted_method_score",
    "snapshots_are_comparable",
]
