import posixpath
from datetime import datetime
from urllib.parse import SplitResult, parse_qsl, unquote, urlsplit
from uuid import UUID

from mask_api.modules.evidence.contracts import SourcePolicy
from mask_api.modules.evidence.domain import (
    CollectionMethod,
    CollectorKind,
    SourcePolicyStatus,
)
from mask_api.modules.evidence.errors import SourcePolicyDenied


def require_dispatchable_policy(
    policy: SourcePolicy,
    collector_kind: CollectorKind,
    now: datetime,
    organization_id: UUID | None = None,
) -> None:
    if policy.status is not SourcePolicyStatus.ALLOWED:
        raise SourcePolicyDenied(
            "source_policy.not_allowed",
            "The source policy is not approved for collection.",
        )
    if (
        policy.approved_at is None
        or policy.reviewer_id is None
        or policy.terms_reviewed_at is None
        or policy.robots_reviewed_at is None
    ):
        raise SourcePolicyDenied(
            "source_policy.unreviewed",
            "The source policy is missing required approval reviews.",
        )
    if now < policy.effective_at or now >= policy.expires_at:
        raise SourcePolicyDenied(
            "source_policy.expired",
            "The source policy is not currently effective.",
        )
    if (
        policy.approved_at > now
        or policy.terms_reviewed_at > now
        or policy.robots_reviewed_at > now
    ):
        raise SourcePolicyDenied(
            "source_policy.invalid_review_time",
            "The source policy review timestamps are not valid for dispatch.",
        )
    if policy.collection_method is not CollectionMethod.SCRAPE:
        raise SourcePolicyDenied(
            "source_policy.method_mismatch",
            "The source policy does not permit HTTP scraping.",
        )
    if policy.collector_kind is not collector_kind:
        raise SourcePolicyDenied(
            "source_policy.collector_mismatch",
            "The source policy does not permit the requested collector.",
        )
    if policy.authentication_required:
        raise SourcePolicyDenied(
            "source_policy.authentication_required",
            "This anonymous collector cannot access an authenticated source.",
        )
    if policy.organization_id is not None and policy.organization_id != organization_id:
        raise SourcePolicyDenied(
            "source_policy.organization_mismatch",
            "The source policy does not belong to the requested organization.",
        )


def require_allowed_fetch_url(url: str, policy: SourcePolicy) -> None:
    candidate = _split_url(url)
    base = _split_url(policy.base_url)
    if candidate.scheme != base.scheme:
        raise _url_denied("scheme")
    if candidate.scheme == "http" and not policy.allow_insecure_http:
        raise _url_denied("insecure_http")
    if candidate.hostname != base.hostname or _effective_port(candidate) != _effective_port(base):
        raise _url_denied("origin")

    decoded_path = unquote(candidate.path or "/")
    segments = decoded_path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise _url_denied("path_traversal")
    normalized_path = posixpath.normpath(decoded_path)
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    if not any(_path_matches(normalized_path, prefix) for prefix in policy.allowed_path_prefixes):
        raise _url_denied("path")

    allowed_query = set(policy.allowed_query_parameters)
    for name, _ in parse_qsl(candidate.query, keep_blank_values=True, strict_parsing=False):
        if name not in allowed_query:
            raise _url_denied("query")


def require_safe_reference_url(url: str, fallback: str) -> str:
    try:
        parts = _split_url(url)
    except SourcePolicyDenied:
        return fallback
    if parts.scheme not in {"http", "https"}:
        return fallback
    return url


def _split_url(url: str) -> SplitResult:
    if len(url) > 2048 or "\\" in url or any(ord(character) < 32 for character in url):
        raise _url_denied("malformed")
    try:
        parts = urlsplit(url)
        _ = parts.port
    except ValueError as exc:
        raise _url_denied("malformed") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise _url_denied("scheme")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise _url_denied("credentials_or_fragment")
    return parts


def _effective_port(parts: SplitResult) -> int:
    return parts.port or (443 if parts.scheme == "https" else 80)


def _path_matches(path: str, prefix: str) -> bool:
    normalized_prefix = posixpath.normpath(unquote(prefix))
    if normalized_prefix == "/":
        return True
    return path == normalized_prefix or path.startswith(normalized_prefix.rstrip("/") + "/")


def _url_denied(reason: str) -> SourcePolicyDenied:
    return SourcePolicyDenied(
        f"source_policy.url_{reason}",
        "The requested URL is outside the approved source scope.",
    )
