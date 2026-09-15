"""Stage B, Wave B: real, multi-source evidence gathering on the top 24
non-HVAC Wave A survivors (scripts/discover_candidate_markets_wave_a.py),
scaled down ("-light") from the full HVAC deep-dive pipeline so 24 markets
are tractable within one real YouTube-quota day and reasonable Gemini
call volume -- per the owner's explicit instruction not to rely on HVAC
only, and to keep full source transparency plus an honest score/
confidence rationale in the eventual document.

For each of the 24 real candidate markets (NAICS codes ranked #2-#25 in
Wave A; #1, 238220 HVAC, is the already-scored baseline and is not
re-run here):

  m1_light   (weight 0.30) -- already computed by Wave A (Census CBP).
  m2_light   (weight 0.25) -- REAL pipeline, scaled down: 2 real YouTube
             search queries (not HVAC's 13), comments from up to
             RESULTS_PER_QUERY*2 videos, up to MAX_GEMINI_CANDIDATES
             substantive (>=100 char) comments sent to real Gemini
             COMMERCIAL_PAIN extraction (via MultiKeyGeminiClient, the
             same real multi-key rotation built for M5), the same real
             A10 grounding validation, and the same real
             PainIntelligenceService.run() used for us_hvac_10_99's own
             M2 -- this is the real M2 formula and real UNKNOWN-on-thin-
             evidence behavior, just given far less raw evidence per
             market than the HVAC deep-dive got.
  m4_light   (weight 0.20) -- the real calculate_m4() formula, fed only
             mean_m2_purchase_intent_0_4 derived from this market's own
             m2_light mentions (the exact same honest pattern used in
             scripts/run_m4_us_hvac_10_99.py -- the other three M4
             components have no real sourced evidence here either, so
             m4_light is UNKNOWN whenever no mention carried a real
             purchase_intent_0_4 value).
  m7_light   (weight 0.15) -- NOT collected in Wave B. Real per-market
             buyer-accessibility evidence (Meta Ad Library, homepage/
             About-page checks) is a manual, non-scalable process (see
             scripts/run_m7_us_hvac_10_99.py) -- doing it honestly for
             24 markets is a Phase-3, finalists-only cost, not a Wave-B
             pre-screen cost. Left None/UNKNOWN for every market here,
             on purpose, and excluded from the composite via the same
             observed-weight renormalization pattern used in Wave A and
             the regional pre-screen.
  m9_light   (weight 0.10) -- an AUTOMATED PROXY, not the real owner-
             reviewed M9: the mean of Gemini's own real
             ai_suitability_1_10 field across this market's m2_light
             mentions (a real, structured, grounded Gemini judgment already
             produced as a side effect of the COMMERCIAL_PAIN extraction,
             not a new call). Explicitly flagged in the output as a proxy
             -- any market that advances still needs the same real,
             owner-reviewed M9 pass us_hvac_10_99 got
             (scripts/run_m9_us_hvac_10_99.py), using the same owner-
             supplied MASK AI Capability Registry.

Composite score = weighted average over OBSERVED components only,
renormalized by observed weight (identical pattern to Wave A's
`_normalize`/M1-light renormalization) -- never a forced/padded score.
`observed_weight` is reported per market as an explicit confidence/
coverage figure, satisfying the owner's requirement that the eventual
document explain why a score's confidence was low or high.

Real per-market failures (YouTube transport errors, zero videos, zero
qualifying comments, Gemini errors, thin M2 evidence) do not crash the
run: each market is wrapped independently, logged, and the run continues
-- mirroring the real OfficialDataError-crash lesson from Wave A. Partial
results are checkpointed to disk after every market.

Usage:
    uv run python scripts/discover_wave_b_top24.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, date, datetime
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
from mask_api.modules.youtube_data.quota import YouTubeQuotaLedger, YouTubeQuotaLimits  # noqa: E402
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

RESULTS_PER_QUERY = 6
MAX_COMMENTS_PER_VIDEO = 20
MIN_COMMENT_LENGTH = 100
MAX_GEMINI_CANDIDATES_PER_MARKET = 15
MODEL_REFERENCE = "gemini-flash-lite-latest"
SLEEP_BETWEEN_GEMINI_CALLS_SECONDS = 1.2

WEIGHTS = {
    "m1_light": Decimal("0.30"),
    "m2_light": Decimal("0.25"),
    "m4_light": Decimal("0.20"),
    "m7_light": Decimal("0.15"),
    "m9_light": Decimal("0.10"),
}

_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_ID = f"discover_wave_b_top24_{_RUN_TIMESTAMP}"
OUT_DIR = ROOT / "outputs" / "runs" / RUN_ID


def _slugify(label: str) -> str:
    label = re.sub(r"\([^)]*\)", "", label)
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:60].strip("_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _load_candidates() -> list[dict[str, object]]:
    data = json.loads((WAVE_A_RUN_DIR / "wave_a_prescreen.json").read_text(encoding="utf-8"))
    ranked = data["qualifying_candidates_ranked"]
    top = [r for r in ranked[:TOP_N_INCLUDING_HVAC] if int(r["naics"]) != HVAC_NAICS]
    return top


def _collect_youtube(
    *,
    naics: int,
    label: str,
    market_slug: str,
    adapter: YouTubeApiAdapter,
    api_key: str,
    ledger: BudgetLedger,
    quota: YouTubeQuotaLedger,
) -> tuple[list[dict[str, object]], list[str]]:
    clean_label = re.sub(r"\([^)]*\)", "", label).strip()
    queries = [
        f"{clean_label} business scheduling software problems",
        f"{clean_label} business customer complaints reviews",
    ]
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
        except YouTubeTransportError as error:
            notes.append(f"COMMENTS video={video_id}: SKIPPED {error.code}")
    notes.append(f"videos={len(videos)} comments={len(all_comments)} market_slug={market_slug}")
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
    for comment in candidates:
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
            result = gemini_client.analyze(request, ledger)
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
            "evidence_reference": (
                "Census CBP 2022, NAICS candidate pre-screen "
                "(scripts/discover_candidate_markets_wave_a.py)"
            ),
        }
    }

    m2_status = "UNKNOWN"
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
            m2_status = m2_result.status.value
            if m2_result.status.value == "COMPLETE":
                m2_score = m2_result.score
            detail["m2_light"] = {
                "status": m2_status,
                "score": str(m2_score) if m2_score is not None else None,
                "unknown_reasons": list(m2_result.unknown_reasons),
                "real_pain_mentions": len(mentions),
                "candidate_documents_assessed": all_relevant_unique_documents,
                "evidence_reference": (
                    "Real YouTube comments, Gemini COMMERCIAL_PAIN extraction, A10 grounding, "
                    "real PainIntelligenceService.run() -- scaled-down (Wave B-light) evidence "
                    "volume vs. the HVAC deep-dive."
                ),
            }
        except Exception as error:  # noqa: BLE001 -- report, never silently drop
            detail["m2_light"] = {"status": "ERROR", "error": f"{type(error).__name__}: {error}"}
    else:
        detail["m2_light"] = {
            "status": "UNKNOWN",
            "unknown_reasons": ["no_real_pain_mentions_extracted"],
            "evidence_reference": "No real YouTube comments qualified for extraction.",
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
                    f"from this market's real m2_light pain mentions. THIN SAMPLE "
                    f"({len(values)} of {len(mentions)} real mentions) -- Wave B-light, not a "
                    "robust estimate."
                ),
                observation_state=ObservationState.OBSERVED,
                geography="US",
                population=f"Anonymous YouTube commenters on {candidate['label']} videos",
                period=RUN_ID,
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
        "unknown_reasons": ["not_collected_in_wave_b_deferred_to_phase_3_finalists"],
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
                "AUTOMATED PROXY ONLY -- mean of Gemini's real ai_suitability_1_10 field "
                "across this market's real m2_light mentions. NOT the real, owner-reviewed M9 "
                "(capability-registry mapping); that pass is still required for any market "
                "that advances, exactly as done for us_hvac_10_99."
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
        "composite_score_0_10": str(composite) if composite is not None else None,
        "observed_weight_0_1": str(observed_weight),
        "confidence_note": (
            f"{observed_weight * 100}% of the full DiscoveryPreScreenScore weight was "
            "real, observed evidence for this market; the rest is UNKNOWN (see component "
            "detail) and was excluded from the composite, not padded or estimated."
        ),
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

    candidates = _load_candidates()
    if len(sys.argv) >= 2:
        max_markets = int(sys.argv[1])
        candidates = candidates[:max_markets]
        print(f"Smoke-test cap applied: processing only {len(candidates)} market(s)")
    print(f"Wave B candidates (top {TOP_N_INCLUDING_HVAC} minus HVAC baseline): {len(candidates)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_store = LocalArtifactStore(OUT_DIR / "artifacts")
    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    youtube_adapter = YouTubeApiAdapter(
        profile.sources["youtube"].model_copy(update={"operational_status": "available"}),
        YouTubeApiSettings(enabled=True, policy_approved=True),
        UrllibYouTubeTransport(),
        user_agent="MASK-AI-Market-Research/0.1",
    )
    quota = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=9_000))
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
            max_requests=len(candidates) * MAX_GEMINI_CANDIDATES_PER_MARKET + 50,
            max_documents=len(candidates) * MAX_GEMINI_CANDIDATES_PER_MARKET + 50,
            max_total_bytes=200_000_000,
            max_duration_seconds=10_800,
            max_paid_cost_usd=Decimal("5"),
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

    results: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates):
        naics = int(str(candidate["naics"]))
        label = str(candidate["label"])
        market_slug = _slugify(label)
        market_id = f"us_{market_slug}_10_99_wb"
        print(f"\n[{index + 1}/{len(candidates)}] NAICS {naics} {label} (market_id={market_id})")
        try:
            comments, yt_notes = _collect_youtube(
                naics=naics,
                label=label,
                market_slug=market_slug,
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
            market_result["extraction_log"] = extraction_log
            print(
                f"  composite_score_0_10={market_result['composite_score_0_10']} "
                f"observed_weight={market_result['observed_weight_0_1']}"
            )
        except Exception as error:  # noqa: BLE001 -- one market's failure must not crash the run
            market_result = {
                "naics": naics,
                "label": label,
                "market_id": market_id,
                "composite_score_0_10": None,
                "status": "ERROR",
                "error": f"{type(error).__name__}: {error}",
            }
            print(f"  MARKET FAILED (recorded, run continues): {market_result['error']}")
        results.append(market_result)
        (OUT_DIR / "wave_b_results.json").write_text(
            json.dumps(
                {
                    "run_id": RUN_ID,
                    "candidates_total": len(candidates),
                    "candidates_processed": len(results),
                    "youtube_quota_units_used": quota.units_used,
                    "gemini_key_switch_count": gemini_client.key_switch_count,
                    "gemini_exhausted_key_count": gemini_client.exhausted_key_count,
                    "results": results,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    ranked = sorted(
        (r for r in results if r.get("composite_score_0_10") is not None),
        key=lambda r: Decimal(str(r["composite_score_0_10"])),
        reverse=True,
    )
    unranked = [r for r in results if r.get("composite_score_0_10") is None]
    print(f"\n\nDone. {len(ranked)} markets scored, {len(unranked)} could not be scored.")
    print(f"YouTube quota used: {quota.units_used} / 9000")
    print(f"Gemini key switches: {gemini_client.key_switch_count}")
    for r in ranked:
        print(
            f"  NAICS {r['naics']:>6} {str(r['label'])[:55]:<55} "
            f"score={r['composite_score_0_10']:>5} coverage={r['observed_weight_0_1']}"
        )
    for r in unranked:
        print(f"  NAICS {r['naics']:>6} {str(r['label'])[:55]:<55} UNSCORED: {r.get('error')}")
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
