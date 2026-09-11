from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from mask_api.modules.onet_data.bootstrap import OnetBootstrapper, OnetBootstrapSettings
from mask_api.modules.onet_data.cache import LocalOnetCache
from mask_api.modules.onet_data.transport import (
    OnetDownloadResult,
    OnetHeadResult,
    OnetTransportError,
)
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _archive_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "db_31_0_csv/occupation_data.csv", (FIXTURES / "occupation_data.csv").read_bytes()
        )
        archive.writestr(
            "db_31_0_csv/task_statements.csv", (FIXTURES / "task_statements.csv").read_bytes()
        )
    return buffer.getvalue()


ARCHIVE_BYTES = _archive_bytes()


@dataclass
class FakeTransport:
    head_results: list[OnetHeadResult] = field(default_factory=list)
    download_results: list[OnetDownloadResult] = field(default_factory=list)
    head_calls: int = 0
    download_calls: int = 0

    def head(self, url: str, *, timeout_seconds: float) -> OnetHeadResult:
        self.head_calls += 1
        return self.head_results.pop(0)

    def download(self, url: str, *, timeout_seconds: float, max_bytes: int) -> OnetDownloadResult:
        self.download_calls += 1
        return self.download_results.pop(0)


def head(**changes: object) -> OnetHeadResult:
    values: dict[str, object] = {
        "status_code": 200,
        "content_length": len(ARCHIVE_BYTES),
        "content_type": "application/zip",
        "etag": '"fixture-etag"',
        "last_modified": "Tue, 25 Aug 2026 03:47:42 GMT",
    }
    values.update(changes)
    return OnetHeadResult(**values)  # type: ignore[arg-type]


def download(body: bytes = ARCHIVE_BYTES) -> OnetDownloadResult:
    return OnetDownloadResult(status_code=200, content_type="application/zip", body=body)


def settings(**changes: object) -> OnetBootstrapSettings:
    values: dict[str, object] = {"enabled": True, "policy_approved": True}
    values.update(changes)
    return OnetBootstrapSettings(**values)  # type: ignore[arg-type]


def ledger() -> BudgetLedger:
    return BudgetLedger(
        RunBudgetLimits(
            max_requests=5,
            max_documents=5,
            max_total_bytes=50_000_000,
            max_duration_seconds=120,
            max_paid_cost_usd=Decimal("0"),
        )
    )


def bootstrapper(
    transport: FakeTransport, cache_dir: Path, configured: OnetBootstrapSettings | None = None
) -> OnetBootstrapper:
    return OnetBootstrapper(
        configured or settings(),
        transport,
        LocalOnetCache(cache_dir),
        now=lambda: NOW,
    )


def test_ensure_dataset_downloads_and_caches_when_nothing_is_cached(tmp_path: Path) -> None:
    transport = FakeTransport(head_results=[head()], download_results=[download()])
    budget = ledger()

    descriptor = bootstrapper(transport, tmp_path).ensure_dataset(budget)

    assert descriptor.version == "31.0"
    assert descriptor.content_length == len(ARCHIVE_BYTES)
    assert descriptor.etag == '"fixture-etag"'
    assert transport.head_calls == 1
    assert transport.download_calls == 1
    assert budget.usage.requests == 2
    assert budget.usage.total_bytes == len(ARCHIVE_BYTES)


def test_ensure_dataset_skips_download_when_cached_descriptor_still_matches(
    tmp_path: Path,
) -> None:
    transport = FakeTransport(head_results=[head(), head()], download_results=[download()])
    budget = ledger()
    first = bootstrapper(transport, tmp_path).ensure_dataset(budget)

    second = bootstrapper(transport, tmp_path).ensure_dataset(ledger())

    assert second == first
    assert transport.head_calls == 2
    assert transport.download_calls == 1


def test_ensure_dataset_redownloads_when_remote_content_length_changed(tmp_path: Path) -> None:
    changed_body = ARCHIVE_BYTES + b"x"
    transport = FakeTransport(
        head_results=[head(), head(content_length=len(changed_body))],
        download_results=[download(), download(body=changed_body)],
    )
    bootstrapper(transport, tmp_path).ensure_dataset(ledger())

    bootstrapper(transport, tmp_path).ensure_dataset(ledger())

    assert transport.download_calls == 2


def test_ensure_dataset_rejects_a_short_download_instead_of_caching_it(tmp_path: Path) -> None:
    transport = FakeTransport(
        head_results=[head()], download_results=[download(body=ARCHIVE_BYTES[:-1])]
    )

    with pytest.raises(OnetTransportError) as captured:
        bootstrapper(transport, tmp_path).ensure_dataset(ledger())

    assert captured.value.code == "onet.download_incomplete"
    assert captured.value.retryable is True
    assert LocalOnetCache(tmp_path).read_descriptor() is None


def test_ensure_dataset_requires_enabled_and_policy_approval(tmp_path: Path) -> None:
    transport = FakeTransport()

    with pytest.raises(OnetTransportError) as captured:
        bootstrapper(transport, tmp_path, settings(enabled=False)).ensure_dataset(ledger())

    assert captured.value.code == "onet.disabled"
    assert transport.head_calls == 0


def test_import_batch_extracts_and_parses_both_tables(tmp_path: Path) -> None:
    transport = FakeTransport(head_results=[head()], download_results=[download()])
    bootstrap = bootstrapper(transport, tmp_path)
    descriptor = bootstrap.ensure_dataset(ledger())

    batch = bootstrap.import_batch(descriptor)

    assert batch.descriptor == descriptor
    assert len(batch.occupations) == 1
    assert batch.occupations[0].onet_soc_code == "49-9021.00"
    assert len(batch.task_statements) == 3
    assert any(issue.code == "onet.occupation_data.row_invalid" for issue in batch.issues)


def test_import_batch_detects_cached_archive_corruption(tmp_path: Path) -> None:
    transport = FakeTransport(head_results=[head()], download_results=[download()])
    bootstrap = bootstrapper(transport, tmp_path)
    descriptor = bootstrap.ensure_dataset(ledger())
    (tmp_path / descriptor.archive_filename).write_bytes(b"corrupted")

    with pytest.raises(OnetTransportError) as captured:
        bootstrap.import_batch(descriptor)

    assert captured.value.code == "onet.cached_archive_checksum_mismatch"
