"""Disabled-by-default O*NET database bootstrap: download, cache, import.

Downloads the official O*NET downloadable CSV database release (not the
separate, approval-gated O*NET Web Services API), verifies what was
received, caches it locally, and imports two bounded tables --
`occupation_data.csv` and `task_statements.csv` -- for M3 occupation/task/
workflow mapping. A cached copy whose remote descriptor (Content-Length,
ETag) still matches is reused without a redundant ~16MB download.
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO

from mask_api.modules.onet_data.cache import OnetCache
from mask_api.modules.onet_data.contracts import OnetDatasetDescriptor, OnetImportBatch
from mask_api.modules.onet_data.parsers import parse_occupation_data, parse_task_statements
from mask_api.modules.onet_data.transport import OnetHeadResult, OnetTransport, OnetTransportError
from mask_api.research_runner.budgets import BudgetCharge, BudgetLedger

_DEFAULT_BASE_URL = "https://www.onetcenter.org/dl_files/database"


@dataclass(frozen=True)
class OnetBootstrapSettings:
    enabled: bool = False
    policy_approved: bool = False
    dataset_version: str = "31.0"
    source_base_url: str = _DEFAULT_BASE_URL
    timeout_seconds: float = 60.0
    max_response_bytes: int = 25_000_000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("O*NET timeout must be in the interval (0, 300]")
        if self.max_response_bytes < 1_000_000 or self.max_response_bytes > 100_000_000:
            raise ValueError("O*NET response byte limit is outside the safe range")

    @property
    def archive_filename(self) -> str:
        return f"db_{self.dataset_version.replace('.', '_')}_csv.zip"

    @property
    def source_url(self) -> str:
        return f"{self.source_base_url}/{self.archive_filename}"


class OnetBootstrapper:
    def __init__(
        self,
        settings: OnetBootstrapSettings,
        transport: OnetTransport,
        cache: OnetCache,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._cache = cache
        self._now = now or (lambda: datetime.now(UTC))

    def ensure_dataset(self, ledger: BudgetLedger) -> OnetDatasetDescriptor:
        """Return a cached or freshly downloaded, verified dataset descriptor."""
        self._require_enabled()
        cached = self._cache.read_descriptor()
        ledger.ensure_capacity(BudgetCharge(requests=1))
        head = self._transport.head(
            self._settings.source_url, timeout_seconds=self._settings.timeout_seconds
        )
        ledger.consume(BudgetCharge(requests=1))
        if head.status_code < 200 or head.status_code > 299:
            raise OnetTransportError(f"onet.head_http_{head.status_code}")
        if cached is not None and self._matches_remote(cached, head):
            return cached
        return self._download_and_cache(ledger, head)

    def import_batch(self, descriptor: OnetDatasetDescriptor) -> OnetImportBatch:
        archive_bytes = self._cache.read_archive(descriptor.archive_filename)
        if hashlib.sha256(archive_bytes).hexdigest() != descriptor.sha256:
            raise OnetTransportError("onet.cached_archive_checksum_mismatch")
        prefix = self._member_prefix(descriptor)
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            occupation_bytes = archive.read(f"{prefix}occupation_data.csv")
            task_bytes = archive.read(f"{prefix}task_statements.csv")
        occupations, occupation_issues = parse_occupation_data(occupation_bytes)
        tasks, task_issues = parse_task_statements(task_bytes)
        return OnetImportBatch(
            descriptor=descriptor,
            occupations=occupations,
            task_statements=tasks,
            issues=(*occupation_issues, *task_issues),
        )

    def _member_prefix(self, descriptor: OnetDatasetDescriptor) -> str:
        return f"db_{descriptor.version.replace('.', '_')}_csv/"

    def _matches_remote(self, cached: OnetDatasetDescriptor, head: OnetHeadResult) -> bool:
        if cached.version != self._settings.dataset_version:
            return False
        if head.content_length is not None and head.content_length != cached.content_length:
            return False
        if head.etag is not None and cached.etag is not None and head.etag != cached.etag:
            return False
        return True

    def _download_and_cache(
        self, ledger: BudgetLedger, head: OnetHeadResult
    ) -> OnetDatasetDescriptor:
        ledger.ensure_capacity(
            BudgetCharge(requests=1, total_bytes=self._settings.max_response_bytes)
        )
        response = self._transport.download(
            self._settings.source_url,
            timeout_seconds=self._settings.timeout_seconds,
            max_bytes=self._settings.max_response_bytes,
        )
        ledger.consume(BudgetCharge(requests=1, total_bytes=len(response.body)))
        if response.status_code < 200 or response.status_code > 299:
            raise OnetTransportError(f"onet.download_http_{response.status_code}")
        if response.content_type.split(";", maxsplit=1)[0].strip().casefold() not in (
            "application/zip",
            "application/octet-stream",
            "application/x-zip-compressed",
        ):
            raise OnetTransportError("onet.content_type_invalid")
        if head.content_length is not None and len(response.body) != head.content_length:
            # The transport's single read can return fewer bytes than the
            # server declared (observed with a slow/unstable connection to
            # this ~16MB archive). Never cache a short read as if it were
            # the complete dataset -- surface it as a retryable failure.
            raise OnetTransportError("onet.download_incomplete", retryable=True)
        descriptor = OnetDatasetDescriptor(
            version=self._settings.dataset_version,
            source_url=self._settings.source_url,
            content_length=len(response.body),
            etag=head.etag,
            last_modified=head.last_modified,
            retrieved_at=self._timestamp(),
            sha256=hashlib.sha256(response.body).hexdigest(),
            archive_filename=self._settings.archive_filename,
        )
        self._cache.write(descriptor, response.body)
        return descriptor

    def _require_enabled(self) -> None:
        if not self._settings.enabled:
            raise OnetTransportError("onet.disabled")
        if not self._settings.policy_approved:
            raise OnetTransportError("onet.policy_not_approved")

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise OnetTransportError("onet.clock_not_timezone_aware")
        return value
