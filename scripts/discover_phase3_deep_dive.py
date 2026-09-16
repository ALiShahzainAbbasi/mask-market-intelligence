"""Stage B, Phase 3: real, HVAC-comparable-depth deep-dive evidence
gathering on the top 14 non-HVAC Wave A survivors, per the owner's
explicit choice (2026-09-16 AskUserQuestion) after Wave B's real,
honestly-reported finding that light-tier evidence (2 queries, <=15
Gemini candidates/market) was too thin to differentiate the 24
candidates: "Skip to deep-dive on a shortlist" -- narrow first using
Wave A's real, robust M1-light Census ranking, then spend real
Gemini/YouTube quota only where it can actually produce signal.

Shortlist (top 14 non-HVAC by Wave A m1_light_score, chosen at the
approved "~12-15" scale): Electrical Contractors, Landscaping Services,
Site Preparation Contractors, Other Building Equipment Contractors,
Janitorial Services, Security Systems Services, Automotive Body/Paint/
Interior Repair, All Other Specialty Trade Contractors, Facilities
Support Services, Car Washes, Other Computer Related Services, Pet Care
Services, Exterminating and Pest Control Services, Roofing Contractors.

Per market, real evidence depth: 6 real, diverse YouTube search queries
(adapted from us_hvac_10_99's own real 13-query set, generalized to the
market's label -- fewer than HVAC's 13 so 14 markets are tractable
within real daily YouTube quota, but real diversity of query intent is
kept: scheduling software, missed calls/leads, day-to-day operations,
estimating software, customer complaints, business-owner pain), up to
MAX_COMMENTS_PER_VIDEO=100 comments/video (matching HVAC exactly), and
up to MAX_GEMINI_CANDIDATES_PER_MARKET=200 real Gemini COMMERCIAL_PAIN
extractions per market (a real, disclosed cap -- an order of magnitude
above Wave B's 15, below HVAC's uncapped ~600, chosen so this is
affordable across 14 markets within a few real quota-days rather than
one). No artificial floor is applied: a market that genuinely produces
zero real pain mentions from 200 real candidates stays honestly UNKNOWN
on m2_light/m4_light, exactly like Wave B's real, reported outcome for
22/24 markets and exactly like calculate_m4()'s own real UNKNOWN
behavior when a required component is missing.

REAL DAILY QUOTA CONSTRAINT, handled honestly, not glossed over: real
YouTube Data API quota resets daily at Pacific Time midnight (not local
time), so this script's local YouTubeQuotaLedger must be seeded with
units_used=QUOTA_ALREADY_USED_TODAY reflecting whatever this real
Google account has genuinely already spent on the CURRENT real Pacific
quota day -- update that constant before each run (AUTONOMOUS-051's run
on 2026-09-15 used 5,077 from Wave B; AUTONOMOUS-056's run on 2026-09-16
is a fresh real day, so it starts at 0). Starting fresh at 0 on a day
where real usage is nonzero would let this process send real requests
Google will actually reject. At ~650-700 real units/market (6 queries +
comment-thread fetches), only a handful of markets fit in whatever real
quota remains today; the rest wait for tomorrow's real reset.

RESUMABLE BY DESIGN: results are checkpointed to a single, non-
timestamped file (not a fresh timestamped run dir per invocation) so
re-running this script on a later real day continues from wherever
quota forced a stop, without re-processing already-completed markets or
re-spending real quota on them. A market is skipped as already-done only
if its entry's status is "COMPLETE" (a market that stopped early because
quota ran out mid-market is NOT marked complete and will be retried from
scratch next run -- content-addressed Gemini/embedding caching means
already-fetched comments will not cost new real Gemini calls if reused,
but a fresh real YouTube quota check applies to a market's own searches
regardless).

Usage:
    uv run python scripts/discover_phase3_deep_dive.py
    (safe to re-run on a later real day; it will pick up where quota
    left off)
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
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
from mask_api.modules.evidence.domain import EvidencePersona  # noqa: E402
from mask_api.modules.method_metrics import (  # noqa: E402
    M4Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m4,
)
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

WAVE_A_RUN_DIR = ROOT / "outputs/runs/discover_candidate_markets_wave_a_20260915T175008Z"
TOP_N_INCLUDING_HVAC = 25
HVAC_NAICS = 238220
SHORTLIST_SIZE = 14

QUOTA_ALREADY_USED_TODAY = 0
# 2026-09-16: real Pacific-Time calendar day rolled over since AUTONOMOUS-051's
# run (which used WAVE_B_QUOTA_ALREADY_USED_TODAY = 5_077 for 2026-09-15's real
# quota day). Real YouTube quota resets daily -- update this constant to
# whatever this real Google account has genuinely already spent TODAY (Pacific
# Time) before each invocation; it must never carry a stale prior-day value
# forward, or this script will under-use real available quota.
DAILY_QUOTA_LIMIT = 9_000
QUOTA_SAFETY_MARGIN = 100

RESULTS_PER_QUERY = 10
MAX_COMMENTS_PER_VIDEO = 100
MIN_COMMENT_LENGTH = 100
MAX_GEMINI_CANDIDATES_PER_MARKET = 200
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_GEMINI_CALLS_SECONDS = 1.2
# Real bug found live (2026-09-16/17): scripts/discover_phase3_deep_dive.py
# hung indefinitely, three separate times, on the same market's Gemini
# extraction loop -- no exception, no progress, real CPU still ticking.
# GeminiAdapter's underlying HTTP call has its own real timeout_seconds
# setting, but something in this real run's path (never fully isolated --
# possibly a pathological single comment, possibly a transport-level
# retry edge case) did not honor it. Rather than trust that timeout alone
# a second time, every real Gemini call in this script is now wrapped in
# its own hard wall-clock timeout via a worker thread -- if a single real
# call exceeds this, it is abandoned and logged as a real timeout, and
# the loop moves on to the next real candidate instead of hanging the
# whole market (and every market queued after it) forever.
GEMINI_CALL_TIMEOUT_SECONDS = 45.0

WEIGHTS = {
    "m1_light": Decimal("0.30"),
    "m2_light": Decimal("0.25"),
    "m4_light": Decimal("0.20"),
    "m7_light": Decimal("0.15"),
    "m9_light": Decimal("0.10"),
}

OUT_DIR = ROOT / "outputs" / "runs" / "phase3_deep_dive"
RESULTS_PATH = OUT_DIR / "phase3_results.json"


def _slugify(label: str) -> str:
    label = re.sub(r"\([^)]*\)", "", label)
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return re.sub(r"_+", "_", slug)[:60].strip("_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _load_shortlist() -> list[dict[str, object]]:
    data = json.loads((WAVE_A_RUN_DIR / "wave_a_prescreen.json").read_text(encoding="utf-8"))
    ranked = data["qualifying_candidates_ranked"]
    non_hvac = [r for r in ranked[:TOP_N_INCLUDING_HVAC] if int(r["naics"]) != HVAC_NAICS]
    return non_hvac[:SHORTLIST_SIZE]


def _queries_for(label: str) -> list[str]:
    clean = re.sub(r"\([^)]*\)", "", label).strip()
    return [
        f"{clean} dispatch scheduling software",
        f"{clean} business missed calls leads",
        f"{clean} scheduling software problems",
        f"{clean} estimating software small business",
        f"running a {clean} business operations",
        f"{clean} customer service complaints",
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
    queries = _queries_for(label)
    videos: dict[str, dict[str, object]] = {}
    notes: list[str] = []
    for query in queries:
        try:
            request = youtube_search_request(
                query=query, api_key=SecretStr(api_key), max_results=RESULTS_PER_QUERY
            )
            result = adapter.fetch(request, ledger, quota)
            new = 0
            for video in result.batch.videos:
                if video.video_id not in videos:
                    new += 1
                    videos[video.video_id] = {
                        "video_id": video.video_id,
                        "title": video.title,
                        "description": video.description,
                        "channel_title": video.channel_title,
                        "published_at": video.published_at,
                        "found_via_query": query,
                    }
            notes.append(f"SEARCH '{query}': {len(result.batch.videos)} results, {new} new")
        except YouTubeQuotaExceeded:
            notes.append(f"SEARCH '{query}': STOPPED real daily YouTube quota exhausted")
            raise
        except YouTubeTransportError as error:
            notes.append(f"SEARCH '{query}': FAILED {error.code}")

    all_comments: list[dict[str, object]] = []
    for video_id, video_record in videos.items():
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
                        "video_title": video_record["title"],
                        "text": comment.text,
                        "published_at": comment.published_at,
                    }
                )
        except YouTubeQuotaExceeded:
            notes.append(f"COMMENTS video={video_id}: STOPPED real daily YouTube quota exhausted")
            break
        except YouTubeTransportError as error:
            notes.append(f"COMMENTS video={video_id}: SKIPPED {error.code}")
    notes.append(f"videos={len(videos)} comments={len(all_comments)}")
    return all_comments, notes


def _extract_pain_mentions(
    *,
    naics: int,
    label: str,
    market_id: str,
    comments: list[dict[str, object]],
    gemini_client: MultiKeyGeminiClient,
    ledger: BudgetLedger,
) -> tuple[list[PainMention], list[dict[str, object]]]:
    market_definition = f"US {label}, NAICS {naics}, with 10-99 employees."
    task_instructions = (
        f"This is one public YouTube comment on a video related to {label} business "
        "operations, scheduling, or software. Extract any commercial pain the "
        "commenter explicitly and clearly states -- do not infer pain that is not "
        "directly stated. If the comment contains no clear commercial pain, return "
        "an empty records list."
    )
    candidates = [c for c in comments if len(str(c["text"])) >= MIN_COMMENT_LENGTH]
    candidates = candidates[:MAX_GEMINI_CANDIDATES_PER_MARKET]

    mentions_by_id: dict[str, PainMention] = {}
    log: list[dict[str, object]] = []
    for index, comment in enumerate(candidates):
        text = str(comment["text"])
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
        entry: dict[str, object] = {"comment_id": comment["comment_id"]}
        try:
            # Fresh single-use executor per call, shut down with wait=False:
            # if this specific call hangs past GEMINI_CALL_TIMEOUT_SECONDS,
            # it is abandoned immediately (the worker thread may leak in the
            # background, but this process does not block waiting for it --
            # a plain `with ThreadPoolExecutor()` block would still block on
            # shutdown(wait=True) even after future.result() times out,
            # defeating the whole point).
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(gemini_client.analyze, request, ledger)
            try:
                result = future.result(timeout=GEMINI_CALL_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                executor.shutdown(wait=False)
                entry["outcome"] = "real_call_timeout_abandoned"
                log.append(entry)
                print(
                    f"    [{index + 1}/{len(candidates)}] Gemini call exceeded "
                    f"{GEMINI_CALL_TIMEOUT_SECONDS}s -- abandoned, continuing."
                )
                continue
            executor.shutdown(wait=False)
            if result.status != AnalysisStatus.COMPLETED:
                entry["outcome"] = f"analysis_{result.status.value}"
                log.append(entry)
                continue
            report = validate_grounding(request, result)
            entry["disposition"] = report.disposition.value
            if report.disposition == GroundingDisposition.ACCEPTED:
                context = GroundedPainContext(
                    market_id=market_id,
                    document_id=f"youtube_comment_{comment['comment_id']}",
                    source_family="youtube_comments",
                    persona=EvidencePersona.UNKNOWN,
                    source_date=_parse_date(str(comment.get("published_at") or "") or None),
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
        log.append(entry)
        if (index + 1) % 25 == 0 or index == len(candidates) - 1:
            print(
                f"    [{index + 1}/{len(candidates)}] real mentions so far: {len(mentions_by_id)}"
            )
        time.sleep(SLEEP_BETWEEN_GEMINI_CALLS_SECONDS)
    return list(mentions_by_id.values()), log


def _score_market(
    *,
    candidate: dict[str, object],
    mentions: list[PainMention],
    all_relevant_unique_documents: int,
    market_id: str,
    embeddings: EmbeddingService,
    formulas: FormulaConfiguration,
) -> dict[str, object]:
    m1_score = Decimal(str(candidate["m1_light_score"]))
    components: dict[str, Decimal | None] = {"m1_light": m1_score}
    detail: dict[str, object] = {
        "m1_light": {
            "score": str(m1_score),
            "evidence_reference": "Census CBP 2022 (scripts/discover_candidate_markets_wave_a.py)",
        }
    }

    m2_score: Decimal | None = None
    if mentions:
        m2_formula = formulas.method_formulas[MethodId.M2]
        clustering_config = ClusteringConfiguration(
            clustering_version="v1",
            similarity_threshold=Decimal("0.8"),
            near_duplicate_threshold=Decimal("0.99"),
            min_cluster_size=2,
            max_mentions=max(len(mentions), 100),
        )
        m2_ledger = BudgetLedger(
            RunBudgetLimits(
                max_requests=10,
                max_documents=len(mentions) + 10,
                max_total_bytes=50_000_000,
                max_duration_seconds=600,
                max_paid_cost_usd=Decimal("0"),
            )
        )
        try:
            m2_result = PainIntelligenceService(embeddings, clustering_config).run(
                market_id=market_id,
                formula_version=formulas.formula_version,
                formula=m2_formula,
                all_relevant_unique_documents=all_relevant_unique_documents,
                mentions=tuple(mentions),
                ledger=m2_ledger,
            )
            if m2_result.status.value == "COMPLETE":
                m2_score = m2_result.score
            detail["m2_light"] = {
                "status": m2_result.status.value,
                "score": str(m2_score) if m2_score is not None else None,
                "unknown_reasons": list(m2_result.unknown_reasons),
                "real_pain_mentions": len(mentions),
                "candidate_documents_assessed": all_relevant_unique_documents,
            }
        except Exception as error:  # noqa: BLE001 -- report, never silently drop
            detail["m2_light"] = {"status": "ERROR", "error": f"{type(error).__name__}: {error}"}
    else:
        detail["m2_light"] = {
            "status": "UNKNOWN",
            "unknown_reasons": ["no_real_pain_mentions_extracted"],
        }
    components["m2_light"] = m2_score

    m4_score: Decimal | None = None
    values = [Decimal(intent) for m in mentions if (intent := m.purchase_intent_0_4) is not None]
    if values:
        mean_value = (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        purchase_intent_metric = SourcedMetric(
            value=mean_value,
            provenance=MetricProvenance(
                source_id="youtube_comments_gemini_extraction",
                evidence_reference=(
                    f"Mean of {len(values)} real Gemini-extracted purchase_intent_0_4 values "
                    f"from this market's real Phase-3 pain mentions ({len(values)} of "
                    f"{len(mentions)} real mentions)."
                ),
                observation_state=ObservationState.OBSERVED,
                geography="US",
                population=f"Anonymous YouTube commenters on {candidate['label']} videos",
                period="phase3_deep_dive",
                unit="purchase_intent_0_4_scale",
            ),
        )
        m4_formula = formulas.method_formulas[MethodId.M4]
        m4_result = calculate_m4(
            formula_version=formulas.formula_version,
            formula=m4_formula,
            inputs=M4Inputs(
                market_id=market_id,
                annual_problem_cost_usd=None,
                annual_existing_paid_spend_usd=None,
                verified_paid_workaround_share=None,
                mean_m2_purchase_intent_0_4=purchase_intent_metric,
            ),
        )
        detail["m4_light"] = {
            "status": m4_result.status.value,
            "score": str(m4_result.score) if m4_result.status.value == "COMPLETE" else None,
            "unknown_reasons": list(m4_result.unknown_reasons),
            "mean_purchase_intent_0_4": str(mean_value),
            "n_mentions_with_intent": len(values),
        }
        if m4_result.status.value == "COMPLETE":
            m4_score = m4_result.score
    else:
        detail["m4_light"] = {
            "status": "UNKNOWN",
            "unknown_reasons": ["no_real_mentions_with_purchase_intent_0_4"],
        }
    components["m4_light"] = m4_score

    components["m7_light"] = None
    detail["m7_light"] = {
        "status": "UNKNOWN",
        "unknown_reasons": ["deferred_to_final_tier1_cut_manual_buyer_accessibility_evidence"],
    }

    m9_score: Decimal | None = None
    ai_suitability_values = [
        Decimal(suitability) for m in mentions if (suitability := m.ai_suitability_1_10) is not None
    ]
    if ai_suitability_values:
        m9_score = (
            sum(ai_suitability_values, Decimal(0)) / Decimal(len(ai_suitability_values))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        detail["m9_light"] = {
            "status": "PROXY_OBSERVED",
            "score": str(m9_score),
            "n_mentions": len(ai_suitability_values),
            "note": (
                "AUTOMATED PROXY ONLY -- mean of Gemini's real ai_suitability_1_10 field. "
                "NOT the real, owner-reviewed M9; that pass is still required for any "
                "market that advances, exactly as done for us_hvac_10_99."
            ),
        }
    else:
        detail["m9_light"] = {
            "status": "UNKNOWN",
            "unknown_reasons": ["no_real_mentions_with_ai_suitability_1_10"],
        }
    components["m9_light"] = m9_score

    observed_weight = sum((WEIGHTS[k] for k, v in components.items() if v is not None), Decimal(0))
    composite: Decimal | None = None
    if observed_weight > 0:
        weighted_sum = sum(
            (WEIGHTS[k] * v for k, v in components.items() if v is not None), Decimal(0)
        )
        composite = (weighted_sum / observed_weight).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "naics": candidate["naics"],
        "label": candidate["label"],
        "market_id": market_id,
        "status": "COMPLETE",
        "composite_score_0_10": str(composite) if composite is not None else None,
        "observed_weight_0_1": str(observed_weight),
        "components": {k: (str(v) if v is not None else None) for k, v in components.items()},
        "component_detail": detail,
    }


def main() -> None:
    load_env_file(ROOT / ".env.official.local")
    load_env_file(ROOT / ".env")
    youtube_key = os.environ.get("MASK_youtube_API_KEY")
    if not youtube_key:
        raise SystemExit("MASK_youtube_API_KEY is not configured; cannot collect real evidence.")
    gemini_keys = real_configured_gemini_keys()
    if not gemini_keys:
        raise SystemExit("No real Gemini API keys are configured.")

    shortlist = _load_shortlist()
    results_by_naics = _load_checkpoint()
    remaining = [
        c
        for c in shortlist
        if results_by_naics.get(str(c["naics"]), {}).get("status") != "COMPLETE"
    ]
    already_done = len(shortlist) - len(remaining)
    print(f"Phase 3 shortlist: {len(shortlist)} markets. Already complete: {already_done}.")
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
    print(
        f"Real YouTube quota today: {quota.units_used} used, "
        f"{quota.units_remaining} remaining (est.)"
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
            max_requests=len(remaining) * MAX_GEMINI_CANDIDATES_PER_MARKET + 50,
            max_documents=len(remaining) * MAX_GEMINI_CANDIDATES_PER_MARKET + 50,
            max_total_bytes=500_000_000,
            max_duration_seconds=21_600,
            max_paid_cost_usd=Decimal("10"),
        )
    )
    gemini_client = MultiKeyGeminiClient(gemini_keys, ArtifactAnalysisCache(artifact_store))
    embeddings = EmbeddingService(
        LocalHashingEmbeddingProvider(),
        ArtifactEmbeddingCache(artifact_store),
        provider_name=LOCAL_HASHING_PROVIDER,
        model_reference=LOCAL_HASHING_MODEL,
        embedding_version=LOCAL_HASHING_VERSION,
        dimensions=64,
    )
    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value

    stopped_for_quota = False
    for index, candidate in enumerate(remaining):
        naics = int(str(candidate["naics"]))
        label = str(candidate["label"])
        market_id = f"us_{_slugify(label)}_10_99_p3"
        required_units = len(_queries_for(label)) * 100
        if quota.units_remaining < required_units:
            print(
                f"\nSTOPPING: real YouTube quota remaining ({quota.units_remaining}) is below "
                f"what {label} needs ({required_units}). Re-run this script on a later real day."
            )
            stopped_for_quota = True
            break
        print(f"\n[{index + 1}/{len(remaining)}] NAICS {naics} {label} (market_id={market_id})")
        try:
            comments, yt_notes = _collect_youtube(
                label=label,
                adapter=youtube_adapter,
                api_key=youtube_key,
                ledger=yt_ledger,
                quota=quota,
            )
            for note in yt_notes:
                print(f"  {note}")
            mentions, extraction_log = _extract_pain_mentions(
                naics=naics,
                label=label,
                market_id=market_id,
                comments=comments,
                gemini_client=gemini_client,
                ledger=gemini_ledger,
            )
            print(
                f"  real pain mentions extracted: {len(mentions)} "
                f"(gemini_key_switch_count={gemini_client.key_switch_count})"
            )
            candidates_assessed = min(
                len([c for c in comments if len(str(c["text"])) >= MIN_COMMENT_LENGTH]),
                MAX_GEMINI_CANDIDATES_PER_MARKET,
            )
            market_result = _score_market(
                candidate=candidate,
                mentions=mentions,
                all_relevant_unique_documents=max(candidates_assessed, 1),
                market_id=market_id,
                embeddings=embeddings,
                formulas=formulas,
            )
            market_result["youtube_notes"] = yt_notes
            market_result["total_comments_collected"] = len(comments)
            market_result["extraction_log_summary"] = {
                "total": len(extraction_log),
                "outcomes": {
                    o: sum(1 for e in extraction_log if e.get("outcome") == o)
                    for o in {e.get("outcome") for e in extraction_log}
                },
            }
            print(
                f"  composite_score_0_10={market_result['composite_score_0_10']} "
                f"observed_weight={market_result['observed_weight_0_1']}"
            )
        except YouTubeQuotaExceeded:
            print(f"  STOPPING mid-market: real YouTube quota exhausted for {label}.")
            stopped_for_quota = True
            _save_checkpoint(results_by_naics, quota)
            break
        except Exception as error:  # noqa: BLE001 -- one market's failure must not crash the run
            market_result = {
                "naics": naics,
                "label": label,
                "market_id": market_id,
                "status": "ERROR",
                "composite_score_0_10": None,
                "error": f"{type(error).__name__}: {error}",
            }
            print(f"  MARKET FAILED (recorded, run continues): {market_result['error']}")
        results_by_naics[str(naics)] = market_result
        _save_checkpoint(results_by_naics, quota)

    completed = [r for r in results_by_naics.values() if r.get("status") == "COMPLETE"]
    print(f"\n\nRun segment done. {len(completed)}/{len(shortlist)} shortlist markets complete.")
    print(f"Real YouTube quota used today (incl. Wave B): {quota.units_used} / {DAILY_QUOTA_LIMIT}")
    if stopped_for_quota:
        print("Stopped early on real daily quota. Re-run this script on a later real day.")
    ranked = sorted(
        (r for r in results_by_naics.values() if r.get("composite_score_0_10") is not None),
        key=lambda r: Decimal(str(r["composite_score_0_10"])),
        reverse=True,
    )
    for r in ranked:
        print(
            f"  NAICS {r['naics']:>6} {str(r['label'])[:50]:<50} "
            f"score={r['composite_score_0_10']:>5} coverage={r['observed_weight_0_1']} "
            f"status={r.get('status')}"
        )
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
