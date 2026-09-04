from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from mask_api.modules.evidence.domain import (
    CollectionMethod,
    CollectionRunStatus,
    CollectorKind,
    EvidenceAccessClass,
    SourcePolicyStatus,
)


class EvidenceValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SourcePolicy(EvidenceValue):
    id: UUID
    source_id: UUID
    organization_id: UUID | None = None
    version: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=8, max_length=2048)
    status: SourcePolicyStatus
    collection_method: CollectionMethod
    collector_kind: CollectorKind
    effective_at: AwareDatetime
    expires_at: AwareDatetime
    approved_at: AwareDatetime | None = None
    reviewer_id: UUID | None = None
    terms_reviewed_at: AwareDatetime | None = None
    robots_reviewed_at: AwareDatetime | None = None
    authentication_required: bool
    allow_insecure_http: bool = False
    allowed_path_prefixes: tuple[str, ...] = Field(default=("/",), min_length=1, max_length=32)
    allowed_query_parameters: tuple[str, ...] = Field(default=(), max_length=32)
    allowed_content_types: tuple[str, ...] = Field(min_length=1, max_length=16)
    user_agent: str = Field(min_length=8, max_length=300)
    policy_notes: str = Field(min_length=1, max_length=2000)
    access_class: EvidenceAccessClass
    raw_retention_days: int = Field(ge=1, le=3650)
    capture_author: bool = False
    max_discovered_urls: int = Field(default=10, ge=1, le=100)
    max_requests: int = Field(default=10, ge=1, le=100)
    max_documents: int = Field(default=100, ge=1, le=1000)
    max_response_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)
    max_total_bytes: int = Field(default=5_000_000, ge=1024, le=50_000_000)
    max_run_seconds: float = Field(default=60.0, gt=0, le=900)
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    min_interval_seconds: float = Field(default=1.0, ge=0, le=60)
    max_fetch_attempts: int = Field(default=2, ge=1, le=5)
    retry_base_seconds: float = Field(default=0.5, ge=0, le=30)
    retry_cap_seconds: float = Field(default=5.0, ge=0, le=60)
    circuit_breaker_failures: int = Field(default=3, ge=1, le=20)
    max_concurrency: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def validate_limits_and_window(self) -> "SourcePolicy":
        if self.expires_at <= self.effective_at:
            raise ValueError("Policy expiry must be after its effective time")
        if self.request_timeout_seconds > self.max_run_seconds:
            raise ValueError("Request timeout cannot exceed the run duration limit")
        if self.retry_base_seconds > self.retry_cap_seconds:
            raise ValueError("Retry base cannot exceed the retry cap")
        return self

    @field_validator("allowed_path_prefixes")
    @classmethod
    def validate_paths(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        if any(not path.startswith("/") or "\\" in path for path in paths):
            raise ValueError("Allowed path prefixes must be absolute URL paths")
        return paths

    @field_validator("allowed_query_parameters")
    @classmethod
    def validate_query_names(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(names)) != len(names) or any(not name or len(name) > 100 for name in names):
            raise ValueError("Allowed query parameter names must be unique and bounded")
        return names

    @field_validator("allowed_content_types")
    @classmethod
    def normalize_content_types(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().lower() for value in values)
        if any("/" not in value or ";" in value for value in normalized):
            raise ValueError("Content types must be bare MIME types")
        return normalized


class CollectionRequest(EvidenceValue):
    run_id: UUID
    correlation_id: UUID
    organization_id: UUID
    market_id: UUID
    market_definition_version_id: UUID
    source_policy_version_id: UUID
    collector_kind: CollectorKind
    start_urls: tuple[str, ...] = Field(min_length=1, max_length=100)


class DiscoveredResource(EvidenceValue):
    url: str = Field(min_length=8, max_length=2048)
    external_id: str | None = Field(default=None, max_length=500)


class FetchedResource(EvidenceValue):
    requested_url: str = Field(min_length=8, max_length=2048)
    final_url: str = Field(min_length=8, max_length=2048)
    status_code: int = Field(ge=200, le=299)
    content_type: str = Field(min_length=3, max_length=200)
    body: bytes = Field(repr=False)
    fetched_at: AwareDatetime
    etag: str | None = Field(default=None, max_length=500)
    last_modified: str | None = Field(default=None, max_length=500)


class ParsedDocument(EvidenceValue):
    source_url: str = Field(min_length=8, max_length=2048)
    external_id: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=1000)
    author_persona_hint: str | None = Field(default=None, max_length=500)
    published_at: AwareDatetime | None = None
    raw_content: bytes = Field(repr=False)
    raw_content_type: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=1)
    language: str = Field(default="und", min_length=2, max_length=35)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class NormalizedDocument(EvidenceValue):
    occurrence_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    organization_id: UUID
    market_id: UUID
    market_definition_version_id: UUID
    source_id: UUID
    source_policy_version_id: UUID
    source_policy_version: str
    source_url: str
    external_id: str | None = None
    title: str | None = None
    author_persona_hint: str | None = None
    published_at: AwareDatetime | None = None
    collected_at: AwareDatetime
    raw_content: bytes = Field(repr=False)
    raw_content_type: str
    raw_content_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    normalized_text: str = Field(min_length=1)
    language: str
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, JsonValue]
    access_class: EvidenceAccessClass
    raw_retention_days: int
    collector_kind: CollectorKind
    collector_version: str
    parser_version: str
    normalizer_version: str


class DuplicateLink(EvidenceValue):
    duplicate_occurrence_key: str
    canonical_occurrence_key: str
    content_hash: str


class CollectionIssue(EvidenceValue):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    message: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=2048)
    retryable: bool = False


class CollectionMetrics(EvidenceValue):
    requests_attempted: int = Field(ge=0)
    requests_succeeded: int = Field(ge=0)
    bytes_fetched: int = Field(ge=0)
    documents_parsed: int = Field(ge=0)
    unique_documents: int = Field(ge=0)
    duplicate_occurrences: int = Field(ge=0)


class CollectionBatch(EvidenceValue):
    run_id: UUID
    correlation_id: UUID
    organization_id: UUID
    market_id: UUID
    market_definition_version_id: UUID
    source_id: UUID
    source_policy_version_id: UUID
    status: CollectionRunStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime
    raw_resources: tuple[FetchedResource, ...]
    documents: tuple[NormalizedDocument, ...]
    canonical_documents: tuple[NormalizedDocument, ...]
    duplicate_links: tuple[DuplicateLink, ...]
    issues: tuple[CollectionIssue, ...]
    metrics: CollectionMetrics


class PersistReceipt(EvidenceValue):
    run_id: UUID
    idempotency_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    inserted_occurrences: int = Field(ge=0)
    inserted_canonical_documents: int = Field(ge=0)
    already_persisted: bool = False


class CollectionResult(EvidenceValue):
    batch: CollectionBatch
    persistence: PersistReceipt
