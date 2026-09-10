"""Build the immutable, reproducible v1 market score snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from mask_api.modules.confidence.contracts import MethodStatusSnapshot, VetoAssessmentResult
from mask_api.modules.market_scoring.contracts import (
    AutomatedResearchScore,
    FinalValidatedScore,
    FinalValidatedScoreStatus,
    MarketScoreSnapshot,
    SnapshotCompatibilityKey,
)
from mask_api.modules.market_scoring.gates import evaluate_all_gates
from mask_api.modules.market_scoring.scoring import (
    MarketScoringError,
    aggregate_confidence,
    calculate_automated_research_score,
)
from mask_api.research_runner.contracts import FormulaConfiguration, MethodId


def build_market_score_snapshot(
    *,
    market_id: str,
    formula: FormulaConfiguration,
    market_definition_version: str,
    research_profile: str,
    methods: tuple[MethodStatusSnapshot, ...],
    vetoes: VetoAssessmentResult,
    generated_at: datetime,
) -> MarketScoreSnapshot:
    """Compose one immutable snapshot from already-computed method results.

    This function performs no calculation of its own beyond the aggregation
    rules in `scoring.py`/`gates.py`; it never re-derives a method score,
    confidence dimension, or veto -- those remain each upstream module's
    responsibility, kept separate per MODULARITY.md.
    """
    if generated_at.tzinfo is None:
        raise MarketScoringError("snapshot generation time must be timezone-aware")
    if vetoes.market_id != market_id:
        raise MarketScoringError("veto assessment market_id does not match the snapshot market")
    if vetoes.formula_version != formula.formula_version:
        raise MarketScoringError(
            "veto assessment formula_version does not match the snapshot formula"
        )

    method_map = {item.method_id: item for item in methods}
    if len(method_map) != len(methods):
        raise MarketScoringError("duplicate method_id in snapshot input")

    score, observed_weight, contributing, missing = calculate_automated_research_score(
        dict(formula.overall_weights), method_map
    )
    automated_research_score = AutomatedResearchScore(
        score=score,
        observed_weight=observed_weight,
        contributing_methods=contributing,
        missing_methods=missing,
    )
    # No reviewed-score approval workflow exists yet (P12); the final
    # validated score can never be READY from this offline pipeline alone.
    final_validated_score = FinalValidatedScore(
        status=FinalValidatedScoreStatus.NOT_READY, score=None
    )

    overall_confidence = aggregate_confidence(
        confidence_config=formula.confidence,
        overall_weights=dict(formula.overall_weights),
        required_methods=tuple(MethodId),
        methods=method_map,
    )

    gates = evaluate_all_gates(
        dict(formula.gates),
        confidence_config=formula.confidence,
        overall_weights=dict(formula.overall_weights),
        methods=method_map,
        vetoes=vetoes,
    )

    compatibility = SnapshotCompatibilityKey(
        formula_version=formula.formula_version,
        market_definition_version=market_definition_version,
        research_profile=research_profile,
    )
    inputs_sha256 = _inputs_sha256(market_id, compatibility, methods, vetoes)
    snapshot_id = hashlib.sha256(f"{inputs_sha256}:{generated_at.isoformat()}".encode()).hexdigest()

    return MarketScoreSnapshot(
        snapshot_id=snapshot_id,
        market_id=market_id,
        compatibility=compatibility,
        generated_at=generated_at,
        methods=methods,
        automated_research_score=automated_research_score,
        final_validated_score=final_validated_score,
        overall_confidence=overall_confidence,
        gates=gates,
        vetoes=vetoes,
        inputs_sha256=inputs_sha256,
    )


def _inputs_sha256(
    market_id: str,
    compatibility: SnapshotCompatibilityKey,
    methods: tuple[MethodStatusSnapshot, ...],
    vetoes: VetoAssessmentResult,
) -> str:
    payload = {
        "market_id": market_id,
        "compatibility": compatibility.model_dump(mode="json"),
        "methods": [item.model_dump(mode="json") for item in methods],
        "vetoes": vetoes.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
