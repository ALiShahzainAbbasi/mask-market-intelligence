from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import (
    ConfidenceLabel,
    ConfidenceResult,
    MethodStatusSnapshot,
    VetoAssessmentResult,
)
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot
from mask_api.modules.reporting.builder import build_report_package
from mask_api.modules.reporting.html_report import render_html_report
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
        confidence = ConfidenceResult(
            numeric_confidence=numeric_confidence, label=ConfidenceLabel.HIGH
        )
    return MethodStatusSnapshot(
        method_id=method_id,
        status=status,
        score=score,
        completeness=classify_completeness(status),
        confidence=confidence,
    )


def build_report(*, evidence_text: str = "ordinary evidence span"):
    methods = tuple(
        snapshot(method, score=Decimal("8"), numeric_confidence=Decimal("80"))
        for method in MethodId
        if method not in (MethodId.M8, MethodId.M10)
    ) + (
        snapshot(MethodId.M8, score=None, numeric_confidence=None),
        snapshot(MethodId.M10, score=None, numeric_confidence=None),
    )
    vetoes = VetoAssessmentResult(
        market_id="us_hvac", formula_version="v1", findings=(), not_evaluated=()
    )
    snap = build_market_score_snapshot(
        market_id="us_hvac",
        formula=FORMULAS,
        market_definition_version="v1",
        research_profile="default_us_public",
        methods=methods,
        vetoes=vetoes,
        generated_at=NOW,
    )
    return build_report_package(
        market_id="us_hvac",
        market_name="US HVAC",
        snapshot=snap,
        sources=SOURCES,
        method_detail={MethodId.M1: {"evidence_span": evidence_text}},
        generated_at=NOW,
    )


def test_html_report_contains_key_sections() -> None:
    html = render_html_report(build_report())
    assert "<h1>US HVAC</h1>" in html
    assert "Executive Summary" in html
    assert "M1&ndash;M10 Scorecard" in html
    assert "Gate Readiness" in html
    assert "Source Inventory" in html
    assert "M1" in html


def test_html_report_escapes_untrusted_evidence_text() -> None:
    malicious = "<script>alert(1)</script>"
    html = render_html_report(build_report(evidence_text=malicious))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_report_is_well_formed_enough_to_have_matching_tags() -> None:
    html = render_html_report(build_report())
    assert html.count("<table>") == html.count("</table>")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
