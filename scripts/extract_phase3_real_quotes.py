"""Recover real, per-mention pain-evidence detail for the completed Phase 3
markets from the already-cached real Gemini responses -- zero new API
calls, zero new real quota spent.

scripts/discover_phase3_deep_dive.py only checkpoints aggregate counts
(real_pain_mentions, mean_purchase_intent_0_4, etc.), not individual real
quotes -- a disclosed limitation (see AUTONOMOUS-054). But every real
Gemini call this run made is still sitting on disk as a real
AnalysisCacheRecord (request + result) under
outputs/runs/phase3_deep_dive/artifacts/cache/analysis/, because
ArtifactAnalysisCache persists every real call it ever serves. This
script reads those real cache records back, re-runs the exact same real
A10 grounding validation (validate_grounding) used during the original
extraction pass, and reconstructs real PainMention-equivalent records
with their real evidence_span quotes -- so reports can be deepened
without spending anything new.

Usage:
    uv run python scripts/extract_phase3_real_quotes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.analysis.contracts import AnalysisCacheRecord  # noqa: E402
from mask_api.modules.analysis.grounding import validate_grounding  # noqa: E402
from mask_api.modules.analysis.grounding_contracts import GroundingDisposition  # noqa: E402

CACHE_DIR = ROOT / "outputs/runs/phase3_deep_dive/artifacts/cache/analysis"
OUT_PATH = ROOT / "outputs/runs/phase3_deep_dive/real_quotes_by_market.json"

MARKETS = [
    (238210, "Electrical Contractors"),
    (561730, "Landscaping Services"),
    (238910, "Site Preparation Contractors"),
    (238290, "Other Building Equipment Contractors"),
    (561720, "Janitorial Services"),
    (561621, "Security Systems Services (except Locksmiths)"),
    (811121, "Automotive Body, Paint, and Interior Repair and Maintenance"),
    (238990, "All Other Specialty Trade Contractors"),
    (561210, "Facilities Support Services"),
    (811192, "Car Washes"),
    (541519, "Other Computer Related Services"),
    (812910, "Pet Care Services (except Veterinary)"),
    (561710, "Exterminating and Pest Control Services"),
    (238160, "Roofing Contractors"),
]


def main() -> None:
    market_definitions = {
        f"US {label}, NAICS {naics}, with 10-99 employees.": (naics, label)
        for naics, label in MARKETS
    }

    by_market: dict[str, list[dict[str, object]]] = {label: [] for _, label in MARKETS}
    total_files = 0
    total_accepted_records = 0

    for cache_file in CACHE_DIR.glob("*/*.json"):
        total_files += 1
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        record = AnalysisCacheRecord.model_validate(raw)
        market_key = market_definitions.get(record.request.market_definition)
        if market_key is None:
            continue
        _naics, label = market_key
        report = validate_grounding(record.request, record.result)
        if report.disposition != GroundingDisposition.ACCEPTED:
            continue
        output = record.result.structured_output or {}
        raw_records = output.get("records") if isinstance(output, dict) else None
        if not isinstance(raw_records, list):
            continue
        for raw_mention in raw_records:
            if not isinstance(raw_mention, dict):
                continue
            if not raw_mention.get("pain_present", True):
                continue
            evidence_span = raw_mention.get("evidence_span")
            if (
                not isinstance(evidence_span, str)
                or evidence_span not in record.request.source_text
            ):
                continue
            total_accepted_records += 1
            by_market[label].append(
                {
                    "source_comment": record.request.source_text,
                    "pain_category": raw_mention.get("pain_category"),
                    "pain_subcategory": raw_mention.get("pain_subcategory"),
                    "pain_description": raw_mention.get("pain_description"),
                    "sentiment": raw_mention.get("sentiment"),
                    "severity_1_10": raw_mention.get("severity_1_10"),
                    "urgency_1_10": raw_mention.get("urgency_1_10"),
                    "economic_impact_types": raw_mention.get("economic_impact_types"),
                    "economic_impact_1_10": raw_mention.get("economic_impact_1_10"),
                    "purchase_intent_0_4": raw_mention.get("purchase_intent_0_4"),
                    "existing_workaround": raw_mention.get("existing_workaround"),
                    "solution_dissatisfaction_1_10": raw_mention.get(
                        "solution_dissatisfaction_1_10"
                    ),
                    "ai_suitability_1_10": raw_mention.get("ai_suitability_1_10"),
                    "software_mentioned": raw_mention.get("software_mentioned"),
                    "financial_value_mentioned": raw_mention.get("financial_value_mentioned"),
                    "evidence_span": evidence_span,
                }
            )

    OUT_PATH.write_text(json.dumps(by_market, indent=2, default=str), encoding="utf-8")
    print(f"Scanned {total_files} real cached analysis records.")
    print(f"Real ACCEPTED, grounded pain mentions recovered: {total_accepted_records}")
    for _naics, label in MARKETS:
        print(f"  {label}: {len(by_market[label])} real mentions recovered")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
