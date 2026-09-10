from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    MethodStatusSnapshot,
    VetoAssessmentResult,
)
from mask_api.modules.market_scoring.contracts import (
    FinalValidatedScoreStatus,
    GateResultStatus,
    SnapshotCompatibilityKey,
    snapshots_are_comparable,
)
from mask_api.modules.market_scoring.scoring import MarketScoringError
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot
from mask_api.research_runner.configuration import load_formula_configuration
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
NOW = datetime(2026, 9, 10, tzinfo=UTC)


def snapshot(
    method_id: MethodId, *, score: Decimal | None, numeric_confidence: Decimal | None
) -> MethodStatusSnapshot:
    status = "complete" if score is not None else "unknown"
    confidence = None
    if numeric_confidence is not None:
        label = (
            ConfidenceLabel.HIGH if numeric_confidence >= Decimal("75") else ConfidenceLabel.MEDIUM
        )
        confidence = ConfidenceResult(numeric_confidence=numeric_confidence, label=label)
    return MethodStatusSnapshot(
        method_id=method_id,
        status=status,
        score=score,
        completeness=classify_completeness(status),
        confidence=confidence,
    )


def all_ten(*, score: Decimal, numeric_confidence: Decimal) -> tuple[MethodStatusSnapshot, ...]:
    known = tuple(
        snapshot(method, score=score, numeric_confidence=numeric_confidence)
        for method in MethodId
        if method not in (MethodId.M8, MethodId.M10)
    )
    return known + (
        snapshot(MethodId.M8, score=None, numeric_confidence=None),
        snapshot(MethodId.M10, score=None, numeric_confidence=None),
    )


def no_vetoes(market_id: str = "us_hvac") -> VetoAssessmentResult:
    return VetoAssessmentResult(
        market_id=market_id, formula_version="v1", findings=(), not_evaluated=()
    )


def test_golden_snapshot_composes_score_confidence_and_gates() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    result = build_market_score_snapshot(
        market_id="us_hvac",
        formula=FORMULAS,
        market_definition_version="v1",
        research_profile="default_us_public",
        methods=methods,
        vetoes=no_vetoes(),
        generated_at=NOW,
    )

    assert result.market_id == "us_hvac"
    assert result.automated_research_score.score is not None
    assert result.automated_research_score.score < Decimal("8")  # never renormalized
    assert result.final_validated_score.status == FinalValidatedScoreStatus.NOT_READY
    assert result.final_validated_score.score is None
    assert result.overall_confidence.numeric_confidence is None  # M8/M10 confidence missing
    gate_1 = next(item for item in result.gates if item.gate_id.value == "gate_1")
    assert gate_1.status == GateResultStatus.ELIGIBLE_TO_ADVANCE
    assert len(result.gates) == 4
    assert len(result.methods) == 10


def test_snapshot_is_reproducible_for_identical_inputs() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    first = build_market_score_snapshot(
        market_id="us_hvac",
        formula=FORMULAS,
        market_definition_version="v1",
        research_profile="default_us_public",
        methods=methods,
        vetoes=no_vetoes(),
        generated_at=NOW,
    )
    later = build_market_score_snapshot(
        market_id="us_hvac",
        formula=FORMULAS,
        market_definition_version="v1",
        research_profile="default_us_public",
        methods=methods,
        vetoes=no_vetoes(),
        generated_at=datetime(2026, 9, 11, tzinfo=UTC),
    )
    assert first.inputs_sha256 == later.inputs_sha256
    assert first.snapshot_id != later.snapshot_id  # generation time makes each snapshot unique
    assert first.automated_research_score == later.automated_research_score
    assert first.gates == later.gates


def test_naive_generated_at_is_rejected() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    with pytest.raises(MarketScoringError):
        build_market_score_snapshot(
            market_id="us_hvac",
            formula=FORMULAS,
            market_definition_version="v1",
            research_profile="default_us_public",
            methods=methods,
            vetoes=no_vetoes(),
            generated_at=datetime(2026, 9, 10),  # deliberately naive (no tzinfo)
        )


def test_mismatched_veto_market_id_is_rejected() -> None:
    methods = all_ten(score=Decimal("8"), numeric_confidence=Decimal("80"))
    with pytest.raises(MarketScoringError):
        build_market_score_snapshot(
            market_id="us_hvac",
            formula=FORMULAS,
            market_definition_version="v1",
            research_profile="default_us_public",
            methods=methods,
            vetoes=no_vetoes(market_id="us_plumbing"),
            generated_at=NOW,
        )


def test_snapshots_are_comparable_only_with_matching_compatibility() -> None:
    left = SnapshotCompatibilityKey(
        formula_version="v1", market_definition_version="v1", research_profile="default_us_public"
    )
    same = left.model_copy()
    different_profile = left.model_copy(update={"research_profile": "other_profile"})
    assert snapshots_are_comparable(left, same)
    assert not snapshots_are_comparable(left, different_profile)
