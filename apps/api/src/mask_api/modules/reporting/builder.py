"""Compose the v1 report package from an already-built market score snapshot.

This module performs no calculation of its own: every number it presents
comes from `market_scoring`'s `MarketScoreSnapshot`. It only composes,
summarizes in a fixed deterministic template, and recommends the next
action per SCORING.md section 7's priority order (veto investigation before
gate-blocking evidence before lower-priority completeness).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mask_api.modules.confidence.contracts import VetoStatus
from mask_api.modules.market_scoring.contracts import GateResultStatus, MarketScoreSnapshot
from mask_api.modules.market_scoring.scoring import risk_adjusted_method_score
from mask_api.modules.reporting.contracts import (
    MethodReportEntry,
    ReportPackage,
    SourceAttemptOutcome,
    SourceInventoryEntry,
)
from mask_api.research_runner.contracts import MethodId, SourceProfile


class ReportBuildError(ValueError):
    """Inputs do not satisfy the approved v1 report-building contract."""


def build_report_package(
    *,
    market_id: str,
    market_name: str,
    snapshot: MarketScoreSnapshot,
    sources: SourceProfile,
    method_detail: dict[MethodId, dict[str, object]] | None = None,
    source_attempts: tuple[SourceAttemptOutcome, ...] = (),
    generated_at: datetime,
) -> ReportPackage:
    if generated_at.tzinfo is None:
        raise ReportBuildError("report generation time must be timezone-aware")
    if snapshot.market_id != market_id:
        raise ReportBuildError("snapshot market_id does not match the report market")

    detail = method_detail or {}
    method_map = {item.method_id: item for item in snapshot.methods}
    methods = tuple(
        MethodReportEntry(
            method_id=method_id,
            raw_score=method_map[method_id].score,
            confidence=method_map[method_id].confidence,
            risk_adjusted_score=risk_adjusted_method_score(
                method_map[method_id].score, method_map[method_id].confidence
            ),
            completeness=method_map[method_id].completeness,
            detail=detail.get(method_id),
        )
        for method_id in MethodId
        if method_id in method_map
    )

    source_inventory = tuple(
        SourceInventoryEntry(
            source_id=source_id,
            name=config.name,
            access=config.access.value,
            cost_class=config.cost_class,
            operational_status=config.operational_status,
            methods=config.methods,
        )
        for source_id, config in sorted(sources.sources.items())
    )

    return ReportPackage(
        market_id=market_id,
        market_name=market_name,
        formula_version=snapshot.compatibility.formula_version,
        generated_at=generated_at,
        snapshot=snapshot,
        methods=methods,
        source_inventory=source_inventory,
        source_attempts=source_attempts,
        executive_summary=build_executive_summary(market_name, snapshot),
        next_recommended_action=recommend_next_action(snapshot),
    )


def build_executive_summary(market_name: str, snapshot: MarketScoreSnapshot) -> str:
    research = snapshot.automated_research_score
    score_text = f"{research.score:.2f}/10" if research.score is not None else "not yet available"
    coverage_text = f"{(research.observed_weight * Decimal('100')):.0f}%"
    confidence_text = (
        snapshot.overall_confidence.label.value if snapshot.overall_confidence.label else "unknown"
    )
    confirmed_vetoes = sum(
        1
        for finding in snapshot.vetoes.findings
        if finding.status == VetoStatus.CONFIRMED and finding.severity == "critical"
    )
    eligible_gates = sum(
        1 for gate in snapshot.gates if gate.status == GateResultStatus.ELIGIBLE_TO_ADVANCE
    )
    return (
        f"{market_name}: automated research score {score_text} "
        f"({coverage_text} of approved methodology weight observed; "
        f"overall confidence {confidence_text}). "
        f"{confirmed_vetoes} confirmed critical veto(s); "
        f"{eligible_gates} of {len(snapshot.gates)} gates currently eligible to advance. "
        f"This is a provisional, automatically computed score, not the market's "
        f"approved final score -- see next_recommended_action for what to do next."
    )


def recommend_next_action(snapshot: MarketScoreSnapshot) -> str:
    confirmed = tuple(
        finding
        for finding in snapshot.vetoes.findings
        if finding.status == VetoStatus.CONFIRMED and finding.severity == "critical"
    )
    if confirmed:
        first = confirmed[0]
        return (
            f"Investigate confirmed critical veto '{first.veto_id.value}': {first.trigger_detail}"
        )

    suspected = tuple(
        finding for finding in snapshot.vetoes.findings if finding.status == VetoStatus.SUSPECTED
    )
    if suspected:
        first = suspected[0]
        return f"Investigate suspected veto '{first.veto_id.value}': {first.trigger_detail}"

    for gate in sorted(snapshot.gates, key=lambda item: item.gate_id.value):
        if gate.status == GateResultStatus.NOT_READY and gate.missing_methods:
            return (
                f"Collect evidence for {gate.missing_methods[0].value} to progress toward "
                f"{gate.gate_id.value}"
            )

    if snapshot.automated_research_score.missing_methods:
        return (
            f"Collect evidence for {snapshot.automated_research_score.missing_methods[0].value} "
            "to increase observed methodology weight"
        )

    return (
        "All observed methods are complete for the current gate set; awaiting reviewed-score "
        "approval and further gate progression."
    )
