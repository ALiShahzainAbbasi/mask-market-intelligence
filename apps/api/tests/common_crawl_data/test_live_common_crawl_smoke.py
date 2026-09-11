from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from mask_api.modules.common_crawl_data.errors import CommonCrawlError
from mask_api.modules.common_crawl_data.integration import to_parsed_document
from mask_api.modules.common_crawl_data.retriever import CommonCrawlRetriever, CommonCrawlSettings
from mask_api.modules.common_crawl_data.transport import UrllibCommonCrawlTransport
from mask_api.modules.evidence.contracts import SourcePolicy
from mask_api.modules.evidence.domain import (
    CollectionMethod,
    CollectorKind,
    EvidenceAccessClass,
    SourcePolicyStatus,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MASK_RUN_LIVE_COMMON_CRAWL_SMOKE") != "1"
        or os.getenv("MASK_COMMON_CRAWL_POLICY_APPROVED") != "1",
        reason="live Common Crawl smoke requires explicit run and policy approval flags",
    ),
]

COLLECTION = "CC-MAIN-2026-34"
URL = "https://example.com/"


def _policy() -> SourcePolicy:
    now = datetime.now(UTC)
    return SourcePolicy(
        id=uuid4(),
        source_id=uuid4(),
        version="policy-v1",
        source_name="Live Common Crawl smoke fixture",
        source_family="common_crawl_smoke",
        base_url=URL,
        status=SourcePolicyStatus.ALLOWED,
        collection_method=CollectionMethod.API,
        collector_kind=CollectorKind.COMMON_CRAWL,
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
        approved_at=now - timedelta(days=1),
        reviewer_id=uuid4(),
        terms_reviewed_at=now - timedelta(days=1),
        robots_reviewed_at=now - timedelta(days=1),
        authentication_required=False,
        allowed_path_prefixes=("/",),
        allowed_content_types=("text/html",),
        user_agent="MASK-AI-Market-Research/0.1 (live smoke test)",
        policy_notes="Live smoke fixture policy targeting the public example.com domain.",
        access_class=EvidenceAccessClass.PUBLIC,
        raw_retention_days=90,
        capture_author=False,
    )


def test_live_common_crawl_find_capture_and_fetch_resource() -> None:
    policy = _policy()
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

    capture = retriever.find_capture(URL, COLLECTION, policy, ledger)
    if capture is None:
        pytest.skip(f"{URL} has no capture in {COLLECTION} right now")

    try:
        resource, provenance = retriever.fetch_resource(capture, policy, ledger)
    except CommonCrawlError as error:
        pytest.fail(f"live WARC fetch failed: {error.code}")

    assert resource.status_code == 200
    assert b"Example Domain" in resource.body
    assert provenance.collection_id == COLLECTION
    assert provenance.warc_offset == capture.warc_offset

    document = to_parsed_document(resource, provenance, policy)
    assert "Example Domain" in (document.title or "")
