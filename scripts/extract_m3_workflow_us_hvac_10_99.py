"""Real M3 workflow-bottleneck extraction for us_hvac_10_99 from real O*NET
task statements.

Directive-required pipeline, phase 2 (normalization -> Gemini extraction ->
exact evidence-span verification -> deterministic calculation), consuming
the raw O*NET task statements
scripts/collect_onet_workflow_evidence_us_hvac_10_99.py already retained.

Granularity: one real O*NET task statement = one document = one Gemini
call, matching the M2 extraction script's one-document-per-call design
(WorkflowStepOutput.records has no per-record persona either, so the
same one-document-one-author assumption applies).

O*NET task statements describe real duties of real job incumbents in
this occupation (per O*NET's own survey methodology), so
EvidencePersona.EMPLOYEE is used -- a sourced choice, not a guess, unlike
the anonymous-commenter UNKNOWN used for the M2 YouTube evidence.

O*NET text states WHAT a technician does, never how often, how long, or
how it fails -- so events_per_month/labor_hours_per_month/failure_rate
will honestly come back null for nearly every real step. Per this
project's core doctrine and workflow_intelligence/AGENTS.md, Gemini is
never asked or allowed to invent those; the M3 formula's completeness
rule then honestly reflects that gap (see calculate_m3): if this leaves
M3 UNKNOWN, that is the correct, honest result for this source alone,
not a bug.

Usage:
    uv run python scripts/extract_m3_workflow_us_hvac_10_99.py <run_dir>
    (run_dir is the outputs/runs/onet_workflow_evidence_us_hvac_10_99_*
    directory scripts/collect_onet_workflow_evidence_us_hvac_10_99.py
    wrote)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.analysis.cache import ArtifactAnalysisCache  # noqa: E402
from mask_api.modules.analysis.contracts import (  # noqa: E402
    AnalysisRequest,
    AnalysisResult,
    AnalysisSchemaId,
    AnalysisStatus,
    AnalysisType,
    ModelExecutionPolicy,
)
from mask_api.modules.analysis.gemini import (  # noqa: E402
    GeminiAdapter,
    GeminiError,
    GeminiSettings,
    UrllibGeminiTransport,
)
from mask_api.modules.analysis.grounding import validate_grounding  # noqa: E402
from mask_api.modules.analysis.grounding_contracts import (  # noqa: E402
    GroundingDisposition,
    GroundingReport,
)
from mask_api.modules.evidence.domain import EvidencePersona  # noqa: E402
from mask_api.modules.workflow_intelligence.contracts import GroundedWorkflowContext  # noqa: E402
from mask_api.modules.workflow_intelligence.service import WorkflowIntelligenceService  # noqa: E402
from mask_api.research_runner.budgets import (  # noqa: E402
    BudgetLedger,
    BudgetLimitExceeded,
    RunBudgetLimits,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402
from mask_api.research_runner.local_artifacts import LocalArtifactStore  # noqa: E402
from pydantic import SecretStr  # noqa: E402

MARKET_ID = "us_hvac_10_99"
MARKET_DEFINITION = (
    "US HVAC (Plumbing, Heating, and Air-Conditioning) contractors, NAICS 238220, "
    "with 10-99 employees."
)
TASK_INSTRUCTIONS = (
    "This is one real O*NET task statement describing a duty performed by a "
    "Heating, Air Conditioning, and Refrigeration Mechanic/Installer (O*NET-SOC "
    "49-9021.00). Extract it as one workflow step: who performs it (role), what "
    "system/tool it involves if stated, its input/output if stated, and any "
    "consequence or automation potential that is genuinely implied by the text. "
    "Do NOT invent a frequency (events_per_month), a labor-hours figure, a "
    "waiting time, or a failure rate -- O*NET task statements do not state these; "
    "leave those fields null rather than guessing a plausible-sounding number."
)
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_CALLS_SECONDS = 1.2
RUN_ID = f"extract_m3_workflow_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def _analyze_with_retry(
    adapter: GeminiAdapter, request: AnalysisRequest, ledger: BudgetLedger
) -> AnalysisResult:
    """Retry a retryable GeminiError (429/5xx) with backoff instead of giving up
    on the first transient failure -- a real rate-limit window (hit live during
    this run, right after the M2 script's 600 real calls) recovers in well
    under a minute, so skipping the task outright would silently lose real
    evidence rather than actually failing to obtain it."""
    delays = (10.0, 20.0, 40.0)
    for attempt, delay in enumerate((0.0, *delays)):
        if delay:
            time.sleep(delay)
        try:
            return adapter.analyze(request, ledger)
        except GeminiError as error:
            if not error.retryable or attempt == len(delays):
                raise
    raise AssertionError("unreachable")


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract_m3_workflow_us_hvac_10_99.py <collection_run_dir>")
    run_dir = Path(sys.argv[1])
    tasks = json.loads((run_dir / "task_statements.json").read_text(encoding="utf-8"))
    print(f"Real O*NET task statements: {len(tasks)}")

    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_gemini_API_KEY")
    if not api_key:
        raise SystemExit("MASK_gemini_API_KEY is not configured; cannot run real extraction.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_store = LocalArtifactStore(OUT_DIR / "artifacts")

    policy = ModelExecutionPolicy(
        model_reference=MODEL_REFERENCE,
        input_token_budget=4_000,
        max_output_tokens=2_000,
        input_usd_per_million_tokens=Decimal("0.30"),
        output_usd_per_million_tokens=Decimal("2.50"),
        max_call_cost_usd=Decimal("0.01"),
    )
    adapter = GeminiAdapter(
        GeminiSettings(
            enabled=True,
            policy_approved=True,
            api_key=SecretStr(api_key),
            timeout_seconds=30,
        ),
        UrllibGeminiTransport(),
        ArtifactAnalysisCache(artifact_store),
        now=lambda: datetime.now(UTC),
    )
    # Each task can retry up to 4 times total (see _analyze_with_retry), and
    # every attempt -- including a failed one -- consumes real request/byte
    # budget (GeminiAdapter.analyze() charges the ledger before checking the
    # HTTP status). A tight max_requests hit BudgetLimitExceeded mid-run the
    # first time this ran with retries live -- verified, not hypothetical.
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=len(tasks) * 5 + 20,
            max_documents=len(tasks) * 5 + 20,
            max_total_bytes=50_000_000,
            max_duration_seconds=3_600,
            max_paid_cost_usd=Decimal("2"),
        )
    )

    extraction_log: list[dict[str, object]] = []
    disposition_counts: dict[str, int] = {}
    grounded_documents: list[tuple[GroundedWorkflowContext, GroundingReport]] = []

    for index, task in enumerate(tasks):
        text = task["task"]
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
            market_definition=MARKET_DEFINITION,
            task_instructions=TASK_INSTRUCTIONS,
            source_text=text,
            model_policy=policy,
        )
        entry: dict[str, object] = {"task_id": task["task_id"], "task": text[:80]}
        try:
            result = _analyze_with_retry(adapter, request, ledger)
            if result.status != AnalysisStatus.COMPLETED:
                entry["outcome"] = f"analysis_{result.status.value}"
                extraction_log.append(entry)
                continue
            report = validate_grounding(request, result)
            disposition_counts[report.disposition.value] = (
                disposition_counts.get(report.disposition.value, 0) + 1
            )
            entry["disposition"] = report.disposition.value
            entry["issue_codes"] = [issue.code.value for issue in report.issues]
            if report.disposition == GroundingDisposition.ACCEPTED:
                context = GroundedWorkflowContext(
                    market_id=MARKET_ID,
                    document_id=f"onet_task_{task['task_id']}",
                    source_family="onet_task_statements",
                    persona=EvidencePersona.EMPLOYEE,
                    source_date=None,
                )
                grounded_documents.append((context, report))
            entry["outcome"] = "processed"
        except GeminiError as error:
            entry["outcome"] = f"gemini_error:{error.code}"
        except BudgetLimitExceeded as error:
            entry["outcome"] = f"budget_exceeded:{error.dimension}"
            extraction_log.append(entry)
            print(f"Budget limit hit ({error.dimension}); stopping the run early.")
            break
        extraction_log.append(entry)

        if (index + 1) % 10 == 0 or index == len(tasks) - 1:
            print(
                f"[{index + 1}/{len(tasks)}] grounded so far: {len(grounded_documents)} "
                f"dispositions: {disposition_counts}"
            )
            (OUT_DIR / "extraction_log.json").write_text(
                json.dumps(extraction_log, indent=2, default=str), encoding="utf-8"
            )
        time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    m3_result_payload: dict[str, object] | None = None
    m3_error: str | None = None
    if grounded_documents:
        formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
        m3_formula = formulas.method_formulas[MethodId.M3]
        try:
            m3_result = WorkflowIntelligenceService().run(
                market_id=MARKET_ID,
                formula_version=formulas.formula_version,
                formula=m3_formula,
                grounded_documents=tuple(grounded_documents),
            )
            m3_result_payload = json.loads(m3_result.model_dump_json())
            (OUT_DIR / "m3_result.json").write_text(
                json.dumps(m3_result_payload, indent=2), encoding="utf-8"
            )
            print(f"\nReal M3Result: status={m3_result.status.value} score={m3_result.score}")
            print(f"unknown_reasons={list(m3_result.unknown_reasons)}")
        except Exception as error:  # noqa: BLE001 -- report, never silently drop a real M3 attempt
            m3_error = f"{type(error).__name__}: {error}"
            print(f"\nM3 calculation FAILED (recorded, not silently dropped): {m3_error}")
    else:
        m3_error = "no ACCEPTED workflow-step documents were extracted from any task statement"
        print(f"\nM3 not calculated: {m3_error}")

    summary = {
        "market_id": MARKET_ID,
        "collection_run_dir": str(run_dir),
        "total_task_statements": len(tasks),
        "disposition_counts": disposition_counts,
        "grounded_documents": len(grounded_documents),
        "m3_status": m3_result_payload.get("status") if m3_result_payload else "NOT_CALCULATED",
        "m3_error": m3_error,
        "budget_requests_used": ledger.usage.requests,
        "budget_paid_cost_usd": str(ledger.usage.paid_cost_usd),
    }
    (OUT_DIR / "extraction_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("\nDone.")
    print(json.dumps(summary, indent=2))
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
