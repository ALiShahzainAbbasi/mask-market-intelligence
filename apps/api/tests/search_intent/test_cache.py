from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from mask_api.modules.search_intent.cache import ArtifactKeywordMetricsCache
from mask_api.modules.search_intent.contracts import HistoricalMetricsRequest
from mask_api.modules.search_intent.google_ads import parse_google_ads_historical_metrics
from mask_api.research_runner.artifacts import ArtifactKind
from mask_api.research_runner.local_artifacts import LocalArtifactStore

FIXTURE = Path(__file__).parent / "fixtures/google_ads_historical.json"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def request() -> HistoricalMetricsRequest:
    return HistoricalMetricsRequest(
        account_scope_sha256="b" * 64,
        keywords=("field service software",),
        geo_target_constants=("geoTargetConstants/2840",),
        language_constant="languageConstants/1000",
        currency_code="USD",
    )


def test_artifact_cache_is_append_only_freshness_aware_and_secret_free(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    cache = ArtifactKeywordMetricsCache(store, ttl=timedelta(days=30))
    requested = request()
    batch = parse_google_ads_historical_metrics(FIXTURE.read_bytes(), requested, retrieved_at=NOW)

    record = cache.put(requested, batch)

    receipts = store.list_artifacts(ArtifactKind.CACHE)
    assert len(receipts) == 1
    assert requested.cache_key[:24] in receipts[0].relative_path
    assert record.expires_at == NOW + timedelta(days=30)
    assert cache.get(requested, now=NOW + timedelta(days=29)) == batch
    assert cache.get(requested, now=NOW + timedelta(days=30)) is None
    serialized = store.read_bytes(ArtifactKind.CACHE, receipts[0].relative_path)
    assert b"customer_id" not in serialized
    assert b"developer_token" not in serialized
