from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from mask_api.config import Settings
from mask_api.modules.evidence.contracts import SourcePolicy
from mask_api.modules.evidence.domain import (
    CollectionMethod,
    CollectorKind,
    EvidenceAccessClass,
    SourcePolicyStatus,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+psycopg://localhost/mask_test",
        enable_dev_routes=False,
    )


@pytest.fixture
def source_policy() -> SourcePolicy:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    return SourcePolicy(
        id=uuid4(),
        source_id=uuid4(),
        version="policy-v1",
        source_name="Fixture source",
        base_url="https://research.example.test/",
        status=SourcePolicyStatus.ALLOWED,
        collection_method=CollectionMethod.SCRAPE,
        collector_kind=CollectorKind.RSS_ATOM,
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
        approved_at=now - timedelta(days=1),
        reviewer_id=uuid4(),
        terms_reviewed_at=now - timedelta(days=1),
        robots_reviewed_at=now - timedelta(days=1),
        authentication_required=False,
        allowed_path_prefixes=("/feeds", "/articles"),
        allowed_query_parameters=("page",),
        allowed_content_types=(
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
            "text/html",
        ),
        user_agent="MASK-AI-Research/0.1 (owner-approved contact)",
        policy_notes="Offline fixture policy for collector tests.",
        access_class=EvidenceAccessClass.PUBLIC,
        raw_retention_days=90,
        capture_author=False,
        min_interval_seconds=0,
    )
