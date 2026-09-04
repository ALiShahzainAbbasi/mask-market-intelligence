from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mask_api.modules.evidence.contracts import (
    CollectionRequest,
    FetchedResource,
    PersistReceipt,
)
from mask_api.modules.evidence.domain import CollectionRunStatus, CollectorKind, SourcePolicyStatus
from mask_api.modules.evidence.errors import (
    FetchFailure,
    PersistenceFailure,
    SourcePolicyDenied,
    SourcePolicyUnavailable,
)
from mask_api.modules.evidence.services import CollectionService
from mask_api.modules.evidence.wiring import default_collectors

FIXTURES = Path(__file__).parent / "fixtures"


class PolicyProvider:
    def __init__(self, policy) -> None:
        self.policy = policy

    def get_policy(self, policy_version_id):
        if isinstance(self.policy, Exception):
            raise self.policy
        return self.policy


class Clock:
    def __init__(self) -> None:
        self.current = datetime(2026, 9, 4, tzinfo=UTC)
        self.monotonic_value = 100.0

    def now(self):
        return self.current

    def monotonic(self):
        return self.monotonic_value


class Sleeper:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.monotonic_value += seconds


class Jitter:
    def __init__(self, value=0.0) -> None:
        self.value = value

    def fraction(self) -> float:
        return self.value


class Cancellation:
    def __init__(self, cancelled=False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class Fetcher:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def fetch(self, url, policy, fetched_at, max_bytes):
        self.calls.append((url, max_bytes))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        content_type, body = outcome
        return FetchedResource(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type=content_type,
            body=body,
            fetched_at=fetched_at,
        )


class Writer:
    def __init__(self, *, fail=False, mismatched=False) -> None:
        self.fail = fail
        self.mismatched = mismatched
        self.calls = []

    def persist(self, batch, idempotency_key):
        self.calls.append((batch, idempotency_key))
        if self.fail:
            raise RuntimeError("private database detail")
        return PersistReceipt(
            run_id=uuid4() if self.mismatched else batch.run_id,
            idempotency_key=idempotency_key,
            inserted_occurrences=len(batch.documents),
            inserted_canonical_documents=len(batch.canonical_documents),
        )


def request(policy, kind: CollectorKind, *urls: str) -> CollectionRequest:
    return CollectionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        organization_id=uuid4(),
        market_id=uuid4(),
        market_definition_version_id=uuid4(),
        source_policy_version_id=policy.id,
        collector_kind=kind,
        start_urls=urls,
    )


def service(policy, fetcher, writer=None, cancellation=None):
    clock = Clock()
    sleeper = Sleeper(clock)
    instance = CollectionService(
        policy_provider=PolicyProvider(policy),
        fetcher=fetcher,
        writer=writer or Writer(),
        collectors=default_collectors(),
        clock=clock,
        sleeper=sleeper,
        jitter=Jitter(),
        cancellation=cancellation or Cancellation(),
    )
    return instance, sleeper


@pytest.mark.parametrize(
    ("kind", "filename", "content_type", "url", "expected_documents"),
    [
        (
            CollectorKind.RSS_ATOM,
            "rss_success.xml",
            "application/rss+xml; charset=utf-8",
            "https://research.example.test/feeds/rss",
            2,
        ),
        (
            CollectorKind.STATIC_HTML,
            "html_success.html",
            "text/html; charset=utf-8",
            "https://research.example.test/articles/field-service",
            1,
        ),
    ],
)
def test_both_collectors_use_the_same_persisted_pipeline(
    source_policy, kind, filename, content_type, url, expected_documents
) -> None:
    policy = source_policy.model_copy(update={"collector_kind": kind})
    writer = Writer()
    collector_service, _ = service(
        policy,
        Fetcher([(content_type, (FIXTURES / filename).read_bytes())]),
        writer,
    )

    result = collector_service.run(request(policy, kind, url))

    assert result.batch.status is CollectionRunStatus.SUCCEEDED
    assert result.batch.metrics.documents_parsed == expected_documents
    assert result.batch.raw_resources[0].body == (FIXTURES / filename).read_bytes()
    assert writer.calls[0][0] == result.batch
    assert len(result.persistence.idempotency_key) == 64


def test_exact_feed_duplicates_do_not_inflate_unique_count(source_policy) -> None:
    body = (FIXTURES / "rss_success.xml").read_bytes()
    fetcher = Fetcher([("application/rss+xml", body)])
    collector_service, _ = service(source_policy, fetcher)

    result = collector_service.run(
        request(
            source_policy,
            CollectorKind.RSS_ATOM,
            "https://research.example.test/feeds/rss",
        )
    )

    assert result.batch.metrics.documents_parsed == 2
    assert result.batch.metrics.unique_documents == 1
    assert result.batch.metrics.duplicate_occurrences == 1
    assert len(result.batch.documents) == 2


def test_retry_is_bounded_and_uses_backoff(source_policy) -> None:
    body = (FIXTURES / "rss_empty.xml").read_bytes()
    fetcher = Fetcher(
        [
            FetchFailure(
                "collection.network_error",
                "Temporary source failure.",
                retryable=True,
            ),
            ("application/rss+xml", body),
        ]
    )
    collector_service, sleeper = service(source_policy, fetcher)

    result = collector_service.run(
        request(
            source_policy,
            CollectorKind.RSS_ATOM,
            "https://research.example.test/feeds/rss",
        )
    )

    assert result.batch.status is CollectionRunStatus.SUCCEEDED
    assert result.batch.metrics.requests_attempted == 2
    assert sleeper.calls == [0.5]


def test_parse_failure_retains_raw_response_and_records_failed_run(source_policy) -> None:
    body = (FIXTURES / "feed_malformed.xml").read_bytes()
    collector_service, _ = service(
        source_policy,
        Fetcher([("application/rss+xml", body)]),
    )
    result = collector_service.run(
        request(
            source_policy,
            CollectorKind.RSS_ATOM,
            "https://research.example.test/feeds/broken",
        )
    )

    assert result.batch.status is CollectionRunStatus.FAILED
    assert result.batch.raw_resources[0].body == body
    assert result.batch.documents == ()
    assert result.batch.issues[0].code == "collection.malformed_feed"


def test_policy_denial_prevents_fetch_and_persistence(source_policy) -> None:
    policy = source_policy.model_copy(update={"status": SourcePolicyStatus.BLOCKED})
    fetcher = Fetcher([])
    writer = Writer()
    collector_service, _ = service(policy, fetcher, writer)

    with pytest.raises(SourcePolicyDenied):
        collector_service.run(
            request(
                policy,
                CollectorKind.RSS_ATOM,
                "https://research.example.test/feeds/rss",
            )
        )
    assert fetcher.calls == []
    assert writer.calls == []


def test_policy_repository_failure_is_safe(source_policy) -> None:
    fetcher = Fetcher([])
    writer = Writer()
    clock = Clock()
    collector_service = CollectionService(
        policy_provider=PolicyProvider(RuntimeError("private database detail")),
        fetcher=fetcher,
        writer=writer,
        collectors=default_collectors(),
        clock=clock,
        sleeper=Sleeper(clock),
        jitter=Jitter(),
        cancellation=Cancellation(),
    )
    with pytest.raises(SourcePolicyUnavailable) as failure:
        collector_service.run(
            request(
                source_policy,
                CollectorKind.RSS_ATOM,
                "https://research.example.test/feeds/rss",
            )
        )
    assert "private" not in str(failure.value)
    assert fetcher.calls == []
    assert writer.calls == []


def test_request_cap_and_circuit_breaker_stop_further_network_work(source_policy) -> None:
    policy = source_policy.model_copy(
        update={
            "max_fetch_attempts": 1,
            "max_requests": 5,
            "circuit_breaker_failures": 2,
        }
    )
    fetcher = Fetcher(
        [
            FetchFailure("collection.http_error", "Denied.", retryable=False),
            FetchFailure("collection.http_error", "Denied.", retryable=False),
        ]
    )
    collector_service, _ = service(policy, fetcher)
    result = collector_service.run(
        request(
            policy,
            CollectorKind.RSS_ATOM,
            "https://research.example.test/feeds/one",
            "https://research.example.test/feeds/two",
            "https://research.example.test/feeds/three",
        )
    )

    assert result.batch.status is CollectionRunStatus.FAILED
    assert result.batch.metrics.requests_attempted == 2
    assert result.batch.issues[-1].code == "collection.circuit_open"
    assert len(fetcher.calls) == 2


def test_cancellation_is_recorded_without_network_work(source_policy) -> None:
    fetcher = Fetcher([])
    collector_service, _ = service(
        source_policy,
        fetcher,
        cancellation=Cancellation(cancelled=True),
    )
    result = collector_service.run(
        request(
            source_policy,
            CollectorKind.RSS_ATOM,
            "https://research.example.test/feeds/rss",
        )
    )
    assert result.batch.status is CollectionRunStatus.CANCELLED
    assert result.batch.issues[0].code == "collection.cancelled"
    assert fetcher.calls == []


@pytest.mark.parametrize("writer", [Writer(fail=True), Writer(mismatched=True)])
def test_persistence_errors_are_safe(source_policy, writer) -> None:
    body = (FIXTURES / "rss_empty.xml").read_bytes()
    collector_service, _ = service(
        source_policy,
        Fetcher([("application/rss+xml", body)]),
        writer,
    )
    with pytest.raises(PersistenceFailure) as failure:
        collector_service.run(
            request(
                source_policy,
                CollectorKind.RSS_ATOM,
                "https://research.example.test/feeds/rss",
            )
        )
    assert "private" not in str(failure.value)
