"""Real M2 commercial-pain extraction for us_hvac_10_99 from collected YouTube evidence.

Directive-required pipeline, phase 2 (normalization -> Gemini extraction ->
exact evidence-span verification -> deterministic calculation), consuming
the raw evidence scripts/collect_youtube_pain_evidence_us_hvac_10_99.py
already retained.

Granularity: one real YouTube comment = one document = one Gemini call.
CommercialPainRecord (and GroundedPainContext) carry no per-record
persona -- the pipeline's contract assumes one document has one author,
so batching many different commenters' text into one Gemini call would
force a false shared persona onto genuinely distinct people. A per-video
batch was considered and rejected for exactly this reason.

Only comments with substantive length (>=100 characters, a documented
scope decision for this first real pass, not a silent drop -- every
collected comment remains in the committed raw evidence file regardless)
are sent to Gemini, to keep this run's real call volume practical.

No commenter's real-world persona (owner/employee/customer/vendor) is
knowable from an anonymous YouTube comment alone; every mention in this
pass uses EvidencePersona.UNKNOWN rather than a guessed value -- an
honest gap, not an invented one.

Gemini extracts and classifies only. It never calculates a score. A10's
validate_grounding() rejects any claim whose evidence_span is not an
exact substring of the real comment text before anything becomes
scoring input.

Usage:
    uv run python scripts/extract_m2_pain_us_hvac_10_99.py <run_dir> [max_candidates]
    (run_dir is the outputs/runs/youtube_pain_evidence_us_hvac_10_99_*
    directory scripts/collect_youtube_pain_evidence_us_hvac_10_99.py wrote;
    max_candidates optionally caps real Gemini calls for a smoke test before
    a full paid run)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.analysis.cache import ArtifactAnalysisCache  # noqa: E402
from mask_api.modules.analysis.contracts import (  # noqa: E402
    AnalysisRequest,
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
from mask_api.modules.analysis.grounding_contracts import GroundingDisposition  # noqa: E402
from mask_api.modules.evidence.domain import EvidencePersona  # noqa: E402
from mask_api.modules.pain_intelligence.contracts import (  # noqa: E402
    ClusteringConfiguration,
    GroundedPainContext,
    PainMention,
)
from mask_api.modules.pain_intelligence.embedding_cache import ArtifactEmbeddingCache  # noqa: E402
from mask_api.modules.pain_intelligence.embeddings import (  # noqa: E402
    LOCAL_HASHING_MODEL,
    LOCAL_HASHING_PROVIDER,
    LOCAL_HASHING_VERSION,
    EmbeddingService,
    LocalHashingEmbeddingProvider,
)
from mask_api.modules.pain_intelligence.ingestion import (  # noqa: E402
    PainIngestionError,
    mentions_from_grounding,
)
from mask_api.modules.pain_intelligence.service import PainIntelligenceService  # noqa: E402
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
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
    "This is one public YouTube comment on a video about HVAC dispatch, scheduling, "
    "field service management, or running an HVAC business. Extract any commercial "
    "pain the commenter explicitly and clearly states -- do not infer pain that is "
    "not directly stated. If the comment contains no clear commercial pain, return "
    "an empty records list."
)
MIN_COMMENT_LENGTH = 100
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_CALLS_SECONDS = 1.2
RUN_ID = f"extract_m2_pain_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract_m2_pain_us_hvac_10_99.py <collection_run_dir>")
    run_dir = Path(sys.argv[1])
    comments = json.loads((run_dir / "comments.json").read_text(encoding="utf-8"))

    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_gemini_API_KEY")
    if not api_key:
        raise SystemExit("MASK_gemini_API_KEY is not configured; cannot run real extraction.")

    candidates = [c for c in comments if len(c["text"]) >= MIN_COMMENT_LENGTH]
    print(f"Total collected comments: {len(comments)}")
    print(f"Candidates >= {MIN_COMMENT_LENGTH} chars: {len(candidates)}")
    if len(sys.argv) >= 3:
        max_candidates = int(sys.argv[2])
        candidates = candidates[:max_candidates]
        print(f"Smoke-test cap applied: processing only {len(candidates)} candidates")

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
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=len(candidates) + 10,
            max_documents=len(candidates) + 10,
            max_total_bytes=200_000_000,
            max_duration_seconds=7_200,
            max_paid_cost_usd=Decimal("5"),
        )
    )

    extraction_log: list[dict[str, object]] = []
    disposition_counts: dict[str, int] = {}
    mentions_by_id: dict[str, PainMention] = {}

    for index, comment in enumerate(candidates):
        text = comment["text"]
        normalized_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        request = AnalysisRequest(
            analysis_type=AnalysisType.COMMERCIAL_PAIN,
            schema_id=AnalysisSchemaId.COMMERCIAL_PAIN_V1,
            analysis_version="v1",
            prompt_version="v1",
            schema_version="v1",
            taxonomy_version="commercial-pain-v1",
            normalization_version="youtube-comment-raw-v1",
            normalized_document_sha256=normalized_sha256,
            market_definition=MARKET_DEFINITION,
            task_instructions=TASK_INSTRUCTIONS,
            source_text=text,
            model_policy=policy,
        )
        entry: dict[str, object] = {
            "comment_id": comment["comment_id"],
            "video_id": comment["video_id"],
        }
        try:
            result = adapter.analyze(request, ledger)
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
                context = GroundedPainContext(
                    market_id=MARKET_ID,
                    document_id=f"youtube_comment_{comment['comment_id']}",
                    source_family="youtube_comments",
                    persona=EvidencePersona.UNKNOWN,
                    source_date=_parse_date(comment.get("published_at")),
                )
                try:
                    mentions = mentions_from_grounding(context, report)
                    entry["records_extracted"] = len(mentions)
                    for mention in mentions:
                        mentions_by_id[mention.mention_id] = mention
                except PainIngestionError as error:
                    entry["outcome"] = f"ingestion_error:{error}"
            entry["outcome"] = entry.get("outcome", "processed")
        except GeminiError as error:
            entry["outcome"] = f"gemini_error:{error.code}"
            if error.retryable:
                time.sleep(5.0)
        extraction_log.append(entry)

        if (index + 1) % 25 == 0 or index == len(candidates) - 1:
            print(
                f"[{index + 1}/{len(candidates)}] mentions so far: {len(mentions_by_id)} "
                f"dispositions: {disposition_counts}"
            )
            (OUT_DIR / "extraction_log.json").write_text(
                json.dumps(extraction_log, indent=2, default=str), encoding="utf-8"
            )
            (OUT_DIR / "pain_mentions.json").write_text(
                json.dumps(
                    [json.loads(m.model_dump_json()) for m in mentions_by_id.values()],
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    all_mentions = tuple(mentions_by_id.values())
    all_relevant_unique_documents = len(candidates)
    print(
        f"\nExtraction pass complete. {len(all_mentions)} real pain mentions from "
        f"{len({m.document_id for m in all_mentions})} distinct documents "
        f"(out of {all_relevant_unique_documents} candidate documents assessed)."
    )

    m2_result_payload: dict[str, object] | None = None
    m2_error: str | None = None
    if all_mentions:
        formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
        m2_formula = formulas.method_formulas[MethodId.M2]
        clustering_config = ClusteringConfiguration(
            clustering_version="v1",
            similarity_threshold=Decimal("0.8"),
            near_duplicate_threshold=Decimal("0.99"),
            min_cluster_size=2,
            max_mentions=max(len(all_mentions), 100),
        )
        embeddings = EmbeddingService(
            LocalHashingEmbeddingProvider(),
            ArtifactEmbeddingCache(artifact_store),
            provider_name=LOCAL_HASHING_PROVIDER,
            model_reference=LOCAL_HASHING_MODEL,
            embedding_version=LOCAL_HASHING_VERSION,
            dimensions=64,
        )
        m2_ledger = BudgetLedger(
            RunBudgetLimits(
                max_requests=10,
                max_documents=len(all_mentions) + 10,
                max_total_bytes=50_000_000,
                max_duration_seconds=600,
                max_paid_cost_usd=Decimal("0"),
            )
        )
        try:
            m2_result = PainIntelligenceService(embeddings, clustering_config).run(
                market_id=MARKET_ID,
                formula_version=formulas.formula_version,
                formula=m2_formula,
                all_relevant_unique_documents=all_relevant_unique_documents,
                mentions=all_mentions,
                ledger=m2_ledger,
            )
            m2_result_payload = json.loads(m2_result.model_dump_json())
            (OUT_DIR / "m2_result.json").write_text(
                json.dumps(m2_result_payload, indent=2), encoding="utf-8"
            )
            print(f"\nReal M2Result: status={m2_result.status.value} score={m2_result.score}")
        except Exception as error:  # noqa: BLE001 -- report, never silently drop a real M2 attempt
            m2_error = f"{type(error).__name__}: {error}"
            print(f"\nM2 calculation FAILED (recorded, not silently dropped): {m2_error}")
    else:
        m2_error = "no ACCEPTED pain mentions were extracted from any candidate document"
        print(f"\nM2 not calculated: {m2_error}")

    summary = {
        "market_id": MARKET_ID,
        "collection_run_dir": str(run_dir),
        "total_collected_comments": len(comments),
        "candidates_sent_to_gemini": len(candidates),
        "min_comment_length_filter": MIN_COMMENT_LENGTH,
        "disposition_counts": disposition_counts,
        "total_pain_mentions_extracted": len(all_mentions),
        "all_relevant_unique_documents": all_relevant_unique_documents,
        "m2_status": m2_result_payload.get("status") if m2_result_payload else "NOT_CALCULATED",
        "m2_error": m2_error,
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
