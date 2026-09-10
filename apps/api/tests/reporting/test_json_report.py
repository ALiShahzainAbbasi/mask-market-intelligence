from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import MethodStatusSnapshot, VetoAssessmentResult
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot
from mask_api.modules.reporting.builder import build_report_package
from mask_api.modules.reporting.contracts import ReportPackage
from mask_api.modules.reporting.json_report import render_json_report
from mask_api.research_runner.configuration import load_formula_configuration, load_source_profile
from mask_api.research_runner.contracts import MethodId

ROOT = Path(__file__).parents[4]
FORMULAS = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
SOURCES = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
NOW = datetime(2026, 9, 10, tzinfo=UTC)


def snapshot(method_id: MethodId, *, score: Decimal | None) -> MethodStatusSnapshot:
    status = "complete" if score is not None else "unknown"
    return MethodStatusSnapshot(
        method_id=method_id, status=status, score=score, completeness=classify_completeness(status)
    )


def build_report():
    methods = tuple(
        snapshot(method, score=Decimal("8"))
        for method in MethodId
        if method not in (MethodId.M8, MethodId.M10)
    ) + (snapshot(MethodId.M8, score=None), snapshot(MethodId.M10, score=None))
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
        market_id="us_hvac", market_name="US HVAC", snapshot=snap, sources=SOURCES, generated_at=NOW
    )


def test_json_report_round_trips_through_the_contract() -> None:
    report = build_report()
    rendered = render_json_report(report)
    parsed = json.loads(rendered)
    assert parsed["schema_version"] == "report-v1"
    assert parsed["market_id"] == "us_hvac"
    round_tripped = ReportPackage.model_validate(parsed)
    assert round_tripped == report


def test_json_report_is_deterministic_for_identical_input() -> None:
    report = build_report()
    assert render_json_report(report) == render_json_report(report)
