"""Deterministic v1 confidence, completeness, method-status, and veto engine."""

from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.confidence import (
    calculate_confidence,
    clamp_100,
    label_for_confidence,
    sample_adequacy_score,
)
from mask_api.modules.confidence.contracts import (
    ConfidenceDimensions,
    ConfidenceLabel,
    ConfidenceResult,
    MarketMethodSummary,
    MethodCompletenessState,
    MethodStatusSnapshot,
    VetoAssessmentResult,
    VetoFinding,
    VetoId,
    VetoStatus,
)
from mask_api.modules.confidence.vetoes import evaluate_automatic_vetoes

__all__ = [
    "ConfidenceDimensions",
    "ConfidenceLabel",
    "ConfidenceResult",
    "MarketMethodSummary",
    "MethodCompletenessState",
    "MethodStatusSnapshot",
    "VetoAssessmentResult",
    "VetoFinding",
    "VetoId",
    "VetoStatus",
    "calculate_confidence",
    "clamp_100",
    "classify_completeness",
    "evaluate_automatic_vetoes",
    "label_for_confidence",
    "sample_adequacy_score",
]
