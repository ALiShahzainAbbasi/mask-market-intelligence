from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from mask_api.research_runner.artifacts import (
    ArtifactConflict,
    ArtifactKind,
    ArtifactLimitExceeded,
    ArtifactLimits,
    ArtifactStoreError,
    UnsafeArtifactPath,
)
from mask_api.research_runner.local_artifacts import LocalArtifactStore
from mask_api.research_runner.ports import ArtifactStore


def test_store_satisfies_artifact_port_and_preserves_raw_bytes(tmp_path: Path) -> None:
    store: ArtifactStore = LocalArtifactStore(tmp_path / "run")
    content = b"\x00raw\xffbytes"

    receipt = store.write_bytes(ArtifactKind.RAW, "source/page-001.bin", content)

    assert receipt.kind == ArtifactKind.RAW
    assert receipt.relative_path == "source/page-001.bin"
    assert receipt.sha256 == hashlib.sha256(content).hexdigest()
    assert receipt.size_bytes == len(content)
    assert receipt.already_present is False
    assert store.read_bytes(ArtifactKind.RAW, "source/page-001.bin") == content
    assert (tmp_path / "run/raw/source/page-001.bin").read_bytes() == content


def test_same_write_is_idempotent_but_content_change_conflicts(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "run")
    first = store.write_bytes(ArtifactKind.METRICS, "m1.json", b"one")
    repeated = store.write_bytes(ArtifactKind.METRICS, "m1.json", b"one")

    assert first.already_present is False
    assert repeated.already_present is True
    with pytest.raises(ArtifactConflict, match="different content"):
        store.write_bytes(ArtifactKind.METRICS, "m1.json", b"two")
    assert store.read_bytes(ArtifactKind.METRICS, "m1.json") == b"one"


@pytest.mark.parametrize("kind", list(ArtifactKind))
def test_each_required_artifact_kind_has_its_own_directory(
    tmp_path: Path, kind: ArtifactKind
) -> None:
    store = LocalArtifactStore(tmp_path / "run")

    store.write_text(kind, "checkpoint.txt", kind.value)

    assert (tmp_path / "run" / kind.value / "checkpoint.txt").read_text(
        encoding="utf-8"
    ) == kind.value


def test_json_is_deterministic_and_rejects_non_finite_values(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "run")

    receipt = store.write_json(ArtifactKind.LINEAGE, "record.json", {"z": 1, "a": "é"})

    expected = '{\n  "a": "é",\n  "z": 1\n}\n'.encode()
    assert receipt.sha256 == hashlib.sha256(expected).hexdigest()
    assert store.read_bytes(ArtifactKind.LINEAGE, "record.json") == expected
    with pytest.raises(ArtifactStoreError, match="not serializable"):
        store.write_json(ArtifactKind.METRICS, "nan.json", {"value": float("nan")})


@pytest.mark.parametrize(
    "relative_path",
    [
        "../outside.txt",
        "nested/../../outside.txt",
        "/absolute.txt",
        "C:/absolute.txt",
        "nested\\windows.txt",
        "NUL.txt",
        "nested/COM1.json",
        ".hidden",
        "has space.txt",
        "trailing-dot.",
        "",
    ],
)
def test_unsafe_or_ambiguous_paths_are_rejected(tmp_path: Path, relative_path: str) -> None:
    store = LocalArtifactStore(tmp_path / "run")

    with pytest.raises(UnsafeArtifactPath):
        store.write_text(ArtifactKind.REPORTS, relative_path, "blocked")

    assert not (tmp_path / "outside.txt").exists()


def test_file_and_run_byte_limits_are_hard_stops(tmp_path: Path) -> None:
    store = LocalArtifactStore(
        tmp_path / "run",
        ArtifactLimits(max_artifacts=3, max_file_bytes=4, max_run_bytes=6),
    )

    store.write_bytes(ArtifactKind.RAW, "first.bin", b"1234")
    with pytest.raises(ArtifactLimitExceeded, match="per-file"):
        store.write_bytes(ArtifactKind.RAW, "large.bin", b"12345")
    with pytest.raises(ArtifactLimitExceeded, match="run byte"):
        store.write_bytes(ArtifactKind.RAW, "second.bin", b"789")


def test_artifact_count_limit_is_a_hard_stop(tmp_path: Path) -> None:
    store = LocalArtifactStore(
        tmp_path / "run",
        ArtifactLimits(max_artifacts=1, max_file_bytes=4, max_run_bytes=4),
    )
    store.write_bytes(ArtifactKind.EVIDENCE, "first.bin", b"1")

    with pytest.raises(ArtifactLimitExceeded, match="count"):
        store.write_bytes(ArtifactKind.EVIDENCE, "second.bin", b"2")


def test_listing_is_sorted_filterable_and_uses_content_hashes(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "run")
    store.write_text(ArtifactKind.REPORTS, "z.html", "z")
    store.write_text(ArtifactKind.METRICS, "nested/a.json", "a")
    store.write_text(ArtifactKind.METRICS, "b.json", "b")

    all_paths = [(item.kind, item.relative_path) for item in store.list_artifacts()]
    metric_paths = [item.relative_path for item in store.list_artifacts(ArtifactKind.METRICS)]

    assert all_paths == [
        (ArtifactKind.METRICS, "b.json"),
        (ArtifactKind.METRICS, "nested/a.json"),
        (ArtifactKind.REPORTS, "z.html"),
    ]
    assert metric_paths == ["b.json", "nested/a.json"]


def test_missing_artifact_returns_safe_error(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "run")

    with pytest.raises(ArtifactStoreError, match="does not exist"):
        store.read_bytes(ArtifactKind.REPORTS, "missing.html")


def test_root_must_be_a_directory(tmp_path: Path) -> None:
    root = tmp_path / "file"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ArtifactStoreError, match="must be a directory"):
        LocalArtifactStore(root)


def test_invalid_limits_fail_before_writes() -> None:
    with pytest.raises(ValueError, match="max_artifacts"):
        ArtifactLimits(max_artifacts=0)
    with pytest.raises(ValueError, match="max_file_bytes"):
        ArtifactLimits(max_file_bytes=0)
    with pytest.raises(ValueError, match="at least max_file_bytes"):
        ArtifactLimits(max_file_bytes=10, max_run_bytes=9)


def test_failed_atomic_replace_leaves_no_target_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalArtifactStore(tmp_path / "run")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("synthetic failure")

    monkeypatch.setattr("mask_api.research_runner.local_artifacts.os.replace", fail_replace)

    with pytest.raises(ArtifactStoreError, match="atomically"):
        store.write_bytes(ArtifactKind.RAW, "failed.bin", b"data")
    assert not (tmp_path / "run/raw/failed.bin").exists()
    assert list((tmp_path / "run/raw").glob(".mask-tmp-*")) == []
