"""Real M5 competitor evidence collection for us_hvac_10_99 from YouTube.

Directive-required pipeline, phase 1 of 2 (discovery -> retrieval -> raw
evidence retention), mirroring collect_youtube_pain_evidence_us_hvac_10_99
.py exactly -- same adapters, same real per-comment document granularity
-- but with queries deliberately aimed at real competitor/pricing/review
discussion rather than general operational pain, since M5 needs
competitor/pricing/feature/complaint evidence M2's pain-focused queries
were not designed to surface.

Usage:
    uv run python scripts/collect_youtube_competitor_evidence_us_hvac_10_99.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

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
from mask_api.research_runner.configuration import load_source_profile  # noqa: E402
from pydantic import SecretStr  # noqa: E402

SEARCH_QUERIES = [
    "Jobber HVAC review pricing",
    "Housecall Pro review complaints",
    "ServiceTitan vs Jobber HVAC",
    "FieldEdge HVAC software review",
    "best HVAC field service software comparison 2026",
    "HVAC dispatch software pricing comparison",
    "Jobber vs Housecall Pro HVAC",
    "HVAC CRM software honest review",
]
RESULTS_PER_QUERY = 10
MAX_COMMENTS_PER_VIDEO = 50
RUN_ID = f"youtube_competitor_evidence_us_hvac_10_99_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
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


def main() -> None:
    _load_env_file(ROOT / ".env.official.local")
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("MASK_youtube_API_KEY")
    if not api_key:
        raise SystemExit("MASK_youtube_API_KEY is not configured; cannot collect real evidence.")

    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value
    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=200,
            max_documents=1000,
            max_total_bytes=50_000_000,
            max_duration_seconds=1800,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    quota = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=9_000))
    adapter = YouTubeApiAdapter(
        profile.sources["youtube"].model_copy(update={"operational_status": "available"}),
        YouTubeApiSettings(enabled=True, policy_approved=True),
        UrllibYouTubeTransport(),
        user_agent="MASK-AI-Market-Research/0.1",
    )

    videos: dict[str, dict[str, object]] = {}
    for query in SEARCH_QUERIES:
        try:
            request = youtube_search_request(
                query=query, api_key=SecretStr(api_key), max_results=RESULTS_PER_QUERY
            )
            result = adapter.fetch(request, ledger, quota)
            found = len(result.batch.videos)
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
            print(f"SEARCH '{query}': {found} results, {new} new unique videos")
        except YouTubeTransportError as error:
            print(f"SEARCH '{query}': FAILED {error.code}")

    print(f"\nTotal unique videos discovered: {len(videos)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "videos.json").write_text(
        json.dumps(list(videos.values()), indent=2, default=str), encoding="utf-8"
    )

    all_comments: list[dict[str, object]] = []
    comment_failures: list[dict[str, str]] = []
    for video_id, video_record in videos.items():
        try:
            request = youtube_comment_threads_request(
                video_id=video_id, api_key=SecretStr(api_key), max_results=MAX_COMMENTS_PER_VIDEO
            )
            result = adapter.fetch(request, ledger, quota)
            for comment in result.batch.comments:
                all_comments.append(
                    {
                        "comment_id": comment.comment_id,
                        "video_id": comment.video_id,
                        "video_title": video_record["title"],
                        "text": comment.text,
                        "author_display_name": comment.author_display_name,
                        "published_at": comment.published_at,
                        "like_count": comment.like_count,
                        "reply_count": comment.reply_count,
                    }
                )
            print(f"COMMENTS video={video_id}: {len(result.batch.comments)} real comments")
        except YouTubeTransportError as error:
            comment_failures.append({"video_id": video_id, "code": error.code})
            print(f"COMMENTS video={video_id}: SKIPPED {error.code}")

    (OUT_DIR / "comments.json").write_text(
        json.dumps(all_comments, indent=2, default=str), encoding="utf-8"
    )
    (OUT_DIR / "comment_failures.json").write_text(
        json.dumps(comment_failures, indent=2), encoding="utf-8"
    )
    summary = {
        "market_id": "us_hvac_10_99",
        "search_queries": SEARCH_QUERIES,
        "unique_videos_discovered": len(videos),
        "videos_with_comment_failures": len(comment_failures),
        "total_real_comments_collected": len(all_comments),
        "quota_units_used": quota.units_used,
        "budget_requests_used": ledger.usage.requests,
        "budget_bytes_used": ledger.usage.total_bytes,
    }
    (OUT_DIR / "collection_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nTotal real comments collected: {len(all_comments)}")
    print(f"YouTube quota used: {quota.units_used} / {quota.limits.max_quota_units}")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
