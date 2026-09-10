"""Export deterministic JSON Schemas for autonomous research configuration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from mask_api.modules.analysis.contracts import AnalysisSchemaId
from mask_api.modules.analysis.schemas import strict_json_schema
from mask_api.modules.confidence.contracts import MarketMethodSummary, VetoAssessmentResult
from mask_api.modules.market_scoring.contracts import MarketScoreSnapshot
from mask_api.modules.method_metrics.contracts import MethodMetricResult
from mask_api.modules.pain_intelligence.contracts import M2Result
from mask_api.modules.reporting.contracts import ReportPackage
from mask_api.modules.workflow_intelligence.contracts import M3Result
from mask_api.research_runner.contracts import MarketConfiguration, SourceProfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS: dict[Path, Callable[[], dict[str, Any]]] = {
    ROOT / "configs" / "schemas" / "market.schema.json": MarketConfiguration.model_json_schema,
    ROOT / "configs" / "schemas" / "source-profile.schema.json": SourceProfile.model_json_schema,
    ROOT / "configs" / "schemas" / "pain" / "m2-result-v1.schema.json": M2Result.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "method_metrics"
    / "method-metric-result-v1.schema.json": MethodMetricResult.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "workflow"
    / "m3-result-v1.schema.json": M3Result.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "confidence"
    / "market-method-summary-v1.schema.json": MarketMethodSummary.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "confidence"
    / "veto-assessment-result-v1.schema.json": VetoAssessmentResult.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "market_scoring"
    / "market-score-snapshot-v1.schema.json": MarketScoreSnapshot.model_json_schema,
    ROOT
    / "configs"
    / "schemas"
    / "reporting"
    / "report-v1.schema.json": ReportPackage.model_json_schema,
}
for schema_id in AnalysisSchemaId:
    target = ROOT / "configs" / "schemas" / "analysis" / f"{schema_id.value}.schema.json"
    TARGETS[target] = partial(strict_json_schema, schema_id)


def rendered_schema(factory: Callable[[], dict[str, Any]]) -> str:
    return json.dumps(factory(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        for target, factory in TARGETS.items():
            rendered = rendered_schema(factory)
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"research configuration schema is out of date: {target.name}")
        print("Research configuration schema is current.")
        return 0
    for target, factory in TARGETS.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered_schema(factory), encoding="utf-8", newline="\n")
        print(f"Wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
