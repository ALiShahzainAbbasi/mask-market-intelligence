"""Cache ports and local immutable-artifact adapter for keyword metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import ValidationError

from mask_api.modules.search_intent.contracts import (
    HistoricalMetricsRequest,
    KeywordHistoricalBatch,
    KeywordMetricsCacheRecord,
)
from mask_api.research_runner.artifacts import ArtifactKind, ArtifactStoreError
from mask_api.research_runner.ports import ArtifactStore


class KeywordMetricsCacheError(RuntimeError):
    """A cache record could not be persisted or validated safely."""


class KeywordMetricsCache(Protocol):
    def get(
        self, request: HistoricalMetricsRequest, *, now: datetime
    ) -> KeywordHistoricalBatch | None: ...

    def put(
        self, request: HistoricalMetricsRequest, batch: KeywordHistoricalBatch
    ) -> KeywordMetricsCacheRecord: ...


class ArtifactKeywordMetricsCache:
    """Persist append-only cache records through the selected artifact store."""

    def __init__(self, artifacts: ArtifactStore, ttl: timedelta = timedelta(days=30)) -> None:
        if ttl <= timedelta(0) or ttl > timedelta(days=31):
            raise ValueError("keyword metrics cache TTL must be in (0, 31 days]")
        self._artifacts = artifacts
        self._ttl = ttl

    def get(
        self, request: HistoricalMetricsRequest, *, now: datetime
    ) -> KeywordHistoricalBatch | None:
        if now.tzinfo is None:
            raise ValueError("cache clock must be timezone-aware")
        prefix = f"ads/{request.cache_key[:24]}/"
        records: list[KeywordMetricsCacheRecord] = []
        try:
            receipts = self._artifacts.list_artifacts(ArtifactKind.CACHE)
            for receipt in receipts:
                if not receipt.relative_path.startswith(prefix):
                    continue
                payload = self._artifacts.read_bytes(ArtifactKind.CACHE, receipt.relative_path)
                record = KeywordMetricsCacheRecord.model_validate_json(payload)
                if record.request.cache_key != request.cache_key:
                    raise KeywordMetricsCacheError("cache key does not match cache path")
                if record.is_fresh_at(now):
                    records.append(record)
        except (ArtifactStoreError, ValidationError, ValueError) as error:
            raise KeywordMetricsCacheError("keyword metrics cache could not be read") from error
        if not records:
            return None
        newest = max(records, key=lambda record: record.batch.retrieved_at)
        return newest.batch

    def put(
        self, request: HistoricalMetricsRequest, batch: KeywordHistoricalBatch
    ) -> KeywordMetricsCacheRecord:
        record = KeywordMetricsCacheRecord(
            request=request,
            batch=batch,
            expires_at=batch.retrieved_at + self._ttl,
        )
        retrieved = batch.retrieved_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        relative_path = (
            f"ads/{request.cache_key[:24]}/{retrieved}-{batch.response_sha256[:16]}.json"
        )
        try:
            self._artifacts.write_bytes(
                ArtifactKind.CACHE,
                relative_path,
                record.model_dump_json(indent=2, exclude_computed_fields=True).encode("utf-8")
                + b"\n",
            )
        except ArtifactStoreError as error:
            raise KeywordMetricsCacheError("keyword metrics cache could not be written") from error
        return record
