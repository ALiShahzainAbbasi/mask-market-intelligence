from enum import StrEnum


class SourcePolicyStatus(StrEnum):
    ALLOWED = "allowed"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"


class CollectionMethod(StrEnum):
    API = "api"
    MANUAL = "manual"
    SCRAPE = "scrape"
    UPLOAD = "upload"


class CollectorKind(StrEnum):
    RSS_ATOM = "rss_atom"
    STATIC_HTML = "static_html"


class CollectionRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvidenceAccessClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
