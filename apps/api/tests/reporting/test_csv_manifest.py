from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from mask_api.modules.confidence.completeness import classify_completeness
from mask_api.modules.confidence.contracts import MethodStatusSnapshot, VetoAssessmentResult
from mask_api.modules.market_scoring.snapshot import build_market_score_snapshot
from mask_api.modules.reporting.builder import build_report_package
from mask_api.modules.reporting.contracts import SourceAttemptOutcome
from mask_api.modules.reporting.csv_manifest import render_source_manifest_csv
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


def build_report(source_attempts: tuple[SourceAttemptOutcome, ...] = ()):
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
        market_id="us_hvac",
        market_name="US HVAC",
        snapshot=snap,
        sources=SOURCES,
        source_attempts=source_attempts,
        generated_at=NOW,
    )


def test_csv_manifest_lists_every_registered_source() -> None:
    csv_text = render_source_manifest_csv(build_report())
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == len(SOURCES.sources)
    source_ids = {row["source_id"] for row in rows}
    assert "census_cbp" in source_ids
    assert "youtube" in source_ids


def test_csv_manifest_joins_source_attempt_outcomes() -> None:
    attempt = SourceAttemptOutcome(
        source_id="census_cbp",
        outcome="successful",
        detail="fetched 1 page",
        requests_used=1,
        cache_hits=0,
    )
    csv_text = render_source_manifest_csv(build_report(source_attempts=(attempt,)))
    rows = {row["source_id"]: row for row in csv.DictReader(io.StringIO(csv_text))}
    assert rows["census_cbp"]["attempt_outcome"] == "successful"
    assert rows["census_cbp"]["requests_used"] == "1"
    # A source never attempted this run stays blank, never a fabricated zero-state row.
    untried = next(row for row in rows.values() if row["source_id"] != "census_cbp")
    assert untried["attempt_outcome"] == ""
