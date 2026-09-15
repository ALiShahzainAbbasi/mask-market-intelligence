"""Real M5 competitive-intelligence extraction for us_hvac_10_99 from real
YouTube evidence.

Directive-required pipeline, phase 2 (normalization -> Gemini extraction
-> exact evidence-span verification -> deterministic calculation),
consuming the raw evidence
scripts/collect_youtube_competitor_evidence_us_hvac_10_99.py already
retained.

Granularity: one real comment = one document = one Gemini call, matching
M2/M3's design (CompetitorOutput.records has no per-record persona
either).

No competitive_intelligence module exists yet (unlike pain_intelligence
for M2 and workflow_intelligence for M3), so this script does the
real-record-to-M5Inputs mapping directly rather than inventing a new,
untested module for what turned out to be a modest real evidence volume
-- matching AUTONOMOUS-043's M5 script's precedent (direct M5Inputs
construction from real Gemini-extracted structured fields). The one
genuinely new piece is gap_score_0_10, which the v1 formula requires as
a plain number but which Gemini must never calculate (core project
doctrine). It is derived here by an explicit, deterministic, documented
rule -- gap_score_0_10 = clamp10(2 * distinct real weaknesses mentioned
for that competitor) -- a transparent count of real, evidenced
complaints, not a language-model judgment. This rule is a proposal, not
an approved v1 formula component; it should be reviewed like AUTONOMOUS-
046's M9 judgment calls were.

Usage:
    uv run python scripts/extract_m5_competitors_us_hvac_10_99.py <run_dir>
    (run_dir is the outputs/runs/youtube_competitor_evidence_us_hvac_10_99_*
    directory scripts/collect_youtube_competitor_evidence_us_hvac_10_99.py
    wrote)
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import unicodedata
from collections import defaultdict
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
from mask_api.modules.analysis.grounding_contracts import GroundingDisposition  # noqa: E402
from mask_api.modules.analysis.schemas import CompetitorOutput, CompetitorRecord  # noqa: E402
from mask_api.modules.method_metrics import (  # noqa: E402
    M5CompetitorGap,
    M5Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m5,
)
from mask_api.research_runner.budgets import (  # noqa: E402
    BudgetLedger,
    BudgetLimitExceeded,
    RunBudgetLimits,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402
from mask_api.research_runner.local_artifacts import LocalArtifactStore  # noqa: E402

MARKET_ID = "us_hvac_10_99"
MARKET_DEFINITION = (
    "US HVAC (Plumbing, Heating, and Air-Conditioning) contractors, NAICS 238220, "
    "with 10-99 employees."
)
TASK_INSTRUCTIONS = (
    "This is one real YouTube comment on a video comparing/reviewing HVAC field-service "
    "or dispatch software. Extract any specific, named competitor tool the comment "
    "explicitly discusses with real detail (pricing, a feature, a strength, a weakness, "
    "or a complaint) -- do not infer a competitor from a vague mention. If no specific "
    "named tool is discussed with actual detail, return an empty records list. Never "
    "invent a price: only report pricing.status=exact/starting_at/estimated with an "
    "amount if the comment states one; otherwise pricing.status=unknown with no amount."
)
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_CALLS_SECONDS = 1.2
RUN_ID = f"extract_m5_competitors_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def _normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract_m5_competitors_us_hvac_10_99.py <collection_run_dir>")
    run_dir = Path(sys.argv[1])
    comments = json.loads((run_dir / "comments.json").read_text(encoding="utf-8"))
    candidates = [c for c in comments if len(c["text"]) >= 40]
    print(f"Real collected comments: {len(comments)}")
    print(f"Candidates >= 40 chars: {len(candidates)}")

    load_env_file(ROOT / ".env.official.local")
    load_env_file(ROOT / ".env")
    api_keys = real_configured_gemini_keys()
    if not api_keys:
        raise SystemExit("No MASK_gemini_API_KEY* is configured; cannot run real extraction.")
    print(f"Real Gemini API keys configured: {len(api_keys)}")

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
    client = MultiKeyGeminiClient(api_keys, ArtifactAnalysisCache(artifact_store))
    # Worst case per candidate: one real gemini.http_429 against every
    # configured key (immediate switch, no backoff) plus up to 3 same-key
    # backoff retries for a non-quota transient error -- each attempt,
    # successful or not, charges this ledger (see MultiKeyGeminiClient's
    # docstring), so headroom must cover len(keys)+3 attempts per candidate.
    max_attempts_per_candidate = len(api_keys) + 3
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=len(candidates) * max_attempts_per_candidate + 20,
            max_documents=len(candidates) * max_attempts_per_candidate + 20,
            max_total_bytes=50_000_000,
            max_duration_seconds=3_600,
            max_paid_cost_usd=Decimal("2"),
        )
    )

    extraction_log: list[dict[str, object]] = []
    disposition_counts: dict[str, int] = {}
    records_by_competitor: dict[str, list[CompetitorRecord]] = defaultdict(list)

    for index, comment in enumerate(candidates):
        text = comment["text"]
        normalized_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        request = AnalysisRequest(
            analysis_type=AnalysisType.COMPETITOR,
            schema_id=AnalysisSchemaId.COMPETITOR_V1,
            analysis_version="v1",
            prompt_version="v1",
            schema_version="v1",
            taxonomy_version="competitor-v1",
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
            result = client.analyze(request, ledger)
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
            if report.disposition == GroundingDisposition.ACCEPTED and report.scoring_input:
                output = CompetitorOutput.model_validate(report.scoring_input)
                entry["records_extracted"] = len(output.records)
                for record in output.records:
                    name_key = _normalize_name(record.competitor_name)
                    records_by_competitor[name_key].append(record)
            entry["outcome"] = "processed"
        except GeminiError as error:
            entry["outcome"] = f"gemini_error:{error.code}"
        except BudgetLimitExceeded as error:
            entry["outcome"] = f"budget_exceeded:{error.dimension}"
            extraction_log.append(entry)
            print(f"Budget limit hit ({error.dimension}); stopping the run early.")
            break
        extraction_log.append(entry)

        if (index + 1) % 25 == 0 or index == len(candidates) - 1:
            print(
                f"[{index + 1}/{len(candidates)}] distinct competitors so far: "
                f"{len(records_by_competitor)} dispositions: {disposition_counts}"
            )
            (OUT_DIR / "extraction_log.json").write_text(
                json.dumps(extraction_log, indent=2, default=str), encoding="utf-8"
            )
            (OUT_DIR / "records_by_competitor.json").write_text(
                json.dumps(
                    {
                        name: [record.model_dump(mode="json") for record in records]
                        for name, records in records_by_competitor.items()
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    print(f"\nReal distinct named competitors found: {sorted(records_by_competitor)}")

    m5_result_payload: dict[str, object] | None = None
    m5_error: str | None = None
    if records_by_competitor:
        gaps: list[M5CompetitorGap] = []
        real_prices: list[Decimal] = []
        for name_key, records in records_by_competitor.items():
            weaknesses: set[str] = set()
            spans: list[str] = []
            for record in records:
                for weakness in record.weaknesses:
                    weaknesses.add(_normalize_name(weakness))
                spans.extend(record.evidence_spans)
                pricing = record.pricing
                if pricing.status in ("exact", "starting_at") and pricing.amount is not None:
                    real_prices.append(Decimal(str(pricing.amount)))
            gap_score = min(Decimal(10), Decimal(2 * len(weaknesses)))
            gaps.append(
                M5CompetitorGap(
                    competitor_id=name_key.replace(" ", "_")[:80] or "unknown",
                    gap_score_0_10=gap_score,
                    evidence_count=len(records),
                    evidence_references=tuple(dict.fromkeys(spans))[:20] or ("no_span",),
                )
            )

        def metric(value: Decimal, unit: str, note: str) -> SourcedMetric:
            return SourcedMetric(
                value=value,
                provenance=MetricProvenance(
                    source_id="youtube_comments_gemini_extraction",
                    evidence_reference=note,
                    observation_state=ObservationState.OBSERVED,
                    geography="US",
                    population="Real YouTube commenters on HVAC field-service software videos",
                    period=run_dir.name,
                    unit=unit,
                ),
            )

        median_price: SourcedMetric | None = None
        if real_prices:
            ordered = sorted(real_prices)
            mid = len(ordered) // 2
            median_value = (
                ordered[mid] if len(ordered) % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2
            )
            median_price = metric(
                median_value,
                "USD",
                f"Median of {len(real_prices)} real, explicitly-stated competitor prices "
                "found in real YouTube comments/descriptions.",
            )

        inputs = M5Inputs(
            market_id=MARKET_ID,
            active_relevant_competitor_count=metric(
                Decimal(len(records_by_competitor)),
                "distinct_competitors",
                f"{len(records_by_competitor)} real, distinctly-named competitors extracted "
                f"from {sum(len(r) for r in records_by_competitor.values())} real grounded "
                "mentions across YouTube comments on HVAC field-service software videos.",
            ),
            median_annualized_customer_price_usd=median_price,
            competitor_gaps=tuple(gaps),
            median_offer_similarity_0_1=None,
            verified_reference_count=None,
        )

        formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
        m5_formula = formulas.method_formulas[MethodId.M5]
        try:
            m5_result = calculate_m5(
                formula_version=formulas.formula_version, formula=m5_formula, inputs=inputs
            )
            m5_result_payload = json.loads(m5_result.model_dump_json())
            (OUT_DIR / "m5_result.json").write_text(
                json.dumps(m5_result_payload, indent=2), encoding="utf-8"
            )
            print(f"\nReal M5Result: status={m5_result.status.value} score={m5_result.score}")
            print(f"unknown_reasons={list(m5_result.unknown_reasons)}")
        except Exception as error:  # noqa: BLE001 -- report, never silently drop a real attempt
            m5_error = f"{type(error).__name__}: {error}"
            print(f"\nM5 calculation FAILED (recorded, not silently dropped): {m5_error}")
    else:
        m5_error = "no real, grounded competitor records were extracted"
        print(f"\nM5 not calculated: {m5_error}")

    summary = {
        "market_id": MARKET_ID,
        "collection_run_dir": str(run_dir),
        "candidates_sent_to_gemini": len(candidates),
        "disposition_counts": disposition_counts,
        "distinct_real_competitors": sorted(records_by_competitor),
        "m5_status": m5_result_payload.get("status") if m5_result_payload else "NOT_CALCULATED",
        "m5_error": m5_error,
        "budget_requests_used": ledger.usage.requests,
        "budget_paid_cost_usd": str(ledger.usage.paid_cost_usd),
        "gemini_key_switch_count": client.key_switch_count,
        "gemini_keys_exhausted": client.exhausted_key_count,
    }
    (OUT_DIR / "extraction_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("\nDone.")
    print(json.dumps(summary, indent=2))
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
