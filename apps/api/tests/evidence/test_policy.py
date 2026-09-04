from datetime import UTC, datetime, timedelta

import pytest
from mask_api.modules.evidence.domain import (
    CollectionMethod,
    CollectorKind,
    SourcePolicyStatus,
)
from mask_api.modules.evidence.errors import SourcePolicyDenied
from mask_api.modules.evidence.policy import (
    require_allowed_fetch_url,
    require_dispatchable_policy,
    require_safe_reference_url,
)


def test_approved_current_policy_is_dispatchable(source_policy) -> None:
    require_dispatchable_policy(
        source_policy,
        CollectorKind.RSS_ATOM,
        datetime(2026, 9, 4, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "status",
    [
        SourcePolicyStatus.BLOCKED,
        SourcePolicyStatus.CONDITIONAL,
        SourcePolicyStatus.REVIEW_REQUIRED,
    ],
)
def test_non_allowed_policy_is_denied(source_policy, status) -> None:
    policy = source_policy.model_copy(update={"status": status})
    with pytest.raises(SourcePolicyDenied) as failure:
        require_dispatchable_policy(
            policy, CollectorKind.RSS_ATOM, datetime(2026, 9, 4, tzinfo=UTC)
        )
    assert failure.value.code == "source_policy.not_allowed"


def test_missing_review_expiry_auth_and_method_are_denied(source_policy) -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    cases = (
        (source_policy.model_copy(update={"robots_reviewed_at": None}), "source_policy.unreviewed"),
        (
            source_policy.model_copy(update={"expires_at": now - timedelta(seconds=1)}),
            "source_policy.expired",
        ),
        (
            source_policy.model_copy(update={"authentication_required": True}),
            "source_policy.authentication_required",
        ),
        (
            source_policy.model_copy(update={"collection_method": CollectionMethod.API}),
            "source_policy.method_mismatch",
        ),
    )
    for policy, code in cases:
        with pytest.raises(SourcePolicyDenied) as failure:
            require_dispatchable_policy(policy, CollectorKind.RSS_ATOM, now)
        assert failure.value.code == code


def test_tenant_owned_policy_cannot_cross_organization(source_policy) -> None:
    owner = source_policy.source_id
    policy = source_policy.model_copy(update={"organization_id": owner})
    with pytest.raises(SourcePolicyDenied) as failure:
        require_dispatchable_policy(
            policy,
            CollectorKind.RSS_ATOM,
            datetime(2026, 9, 4, tzinfo=UTC),
            source_policy.id,
        )
    assert failure.value.code == "source_policy.organization_mismatch"

    require_dispatchable_policy(
        policy,
        CollectorKind.RSS_ATOM,
        datetime(2026, 9, 4, tzinfo=UTC),
        owner,
    )


def test_fetch_url_requires_exact_approved_origin_path_and_query(source_policy) -> None:
    require_allowed_fetch_url("https://research.example.test/feeds/latest?page=1", source_policy)
    denied = (
        "http://research.example.test/feeds/latest",
        "https://other.example.test/feeds/latest",
        "https://research.example.test/private/latest",
        "https://research.example.test/feeds/latest?token=secret",
        "https://user:password@research.example.test/feeds/latest",
        "https://research.example.test/feeds/%2e%2e/private",
        "https://research.example.test/feeds/latest#fragment",
    )
    for url in denied:
        with pytest.raises(SourcePolicyDenied):
            require_allowed_fetch_url(url, source_policy)


def test_untrusted_reference_url_falls_back_to_fetched_url() -> None:
    fallback = "https://research.example.test/feeds/latest"
    assert require_safe_reference_url("javascript:alert(1)", fallback) == fallback
    assert require_safe_reference_url("https://public.example/article", fallback) == (
        "https://public.example/article"
    )
