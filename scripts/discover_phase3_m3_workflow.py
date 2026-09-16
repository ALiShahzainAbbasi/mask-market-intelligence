"""Real M3 (Workflow Intelligence) for the 14 Phase 3 shortlist markets,
matching HVAC's own real M3 pipeline exactly (O*NET task statements ->
Gemini WORKFLOW_STEP extraction -> A10 grounding -> real
WorkflowIntelligenceService.run()).

Reuses the O*NET dataset already bootstrapped locally for us_hvac_10_99
(no new download). Real SOC-code matches were found and verified via
scripts/match_onet_occupations_phase3.py (printed titles/task counts from
the real dataset, not guessed) for 12 of the 14 markets; 2 (All Other
Specialty Trade Contractors, Car Washes) have no single real front-line
occupation in O*NET -- honestly skipped, not forced onto a mismatched
occupation.

Real, expected outcome (matching HVAC precedent): O*NET task statements
describe WHAT a worker does, never frequency/labor-hours/failure-rate, so
M3 is very likely to stay real UNKNOWN for every market here too -- this
run is for completeness/audit-trail parity with HVAC's report depth, not
because it is expected to change any market's score.

Usage:
    uv run python scripts/discover_phase3_m3_workflow.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _gemini_multi_key import (  # noqa: E402
    MultiKeyGeminiClient,
    load_env_file,
    real_configured_gemini_keys,
)
from mask_api.modules.analysis.cache import ArtifactAnalysisCache  # noqa: E402
from mask_api.modules.analysis.contracts import (  # noqa: E402
    AnalysisRequest,
    AnalysisSchemaId,
    AnalysisStatus,
    AnalysisType,
    ModelExecutionPolicy,
)
from mask_api.modules.analysis.gemini import GeminiError  # noqa: E402
from mask_api.modules.analysis.grounding import validate_grounding  # noqa: E402
from mask_api.modules.analysis.grounding_contracts import (  # noqa: E402
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.evidence.domain import EvidencePersona  # noqa: E402
from mask_api.modules.onet_data.bootstrap import (  # noqa: E402
    OnetBootstrapper,
    OnetBootstrapSettings,
)
from mask_api.modules.onet_data.cache import LocalOnetCache  # noqa: E402
from mask_api.modules.onet_data.transport import UrllibOnetTransport  # noqa: E402
from mask_api.modules.workflow_intelligence.contracts import GroundedWorkflowContext  # noqa: E402
from mask_api.modules.workflow_intelligence.service import WorkflowIntelligenceService  # noqa: E402
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402
from mask_api.research_runner.local_artifacts import LocalArtifactStore  # noqa: E402

ONET_CACHE_DIR = ROOT / ".cache" / "onet"
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_CALLS_SECONDS = 1.2

RUN_ID = f"phase3_m3_workflow_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID

# Real, verified (not guessed) O*NET-SOC matches -- see
# scripts/match_onet_occupations_phase3.py's output for the real titles
# and task counts this was chosen from.
MARKET_SOC: list[tuple[int, str, str | None]] = [
    (238210, "Electrical Contractors", "47-2111.00"),
    (561730, "Landscaping Services", "37-3011.00"),
    (238910, "Site Preparation Contractors", "47-2073.00"),
    (238290, "Other Building Equipment Contractors", "47-4021.00"),
    (561720, "Janitorial Services", "37-2011.00"),
    (561621, "Security Systems Services (except Locksmiths)", "49-2098.00"),
    (811121, "Automotive Body, Paint, and Interior Repair and Maintenance", "49-3021.00"),
    (238990, "All Other Specialty Trade Contractors", None),
    (561210, "Facilities Support Services", "49-9071.00"),
    (811192, "Car Washes", None),
    (541519, "Other Computer Related Services", "15-1232.00"),
    (812910, "Pet Care Services (except Veterinary)", "39-2021.00"),
    (561710, "Exterminating and Pest Control Services", "37-2021.00"),
    (238160, "Roofing Contractors", "47-2181.00"),
]


def main() -> None:
    load_env_file(ROOT / ".env.official.local")
    load_env_file(ROOT / ".env")
    gemini_keys = real_configured_gemini_keys()
    if not gemini_keys:
        raise SystemExit("No real Gemini API keys are configured.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_store = LocalArtifactStore(OUT_DIR / "artifacts")
    gemini_client = MultiKeyGeminiClient(gemini_keys, ArtifactAnalysisCache(artifact_store))

    onet_ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=5,
            max_documents=5,
            max_total_bytes=30_000_000,
            max_duration_seconds=1_800,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    bootstrapper = OnetBootstrapper(
        OnetBootstrapSettings(enabled=True, policy_approved=True),
        UrllibOnetTransport(),
        LocalOnetCache(ONET_CACHE_DIR),
    )
    descriptor = bootstrapper.ensure_dataset(onet_ledger)
    batch = bootstrapper.import_batch(descriptor)
    print(f"Real O*NET dataset {descriptor.version}: {len(batch.occupations)} occupations")

    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m3_formula = formulas.method_formulas[MethodId.M3]

    all_results: list[dict[str, object]] = []
    gemini_ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=5_000,
            max_documents=5_000,
            max_total_bytes=200_000_000,
            max_duration_seconds=21_600,
            max_paid_cost_usd=Decimal("5"),
        )
    )

    for naics, label, soc in MARKET_SOC:
        market_id = f"us_p3m3_{naics}"
        print(f"\n=== NAICS {naics} {label} (SOC {soc}) ===")
        if soc is None:
            print("  SKIPPED: no real single front-line O*NET occupation for this NAICS.")
            all_results.append(
                {
                    "naics": naics,
                    "label": label,
                    "onet_soc_code": None,
                    "status": "SKIPPED_NO_CLEAN_OCCUPATION",
                }
            )
            continue

        occupation = next((o for o in batch.occupations if o.onet_soc_code == soc), None)
        if occupation is None:
            print(f"  SOC {soc} not found in real dataset -- skipping.")
            all_results.append(
                {"naics": naics, "label": label, "onet_soc_code": soc, "status": "SOC_NOT_FOUND"}
            )
            continue
        tasks = tuple(t for t in batch.task_statements if t.onet_soc_code == soc)
        print(f"  Real occupation: {occupation.title} -- {len(tasks)} real task statements")

        market_definition = f"US {label}, NAICS {naics}, with 10-99 employees."
        task_instructions = (
            f"This is one real O*NET task statement describing a duty performed by a "
            f"{occupation.title} (O*NET-SOC {soc}). Extract it as one workflow step: who "
            "performs it (role), what system/tool it involves if stated, its input/output "
            "if stated, and any consequence or automation potential genuinely implied by "
            "the text. Do NOT invent a frequency, labor-hours figure, waiting time, or "
            "failure rate -- O*NET task statements do not state these; leave those fields "
            "null rather than guessing."
        )

        grounded_documents: list[tuple[GroundedWorkflowContext, GroundingReport]] = []
        disposition_counts: dict[str, int] = {}
        for task in tasks:
            text = task.task
            normalized_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            request = AnalysisRequest(
                analysis_type=AnalysisType.WORKFLOW_STEP,
                schema_id=AnalysisSchemaId.WORKFLOW_STEP_V1,
                analysis_version="v1",
                prompt_version="v1",
                schema_version="v1",
                taxonomy_version="workflow-step-v1",
                normalization_version="onet-task-statement-raw-v1",
                normalized_document_sha256=normalized_sha256,
                market_definition=market_definition,
                task_instructions=task_instructions,
                source_text=text,
                model_policy=ModelExecutionPolicy(
                    model_reference=MODEL_REFERENCE,
                    input_token_budget=4_000,
                    max_output_tokens=2_000,
                    input_usd_per_million_tokens=Decimal("0.30"),
                    output_usd_per_million_tokens=Decimal("2.50"),
                    max_call_cost_usd=Decimal("0.01"),
                ),
            )
            try:
                result = gemini_client.analyze(request, gemini_ledger)
                if result.status == AnalysisStatus.COMPLETED:
                    report = validate_grounding(request, result)
                    disposition_counts[report.disposition.value] = (
                        disposition_counts.get(report.disposition.value, 0) + 1
                    )
                    if report.disposition == GroundingDisposition.ACCEPTED:
                        context = GroundedWorkflowContext(
                            market_id=market_id,
                            document_id=f"onet_task_{task.task_id}",
                            source_family="onet_task_statements",
                            persona=EvidencePersona.EMPLOYEE,
                            source_date=None,
                        )
                        grounded_documents.append((context, report))
            except GeminiError as error:
                disposition_counts[f"gemini_error:{error.code}"] = (
                    disposition_counts.get(f"gemini_error:{error.code}", 0) + 1
                )
            time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

        print(f"  Real grounded workflow steps: {len(grounded_documents)} / {len(tasks)}")
        market_result: dict[str, object] = {
            "naics": naics,
            "label": label,
            "onet_soc_code": soc,
            "occupation_title": occupation.title,
            "total_task_statements": len(tasks),
            "disposition_counts": disposition_counts,
            "grounded_documents": len(grounded_documents),
        }
        if grounded_documents:
            try:
                m3_result = WorkflowIntelligenceService().run(
                    market_id=market_id,
                    formula_version=formulas.formula_version,
                    formula=m3_formula,
                    grounded_documents=tuple(grounded_documents),
                )
                market_result["status"] = m3_result.status.value
                market_result["score"] = str(m3_result.score) if m3_result.score else None
                market_result["unknown_reasons"] = list(m3_result.unknown_reasons)
                print(f"  Real M3Result: status={m3_result.status.value} score={m3_result.score}")
            except Exception as error:  # noqa: BLE001 -- report, never silently drop
                market_result["status"] = "ERROR"
                market_result["error"] = f"{type(error).__name__}: {error}"
        else:
            market_result["status"] = "NOT_CALCULATED"
            market_result["error"] = "no ACCEPTED workflow-step documents extracted"
        all_results.append(market_result)

        (OUT_DIR / "phase3_m3_results.json").write_text(
            json.dumps(all_results, indent=2, default=str), encoding="utf-8"
        )

    print(f"\n\nDone. Output: {OUT_DIR}")
    for r in all_results:
        print(f"  {r['naics']} {r['label']}: {r.get('status')}")


if __name__ == "__main__":
    main()
