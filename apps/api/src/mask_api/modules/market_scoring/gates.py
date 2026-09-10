"""Deterministic v1 gate readiness evaluation (SCORING.md section 8)."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.confidence.contracts import (
    MethodStatusSnapshot,
    VetoAssessmentResult,
    VetoStatus,
)
from mask_api.modules.market_scoring.contracts import GateEvaluation, GateId, GateResultStatus
from mask_api.modules.market_scoring.scoring import MarketScoringError, aggregate_confidence
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import ConfidenceConfiguration, GateConfiguration, MethodId


def evaluate_gate(
    gate_id: GateId,
    gate_config: GateConfiguration,
    *,
    confidence_config: ConfidenceConfiguration,
    overall_weights: dict[MethodId, Decimal],
    methods: dict[MethodId, MethodStatusSnapshot],
    vetoes: VetoAssessmentResult,
) -> GateEvaluation:
    """Evaluate one gate's deterministic readiness; never records a stage decision."""
    confirmed_critical = tuple(
        finding
        for finding in vetoes.findings
        if finding.status == VetoStatus.CONFIRMED and finding.severity == "critical"
    )
    if confirmed_critical:
        return GateEvaluation(
            gate_id=gate_id,
            status=GateResultStatus.BLOCKED,
            unresolved_reasons=tuple(
                f"veto.{finding.veto_id.value}_confirmed" for finding in confirmed_critical
            ),
        )

    missing = tuple(
        method
        for method in gate_config.methods
        if method not in methods or methods[method].score is None
    )
    if missing:
        return GateEvaluation(
            gate_id=gate_id,
            status=GateResultStatus.NOT_READY,
            missing_methods=missing,
            unresolved_reasons=("gate.required_method_score_missing",),
        )

    total_weight = sum((overall_weights[method] for method in gate_config.methods), ZERO)
    if total_weight <= ZERO:
        raise MarketScoringError(f"{gate_id} required methods must have positive total weight")
    weighted_sum = sum(
        (methods[method].score * overall_weights[method] for method in gate_config.methods),  # type: ignore[operator]
        ZERO,
    )
    gate_score = clamp10(weighted_sum / total_weight)
    gate_confidence = aggregate_confidence(
        confidence_config=confidence_config,
        overall_weights=overall_weights,
        required_methods=gate_config.methods,
        methods=methods,
    )

    if gate_config.minimum_confidence is not None and (
        gate_confidence.numeric_confidence is None
        or gate_confidence.numeric_confidence < gate_config.minimum_confidence
    ):
        return GateEvaluation(
            gate_id=gate_id,
            status=GateResultStatus.NOT_READY,
            gate_score=gate_score,
            gate_confidence=gate_confidence,
            unresolved_reasons=("gate.confidence_below_minimum",),
        )

    if gate_config.preferred_score is not None and gate_score < gate_config.preferred_score:
        return GateEvaluation(
            gate_id=gate_id,
            status=GateResultStatus.FOUNDER_REVIEW_REQUIRED,
            gate_score=gate_score,
            gate_confidence=gate_confidence,
            unresolved_reasons=("gate.preferred_score_not_met",),
        )

    if gate_config.minimum_score is not None and gate_score < gate_config.minimum_score:
        return GateEvaluation(
            gate_id=gate_id,
            status=GateResultStatus.DOES_NOT_MEET_GATE,
            gate_score=gate_score,
            gate_confidence=gate_confidence,
            unresolved_reasons=("gate.minimum_score_not_met",),
        )

    return GateEvaluation(
        gate_id=gate_id,
        status=GateResultStatus.ELIGIBLE_TO_ADVANCE,
        gate_score=gate_score,
        gate_confidence=gate_confidence,
        unresolved_reasons=(),
    )


def evaluate_all_gates(
    gates: dict[str, GateConfiguration],
    *,
    confidence_config: ConfidenceConfiguration,
    overall_weights: dict[MethodId, Decimal],
    methods: dict[MethodId, MethodStatusSnapshot],
    vetoes: VetoAssessmentResult,
) -> tuple[GateEvaluation, ...]:
    if set(gates) != {item.value for item in GateId}:
        raise MarketScoringError("gate taxonomy does not match v1")
    return tuple(
        evaluate_gate(
            GateId(key),
            config,
            confidence_config=confidence_config,
            overall_weights=overall_weights,
            methods=methods,
            vetoes=vetoes,
        )
        for key, config in sorted(gates.items())
    )
