from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mask_api.modules.onet_data.cache import LocalOnetCache, OnetCacheError
from mask_api.modules.onet_data.contracts import OnetDatasetDescriptor

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def descriptor(archive_bytes: bytes, **changes: object) -> OnetDatasetDescriptor:
    values: dict[str, object] = {
        "version": "31.0",
        "source_url": "https://www.onetcenter.org/dl_files/database/db_31_0_csv.zip",
        "content_length": len(archive_bytes),
        "etag": '"fixture-etag"',
        "last_modified": "Tue, 25 Aug 2026 03:47:42 GMT",
        "retrieved_at": NOW,
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_filename": "db_31_0_csv.zip",
    }
    values.update(changes)
    return OnetDatasetDescriptor(**values)  # type: ignore[arg-type]


def test_read_descriptor_returns_none_when_nothing_is_cached(tmp_path: Path) -> None:
    cache = LocalOnetCache(tmp_path / "onet")

    assert cache.read_descriptor() is None


def test_write_then_read_round_trips_descriptor_and_archive(tmp_path: Path) -> None:
    cache = LocalOnetCache(tmp_path / "onet")
    archive_bytes = b"fixture zip bytes"
    record = descriptor(archive_bytes)

    cache.write(record, archive_bytes)

    assert cache.read_descriptor() == record
    assert cache.read_archive(record.archive_filename) == archive_bytes


def test_write_overwrites_a_previous_cached_dataset(tmp_path: Path) -> None:
    cache = LocalOnetCache(tmp_path / "onet")
    first_bytes = b"fixture zip v1"
    second_bytes = b"fixture zip v2, a little longer"
    cache.write(descriptor(first_bytes), first_bytes)

    second = descriptor(second_bytes)
    cache.write(second, second_bytes)

    assert cache.read_descriptor() == second
    assert cache.read_archive(second.archive_filename) == second_bytes


def test_reading_a_missing_archive_raises_a_typed_error(tmp_path: Path) -> None:
    cache = LocalOnetCache(tmp_path / "onet")

    with pytest.raises(OnetCacheError) as captured:
        cache.read_archive("db_31_0_csv.zip")

    assert captured.value.code == "onet.cache_archive_unreadable"


def test_a_path_traversal_archive_filename_is_rejected(tmp_path: Path) -> None:
    cache = LocalOnetCache(tmp_path / "onet")

    with pytest.raises(OnetCacheError) as captured:
        cache.read_archive("../escape.zip")

    assert captured.value.code == "onet.cache_path_invalid"


def test_corrupt_descriptor_json_raises_rather_than_silently_ignoring(tmp_path: Path) -> None:
    cache_dir = tmp_path / "onet"
    cache_dir.mkdir()
    (cache_dir / "dataset_descriptor.json").write_text("not json", encoding="utf-8")
    cache = LocalOnetCache(cache_dir)

    with pytest.raises(OnetCacheError) as captured:
        cache.read_descriptor()

    assert captured.value.code == "onet.cache_descriptor_corrupt"
