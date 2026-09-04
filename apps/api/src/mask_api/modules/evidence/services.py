from dataclasses import dataclass

from mask_api.modules.evidence.collectors.base import Collector
from mask_api.modules.evidence.contracts import (
    CollectionBatch,
    CollectionIssue,
    CollectionMetrics,
    CollectionRequest,
    CollectionResult,
    FetchedResource,
    NormalizedDocument,
    SourcePolicy,
)
from mask_api.modules.evidence.domain import CollectionRunStatus
from mask_api.modules.evidence.errors import (
    CollectionFailure,
    FetchFailure,
    ParseFailure,
    PersistenceFailure,
    SourcePolicyDenied,
    SourcePolicyUnavailable,
)
from mask_api.modules.evidence.normalization import (
    batch_idempotency_key,
    exact_deduplicate,
    normalize_document,
)
from mask_api.modules.evidence.policy import (
    require_allowed_fetch_url,
    require_dispatchable_policy,
)
from mask_api.modules.evidence.ports import (
    CancellationSignal,
    Clock,
    EvidenceWriter,
    JitterSource,
    ResourceFetcher,
    Sleeper,
    SourcePolicyProvider,
)


@dataclass
class _Counters:
    requests_attempted: int = 0
    requests_succeeded: int = 0
    bytes_fetched: int = 0
    last_request_at: float | None = None


class CollectionService:
    """Coordinates the policy-gated discover/fetch/parse/normalize/persist pipeline."""

    def __init__(
        self,
        policy_provider: SourcePolicyProvider,
        fetcher: ResourceFetcher,
        writer: EvidenceWriter,
        collectors: tuple[Collector, ...],
        clock: Clock,
        sleeper: Sleeper,
        jitter: JitterSource,
        cancellation: CancellationSignal,
    ) -> None:
        self._policy_provider = policy_provider
        self._fetcher = fetcher
        self._writer = writer
        self._collectors = {collector.kind: collector for collector in collectors}
        self._clock = clock
        self._sleeper = sleeper
        self._jitter = jitter
        self._cancellation = cancellation

    def run(self, request: CollectionRequest) -> CollectionResult:
        try:
            policy = self._policy_provider.get_policy(request.source_policy_version_id)
        except Exception as exc:
            raise SourcePolicyUnavailable() from exc
        if policy is None or policy.id != request.source_policy_version_id:
            raise SourcePolicyDenied(
                "source_policy.not_found",
                "The requested source policy version is unavailable.",
            )
        started_at = self._clock.now()
        started_monotonic = self._clock.monotonic()
        require_dispatchable_policy(
            policy,
            request.collector_kind,
            started_at,
            request.organization_id,
        )
        collector = self._collectors.get(request.collector_kind)
        if collector is None:
            raise SourcePolicyDenied(
                "source_policy.collector_unavailable",
                "The approved collector is not installed.",
            )

        resources = collector.discover(request, policy)
        for resource in resources:
            require_allowed_fetch_url(resource.url, policy)

        issues: list[CollectionIssue] = []
        if len(dict.fromkeys(request.start_urls)) > len(resources):
            issues.append(
                CollectionIssue(
                    code="collection.discovery_limit_reached",
                    message="Discovery stopped at the approved URL limit.",
                )
            )

        counters = _Counters()
        raw_resources: list[FetchedResource] = []
        documents: list[NormalizedDocument] = []
        consecutive_failures = 0
        cancelled = False

        for resource in resources:
            if self._cancellation.is_cancelled():
                cancelled = True
                issues.append(self._issue("collection.cancelled", "Collection was cancelled."))
                break
            if len(documents) >= policy.max_documents:
                issues.append(
                    self._issue(
                        "collection.document_limit_reached",
                        "Collection stopped at the approved document limit.",
                    )
                )
                break
            if consecutive_failures >= policy.circuit_breaker_failures:
                issues.append(
                    self._issue(
                        "collection.circuit_open",
                        "Collection paused after repeated source failures.",
                    )
                )
                break

            remaining_bytes = policy.max_total_bytes - counters.bytes_fetched
            fetched, failure = self._fetch_with_retries(
                resource.url,
                policy,
                counters,
                started_monotonic,
                remaining_bytes,
            )
            if failure is not None:
                issues.append(failure)
                consecutive_failures += 1
                if failure.code == "collection.cancelled":
                    cancelled = True
                    break
                continue
            if fetched is None:
                continue
            consecutive_failures = 0
            raw_resources.append(fetched)
            counters.requests_succeeded += 1
            counters.bytes_fetched += len(fetched.body)

            try:
                parsed_documents = collector.parse(fetched, policy)
            except ParseFailure as exc:
                issues.append(self._issue(exc.code, str(exc), resource.url, exc.retryable))
                continue
            except Exception:
                issues.append(
                    self._issue(
                        "collection.parser_failed",
                        "The source response could not be parsed safely.",
                        resource.url,
                    )
                )
                continue

            for parsed in parsed_documents:
                if len(documents) >= policy.max_documents:
                    issues.append(
                        self._issue(
                            "collection.document_limit_reached",
                            "Collection stopped at the approved document limit.",
                        )
                    )
                    break
                try:
                    normalized = normalize_document(
                        parsed,
                        policy,
                        request,
                        collector.kind,
                        collector.collector_version,
                        collector.parser_version,
                        fetched.fetched_at,
                    )
                except Exception:
                    issues.append(
                        self._issue(
                            "collection.normalization_failed",
                            "A parsed document could not be normalized safely.",
                            parsed.source_url,
                        )
                    )
                    continue
                documents.append(normalized)

        canonical, duplicates = exact_deduplicate(tuple(documents))
        status = self._status(cancelled, bool(issues), bool(documents))
        completed_at = self._clock.now()
        batch = CollectionBatch(
            run_id=request.run_id,
            correlation_id=request.correlation_id,
            organization_id=request.organization_id,
            market_id=request.market_id,
            market_definition_version_id=request.market_definition_version_id,
            source_id=policy.source_id,
            source_policy_version_id=policy.id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            raw_resources=tuple(raw_resources),
            documents=tuple(documents),
            canonical_documents=canonical,
            duplicate_links=duplicates,
            issues=tuple(issues),
            metrics=CollectionMetrics(
                requests_attempted=counters.requests_attempted,
                requests_succeeded=counters.requests_succeeded,
                bytes_fetched=counters.bytes_fetched,
                documents_parsed=len(documents),
                unique_documents=len(canonical),
                duplicate_occurrences=len(duplicates),
            ),
        )
        idempotency_key = batch_idempotency_key(request.run_id, policy.id)
        try:
            receipt = self._writer.persist(batch, idempotency_key)
        except Exception as exc:
            raise PersistenceFailure() from exc
        if receipt.run_id != request.run_id or receipt.idempotency_key != idempotency_key:
            raise PersistenceFailure()
        return CollectionResult(batch=batch, persistence=receipt)

    def _fetch_with_retries(
        self,
        url: str,
        policy: SourcePolicy,
        counters: _Counters,
        started_monotonic: float,
        remaining_bytes: int,
    ) -> tuple[FetchedResource | None, CollectionIssue | None]:
        if remaining_bytes <= 0:
            return None, self._issue(
                "collection.byte_limit_reached",
                "Collection stopped at the approved byte limit.",
                url,
            )
        retry_delay = 0.0
        last_failure: CollectionFailure | None = None
        for attempt in range(1, policy.max_fetch_attempts + 1):
            if self._cancellation.is_cancelled():
                return None, self._issue("collection.cancelled", "Collection was cancelled.", url)
            if counters.requests_attempted >= policy.max_requests:
                return None, self._issue(
                    "collection.request_limit_reached",
                    "Collection stopped at the approved request limit.",
                    url,
                )
            interval_delay = 0.0
            if counters.last_request_at is not None:
                elapsed = self._clock.monotonic() - counters.last_request_at
                interval_delay = max(0.0, policy.min_interval_seconds - elapsed)
            if not self._sleep_with_budget(
                max(interval_delay, retry_delay), policy.max_run_seconds, started_monotonic
            ):
                return None, self._issue(
                    "collection.duration_limit_reached",
                    "Collection stopped at the approved duration limit.",
                    url,
                )

            counters.requests_attempted += 1
            counters.last_request_at = self._clock.monotonic()
            try:
                return (
                    self._fetcher.fetch(
                        url,
                        policy,
                        self._clock.now(),
                        min(remaining_bytes, policy.max_response_bytes),
                    ),
                    None,
                )
            except SourcePolicyDenied:
                raise
            except CollectionFailure as exc:
                last_failure = exc
            except Exception:
                last_failure = FetchFailure(
                    "collection.fetcher_failed",
                    "The source could not be fetched safely.",
                    retryable=False,
                )

            if last_failure is None or not last_failure.retryable:
                break
            if attempt == policy.max_fetch_attempts:
                break
            backoff = min(
                policy.retry_cap_seconds,
                policy.retry_base_seconds
                * (2 ** (attempt - 1))
                * (1 + 0.25 * self._jitter_value()),
            )
            retry_after = last_failure.retry_after_seconds or 0.0
            if retry_after > policy.retry_cap_seconds:
                break
            retry_delay = max(backoff, retry_after)

        assert last_failure is not None
        return None, self._issue(last_failure.code, str(last_failure), url, last_failure.retryable)

    def _sleep_with_budget(
        self, seconds: float, max_run_seconds: float, started_monotonic: float
    ) -> bool:
        elapsed = self._clock.monotonic() - started_monotonic
        remaining = max_run_seconds - elapsed
        if remaining <= 0 or seconds > remaining:
            return False
        if seconds > 0:
            self._sleeper.sleep(seconds)
        return self._clock.monotonic() - started_monotonic <= max_run_seconds

    def _jitter_value(self) -> float:
        return min(1.0, max(0.0, self._jitter.fraction()))

    @staticmethod
    def _issue(
        code: str, message: str, source_url: str | None = None, retryable: bool = False
    ) -> CollectionIssue:
        return CollectionIssue(
            code=code,
            message=message,
            source_url=source_url,
            retryable=retryable,
        )

    @staticmethod
    def _status(cancelled: bool, has_issues: bool, has_documents: bool) -> CollectionRunStatus:
        if cancelled and not has_documents:
            return CollectionRunStatus.CANCELLED
        if has_issues and has_documents:
            return CollectionRunStatus.PARTIAL
        if has_issues:
            return CollectionRunStatus.FAILED
        return CollectionRunStatus.SUCCEEDED
