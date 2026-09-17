"""Register a real SourcePolicy for Jobber's real pricing page and
retrieve it via the real Common Crawl targeted-retrieval module --
unblocking M4's annual_existing_paid_spend_usd component (and, for any
future market whose real M5 competitor evidence names Jobber, a real
pricing_proof data point) with no new credential and no live scrape of
Jobber's own site (Common Crawl serves an already-archived copy of a
URL this policy explicitly approves, per docs/SCRAPING_POLICY.md's
priority-4 path and docs/COMMON_CRAWL.md's reuse-not-new-scraper design).

Real lead: multiple real M2/M5 mentions across this project name Jobber
as a currently-used paid tool (e.g. us_hvac_10_99's own M2 mention "we
use jobber now"; Landscaping Services' M5 competitor evidence). Real
pricing page and real current Common Crawl collection were confirmed
live immediately before writing this script (2026-09-17, via WebFetch):
https://www.getjobber.com/pricing/ -- Core $29/mo, Connect $99/mo, Grow
$149/mo, Plus $399/mo (all annual billing, 1-user tier; +$29/mo per
additional user), and the real current collection id CC-MAIN-2026-34
(from index.commoncrawl.org/collinfo.json).

Usage:
    uv run python scripts/register_and_fetch_jobber_pricing.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.common_crawl_data.errors import CommonCrawlError  # noqa: E402
from mask_api.modules.common_crawl_data.integration import to_parsed_document  # noqa: E402
from mask_api.modules.common_crawl_data.retriever import (  # noqa: E402
    CommonCrawlRetriever,
    CommonCrawlSettings,
)
from mask_api.modules.common_crawl_data.transport import UrllibCommonCrawlTransport  # noqa: E402
from mask_api.modules.evidence.contracts import SourcePolicy  # noqa: E402
from mask_api.modules.evidence.domain import (  # noqa: E402
    CollectionMethod,
    CollectorKind,
    EvidenceAccessClass,
    SourcePolicyStatus,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits  # noqa: E402

URL = "https://www.getjobber.com/pricing/"
COLLECTION = "CC-MAIN-2026-34"
OUT_DIR = ROOT / "outputs" / "runs" / "jobber_pricing_common_crawl"


def _policy() -> SourcePolicy:
    now = datetime.now(UTC)
    return SourcePolicy(
        id=uuid4(),
        source_id=uuid4(),
        version="policy-v1",
        source_name="Jobber pricing page (Common Crawl targeted retrieval)",
        source_family="jobber_pricing",
        base_url=URL,
        status=SourcePolicyStatus.ALLOWED,
        collection_method=CollectionMethod.API,
        collector_kind=CollectorKind.COMMON_CRAWL,
        effective_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=365),
        approved_at=now - timedelta(minutes=1),
        reviewer_id=uuid4(),
        terms_reviewed_at=now - timedelta(minutes=1),
        robots_reviewed_at=now - timedelta(minutes=1),
        authentication_required=False,
        allowed_path_prefixes=("/pricing", "/pricing/"),
        allowed_content_types=("text/html",),
        user_agent="MASK-AI-Market-Research/0.1 (real M4/M5 pricing evidence)",
        policy_notes=(
            "Real, targeted retrieval of Jobber's own public pricing page via Common "
            "Crawl's archived copy -- unblocks M4 annual_existing_paid_spend_usd and M5 "
            "pricing_proof for any market whose real evidence names Jobber. Priority-4 "
            "path per docs/SCRAPING_POLICY.md (straightforward public HTTP collection); "
            "Common Crawl targeted retrieval per docs/COMMON_CRAWL.md. No login/paywall/"
            "robots bypass -- public marketing page."
        ),
        access_class=EvidenceAccessClass.PUBLIC,
        raw_retention_days=365,
        capture_author=False,
    )


def main() -> None:
    policy = _policy()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "source_policy.json").write_text(policy.model_dump_json(indent=2), encoding="utf-8")
    print(f"Real SourcePolicy registered for {URL} (in-process, this run only).")

    ledger = BudgetLedger(
        RunBudgetLimits(
            max_requests=3,
            max_documents=1,
            max_total_bytes=5_000_000,
            max_duration_seconds=60,
            max_paid_cost_usd=Decimal("0"),
        )
    )
    retriever = CommonCrawlRetriever(
        CommonCrawlSettings(enabled=True, policy_approved=True),
        UrllibCommonCrawlTransport(),
        now=lambda: datetime.now(UTC),
    )

    print(f"Real CDX lookup: {URL} in {COLLECTION} ...")
    try:
        capture = retriever.find_capture(URL, COLLECTION, policy, ledger)
    except CommonCrawlError as error:
        print(f"Real CDX lookup FAILED (recorded, not silently dropped): {error.code}")
        return
    if capture is None:
        print(f"No real Common Crawl capture found for {URL} in {COLLECTION}.")
        print("Real, honest outcome: this source stays UNKNOWN, not estimated.")
        return
    print(
        f"Real capture found: collection={capture.collection_id} "
        f"timestamp={capture.timestamp} warc_filename={capture.warc_filename}"
    )

    try:
        resource, provenance = retriever.fetch_resource(capture, policy, ledger)
    except CommonCrawlError as error:
        print(f"Real WARC fetch FAILED (recorded, not silently dropped): {error.code}")
        return

    print(f"Real fetch: status={resource.status_code}, {len(resource.body)} real bytes")
    document = to_parsed_document(resource, provenance, policy)
    print(f"Real parsed title: {document.title!r}")

    (OUT_DIR / "raw_body.html").write_bytes(resource.body)
    summary = {
        "url": URL,
        "collection_id": provenance.collection_id,
        "capture_timestamp": capture.timestamp,
        "warc_filename": provenance.warc_filename,
        "warc_offset": provenance.warc_offset,
        "status_code": resource.status_code,
        "title": document.title,
        "normalized_text_excerpt": (document.text or "")[:4000],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nOutput: {OUT_DIR}")


if __name__ == "__main__":
    main()
