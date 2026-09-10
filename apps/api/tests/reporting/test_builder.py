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
    VetoFinding,
    VetoId,
    VetoStatus,
)
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot
from mask_api.modules.reporting.builder import (
    ReportBuildError,
    build_executive_summary,
    build_report_package,
    recommend_next_action,
)
from mask_api.modules.reporting.contracts import MethodCompletenessState
from mask_api.research_runner.configuration import load_formula_configuration, load_source_profile
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
SOURCES = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
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


def base_snapshot(
    *, score: Decimal = Decimal("8"), confidence: Decimal = Decimal("80"), vetoes=None
):
    return build_market_score_snapshot(
        market_id="us_hvac",
        formula=FORMULAS,
        market_definition_version="v1",
        research_profile="default_us_public",
        methods=all_ten(score=score, numeric_confidence=confidence),
        vetoes=vetoes or no_vetoes(),
        generated_at=NOW,
    )


def test_golden_report_composes_scorecard_and_sources() -> None:
    snap = base_snapshot()
    report = build_report_package(
        market_id="us_hvac",
        market_name="US HVAC (10-99 employees)",
        snapshot=snap,
        sources=SOURCES,
        method_detail={MethodId.M1: {"score": "8"}},
        generated_at=NOW,
    )
    assert report.market_name == "US HVAC (10-99 employees)"
    assert len(report.methods) == 10
    m1 = next(item for item in report.methods if item.method_id == MethodId.M1)
    assert m1.raw_score == Decimal("8")
    assert m1.completeness == MethodCompletenessState.PROVEN
    assert m1.risk_adjusted_score == Decimal("8") * (
        Decimal("0.70") + Decimal("0.30") * Decimal("0.80")
    )
    assert m1.detail == {"score": "8"}
    assert len(report.source_inventory) == len(SOURCES.sources)
    assert "provisional" in report.executive_summary.lower()


def test_mismatched_market_id_is_rejected() -> None:
    snap = base_snapshot()
    with pytest.raises(ReportBuildError):
        build_report_package(
            market_id="us_plumbing",
            market_name="US Plumbing",
            snapshot=snap,
            sources=SOURCES,
            generated_at=NOW,
        )


def test_naive_generated_at_is_rejected() -> None:
    snap = base_snapshot()
    with pytest.raises(ReportBuildError):
        build_report_package(
            market_id="us_hvac",
            market_name="US HVAC",
            snapshot=snap,
            sources=SOURCES,
            generated_at=datetime(2026, 9, 10),  # deliberately naive
        )


def test_recommend_next_action_prioritizes_confirmed_veto() -> None:
    vetoes = VetoAssessmentResult(
        market_id="us_hvac",
        formula_version="v1",
        findings=(
            VetoFinding(
                veto_id=VetoId.NO_MEANINGFUL_BUDGET,
                severity="critical",
                status=VetoStatus.CONFIRMED,
                trigger_detail="M4 score 1 < 2",
                evidence_references=("evidence:m4",),
            ),
        ),
        not_evaluated=(),
    )
    snap = base_snapshot(vetoes=vetoes)
    action = recommend_next_action(snap)
    assert "confirmed critical veto" in action
    assert "no_meaningful_budget" in action


def test_recommend_next_action_falls_back_to_missing_method() -> None:
    snap = base_snapshot()  # M8/M10 missing, no vetoes
    action = recommend_next_action(snap)
    assert "Collect evidence" in action


def test_executive_summary_mentions_score_and_confidence() -> None:
    snap = base_snapshot(score=Decimal("6.5"), confidence=Decimal("80"))
    summary = build_executive_summary("US HVAC", snap)
    assert "US HVAC" in summary
    # M8/M10 are missing (fixture), so overall confidence stays unknown even
    # though every present method's own confidence is 80/High.
    assert "confidence unknown" in summary.lower()
    assert "5.59" in summary or "5.60" in summary
