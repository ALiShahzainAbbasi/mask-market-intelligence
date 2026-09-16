"""Real M5 (Competitive Intelligence) for the 14 Phase 3 shortlist markets,
matching HVAC's own real M5 pipeline (YouTube competitor-focused search ->
Gemini COMPETITOR_V1 extraction -> A10 grounding -> real calculate_m5()),
generalized across markets and made quota-aware/resumable the same way
scripts/discover_phase3_deep_dive.py is.

HVAC's own M5 queries named specific competitors already known from prior
M1/M2 research (Jobber, Housecall Pro, ServiceTitan, FieldEdge). These 14
markets have no such prior knowledge, so queries here are generic but
still competitor/pricing/review-focused (not pain-focused, which M2
already covers) -- 6 queries/market, matching Phase 3's existing budget
discipline.

REAL DAILY QUOTA CONSTRAINT: update QUOTA_ALREADY_USED_TODAY before every
run to reflect what this real Google account has genuinely already spent
on the CURRENT real Pacific quota day (YouTube resets at Pacific
midnight) -- never carry a stale prior-day value forward. At 6 queries x
100 + comment-thread fetches (~650-700 real units/market), this will
span multiple real days across all 14 markets (~8,400+ units needed for
search alone).

Usage:
    uv run python scripts/discover_phase3_m5_competitors.py
    (safe to re-run on a later real day; resumes from its own checkpoint)
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
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
from mask_api.modules.youtube_data.quota import (  # noqa: E402
    YouTubeQuotaExceeded,
    YouTubeQuotaLedger,
    YouTubeQuotaLimits,
)
from mask_api.modules.youtube_data.requests import (  # noqa: E402
    youtube_comment_threads_request,
    youtube_search_request,
)
from mask_api.modules.youtube_data.transport import (  # noqa: E402
    UrllibYouTubeTransport,
    YouTubeApiAdapter,
    YouTubeApiSettings,
    YouTubeTransportError,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402
from mask_api.research_runner.configuration import (  # noqa: E402
    load_formula_configuration,
    load_source_profile,
)
from mask_api.research_runner.contracts import FormulaConfiguration, MethodId  # noqa: E402
from mask_api.research_runner.local_artifacts import LocalArtifactStore  # noqa: E402
from pydantic import SecretStr  # noqa: E402

# 2026-09-16: update this before every real invocation -- see module docstring.
QUOTA_ALREADY_USED_TODAY = 0
DAILY_QUOTA_LIMIT = 9_000
QUOTA_SAFETY_MARGIN = 100

RESULTS_PER_QUERY = 10
MAX_COMMENTS_PER_VIDEO = 50
MIN_COMMENT_LENGTH = 40
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_CALLS_SECONDS = 1.2
# See scripts/discover_phase3_deep_dive.py's GEMINI_CALL_TIMEOUT_SECONDS
# docstring: a real, reproducible indefinite hang was found live in this
# same MultiKeyGeminiClient call path (2026-09-16/17). Every real call
# here is wrapped in the same hard wall-clock timeout for the same reason.
GEMINI_CALL_TIMEOUT_SECONDS = 45.0

OUT_DIR = ROOT / "outputs" / "runs" / "phase3_m5_competitors"
RESULTS_PATH = OUT_DIR / "phase3_m5_results.json"

MARKETS: list[tuple[int, str]] = [
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


def _normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _normalize_competitor_name(value: str) -> str:
    return "".join(_normalize_name(value).split())


def _queries_for(label: str) -> list[str]:
    clean = re.sub(r"\([^)]*\)", "", label).strip()
    return [
        f"{clean} business software review pricing",
        f"{clean} scheduling software comparison",
        f"best {clean} software 2026",
        f"{clean} CRM software review",
        f"{clean} dispatch software complaints",
        f"{clean} business software vs",
    ]


def _load_checkpoint() -> dict[str, dict[str, object]]:
    if RESULTS_PATH.is_file():
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        return {str(r["naics"]): r for r in data.get("results", [])}
    return {}


def _save_checkpoint(
    results_by_naics: dict[str, dict[str, object]], quota: YouTubeQuotaLedger
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "youtube_quota_units_used_today": quota.units_used,
                "results": list(results_by_naics.values()),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


def _collect_youtube(
    *,
    label: str,
    adapter: YouTubeApiAdapter,
    api_key: str,
    ledger: BudgetLedger,
    quota: YouTubeQuotaLedger,
) -> tuple[list[dict[str, object]], list[str]]:
    videos: dict[str, dict[str, object]] = {}
    notes: list[str] = []
    for query in _queries_for(label):
        request = youtube_search_request(
            query=query, api_key=SecretStr(api_key), max_results=RESULTS_PER_QUERY
        )
        result = adapter.fetch(request, ledger, quota)
        new = 0
        for video in result.batch.videos:
            if video.video_id not in videos:
                new += 1
                videos[video.video_id] = {"video_id": video.video_id, "title": video.title}
        notes.append(f"SEARCH '{query}': {len(result.batch.videos)} results, {new} new")

    all_comments: list[dict[str, object]] = []
    for video_id in videos:
        try:
            request = youtube_comment_threads_request(
                video_id=video_id, api_key=SecretStr(api_key), max_results=MAX_COMMENTS_PER_VIDEO
            )
            comment_result = adapter.fetch(request, ledger, quota)
            for comment in comment_result.batch.comments:
                all_comments.append(
                    {
                        "comment_id": comment.comment_id,
                        "video_id": comment.video_id,
                        "text": comment.text,
                    }
                )
        except YouTubeQuotaExceeded:
            notes.append(f"COMMENTS video={video_id}: STOPPED real daily quota exhausted")
            break
        except YouTubeTransportError as error:
            notes.append(f"COMMENTS video={video_id}: SKIPPED {error.code}")
    notes.append(f"videos={len(videos)} comments={len(all_comments)}")
    return all_comments, notes


def _extract_competitors(
    *,
    naics: int,
    label: str,
    comments: list[dict[str, object]],
    gemini_client: MultiKeyGeminiClient,
    ledger: BudgetLedger,
) -> tuple[dict[str, list[CompetitorRecord]], dict[str, int]]:
    market_definition = f"US {label}, NAICS {naics}, with 10-99 employees."
    task_instructions = (
        f"This is one real YouTube comment on a video related to {label} business "
        "software, reviews, or comparisons. Extract any specific, named competitor "
        "tool the comment explicitly discusses with real detail (pricing, a feature, "
        "a strength, a weakness, or a complaint) -- do not infer a competitor from a "
        "vague mention. If no specific named tool is discussed with actual detail, "
        "return an empty records list. Never invent a price: only report "
        "pricing.status=exact/starting_at/estimated with an amount if the comment "
        "states one; otherwise pricing.status=unknown with no amount."
    )
    candidates = [c for c in comments if len(str(c["text"])) >= MIN_COMMENT_LENGTH]
    records_by_competitor: dict[str, list[CompetitorRecord]] = defaultdict(list)
    disposition_counts: dict[str, int] = {}
    for index, comment in enumerate(candidates):
        text = str(comment["text"])
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
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(gemini_client.analyze, request, ledger)
            try:
                result = future.result(timeout=GEMINI_CALL_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False)
                disposition_counts["real_call_timeout_abandoned"] = (
                    disposition_counts.get("real_call_timeout_abandoned", 0) + 1
                )
                print(
                    f"    [{index + 1}/{len(candidates)}] Gemini call exceeded "
                    f"{GEMINI_CALL_TIMEOUT_SECONDS}s -- abandoned, continuing."
                )
                continue
            executor.shutdown(wait=False)
            if result.status != AnalysisStatus.COMPLETED:
                continue
            report = validate_grounding(request, result)
            disposition_counts[report.disposition.value] = (
                disposition_counts.get(report.disposition.value, 0) + 1
            )
            if report.disposition == GroundingDisposition.ACCEPTED and report.scoring_input:
                output = CompetitorOutput.model_validate(report.scoring_input)
                for record in output.records:
                    name_key = _normalize_competitor_name(record.competitor_name)
                    records_by_competitor[name_key].append(record)
        except GeminiError as error:
            disposition_counts[f"gemini_error:{error.code}"] = (
                disposition_counts.get(f"gemini_error:{error.code}", 0) + 1
            )
        if (index + 1) % 25 == 0 or index == len(candidates) - 1:
            print(
                f"    [{index + 1}/{len(candidates)}] distinct competitors so far: "
                f"{len(records_by_competitor)}"
            )
        time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)
    return records_by_competitor, disposition_counts


def _score_market(
    *,
    naics: int,
    label: str,
    records_by_competitor: dict[str, list[CompetitorRecord]],
    formulas: FormulaConfiguration,
) -> dict[str, object]:
    market_id = f"us_p3m5_{naics}"
    if not records_by_competitor:
        return {
            "naics": naics,
            "label": label,
            "status": "NOT_CALCULATED",
            "error": "no real, grounded competitor records were extracted",
            "distinct_real_competitors": [],
        }

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
                population=f"Real YouTube commenters on {label} software videos",
                period="phase3_m5_competitors",
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
            f"Median of {len(real_prices)} real, explicitly-stated competitor prices.",
        )

    inputs = M5Inputs(
        market_id=market_id,
        active_relevant_competitor_count=metric(
            Decimal(len(records_by_competitor)),
            "distinct_competitors",
            f"{len(records_by_competitor)} real, distinctly-named competitors extracted "
            f"from {sum(len(r) for r in records_by_competitor.values())} real grounded mentions.",
        ),
        median_annualized_customer_price_usd=median_price,
        competitor_gaps=tuple(gaps),
        median_offer_similarity_0_1=None,
        verified_reference_count=None,
    )
    m5_formula = formulas.method_formulas[MethodId.M5]
    result = calculate_m5(
        formula_version=formulas.formula_version,
        formula=m5_formula,
        inputs=inputs,
    )
    return {
        "naics": naics,
        "label": label,
        "status": result.status.value,
        "score": str(result.score) if result.score is not None else None,
        "unknown_reasons": list(result.unknown_reasons),
        "distinct_real_competitors": sorted(records_by_competitor),
        "real_competitor_weaknesses": {
            name: sorted({_normalize_name(w) for r in records for w in r.weaknesses})
            for name, records in records_by_competitor.items()
        },
    }


def main() -> None:
    load_env_file(ROOT / ".env.official.local")
    load_env_file(ROOT / ".env")
    youtube_key = os.environ.get("MASK_youtube_API_KEY")
    if not youtube_key:
        raise SystemExit("MASK_youtube_API_KEY is not configured.")
    gemini_keys = real_configured_gemini_keys()
    if not gemini_keys:
        raise SystemExit("No real Gemini API keys are configured.")

    results_by_naics = _load_checkpoint()
    remaining = [
        (naics, label)
        for naics, label in MARKETS
        if results_by_naics.get(str(naics), {}).get("status")
        not in ("COMPLETE", "UNKNOWN", "NOT_CALCULATED")
    ]
    print(f"M5 markets: {len(MARKETS)}. Already done: {len(MARKETS) - len(remaining)}.")
    print(f"To process this run: {len(remaining)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_store = LocalArtifactStore(OUT_DIR / "artifacts")
    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    youtube_adapter = YouTubeApiAdapter(
        profile.sources["youtube"].model_copy(update={"operational_status": "available"}),
        YouTubeApiSettings(enabled=True, policy_approved=True),
        UrllibYouTubeTransport(),
        user_agent="MASK-AI-Market-Research/0.1",
    )
    quota = YouTubeQuotaLedger(
        YouTubeQuotaLimits(max_quota_units=DAILY_QUOTA_LIMIT - QUOTA_SAFETY_MARGIN),
        units_used=QUOTA_ALREADY_USED_TODAY,
    )
    yt_ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=2_000,
            max_documents=5_000,
            max_total_bytes=200_000_000,
            max_duration_seconds=10_800,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    gemini_ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=20_000,
            max_documents=20_000,
            max_total_bytes=500_000_000,
            max_duration_seconds=21_600,
            max_paid_cost_usd=Decimal("10"),
        )
    )
    gemini_client = MultiKeyGeminiClient(gemini_keys, ArtifactAnalysisCache(artifact_store))
    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value

    for naics, label in remaining:
        required_units = len(_queries_for(label)) * 100
        if quota.units_remaining < required_units:
            print(
                f"\nSTOPPING: real quota remaining ({quota.units_remaining}) < needed "
                f"({required_units}) for {label}. Re-run on a later real day."
            )
            break
        print(f"\n=== NAICS {naics} {label} ===")
        try:
            comments, yt_notes = _collect_youtube(
                label=label,
                adapter=youtube_adapter,
                api_key=youtube_key,
                ledger=yt_ledger,
                quota=quota,
            )
            for n in yt_notes:
                print(f"  {n}")
            records_by_competitor, disposition_counts = _extract_competitors(
                naics=naics,
                label=label,
                comments=comments,
                gemini_client=gemini_client,
                ledger=gemini_ledger,
            )
            print(f"  Real distinct competitors: {sorted(records_by_competitor)}")
            market_result = _score_market(
                naics=naics,
                label=label,
                records_by_competitor=records_by_competitor,
                formulas=formulas,
            )
            market_result["disposition_counts"] = disposition_counts
            print(f"  status={market_result['status']} score={market_result.get('score')}")
        except YouTubeQuotaExceeded:
            print(f"  STOPPING mid-market: real quota exhausted for {label}.")
            _save_checkpoint(results_by_naics, quota)
            break
        except Exception as error:  # noqa: BLE001
            market_result = {"naics": naics, "label": label, "status": "ERROR", "error": str(error)}
            print(f"  MARKET FAILED (recorded, run continues): {error}")
        results_by_naics[str(naics)] = market_result
        _save_checkpoint(results_by_naics, quota)

    print(f"\n\nDone. Real YouTube quota used today: {quota.units_used} / {DAILY_QUOTA_LIMIT}")
    for r in results_by_naics.values():
        print(f"  {r['naics']} {r['label']}: {r.get('status')} {r.get('score')}")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
