"""Explicit, bounded local artifact adapter for CLI research runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from mask_api.research_runner.artifacts import (
    ArtifactConflict,
    ArtifactKind,
    ArtifactLimitExceeded,
    ArtifactLimits,
    ArtifactReceipt,
    ArtifactStoreError,
    UnsafeArtifactPath,
)

_SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class LocalArtifactStore:
    """Persist immutable run artifacts under an explicitly selected directory."""

    def __init__(self, root: Path, limits: ArtifactLimits | None = None) -> None:
        if root.exists() and not root.is_dir():
            raise ArtifactStoreError("artifact root must be a directory")
        try:
            root.mkdir(parents=True, exist_ok=True)
            self._root = root.resolve(strict=True)
        except OSError as error:
            raise ArtifactStoreError("artifact root could not be prepared") from error
        self._limits = limits or ArtifactLimits()

    @property
    def root(self) -> Path:
        return self._root

    def write_bytes(
        self, kind: ArtifactKind, relative_path: str, content: bytes
    ) -> ArtifactReceipt:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        if len(content) > self._limits.max_file_bytes:
            raise ArtifactLimitExceeded("artifact exceeds the per-file byte limit")
        target = self._target(kind, relative_path, create_parent=True)
        digest = hashlib.sha256(content).hexdigest()
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise UnsafeArtifactPath("artifact target is not a regular file")
            try:
                existing = target.read_bytes()
            except OSError as error:
                raise ArtifactStoreError("existing artifact could not be read") from error
            if existing != content:
                raise ArtifactConflict("immutable artifact already contains different content")
            return ArtifactReceipt(kind, relative_path, digest, len(content), already_present=True)

        count, total_bytes = self._usage()
        if count >= self._limits.max_artifacts:
            raise ArtifactLimitExceeded("artifact count limit reached")
        if total_bytes + len(content) > self._limits.max_run_bytes:
            raise ArtifactLimitExceeded("artifact run byte limit would be exceeded")

        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".mask-tmp-", dir=target.parent)
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
        except OSError as error:
            raise ArtifactStoreError("artifact could not be written atomically") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as error:
                    raise ArtifactStoreError("temporary artifact could not be removed") from error
        return ArtifactReceipt(kind, relative_path, digest, len(content))

    def write_text(self, kind: ArtifactKind, relative_path: str, content: str) -> ArtifactReceipt:
        return self.write_bytes(kind, relative_path, content.encode("utf-8"))

    def write_json(
        self,
        kind: ArtifactKind,
        relative_path: str,
        content: Mapping[str, object] | Sequence[object],
    ) -> ArtifactReceipt:
        try:
            rendered = json.dumps(
                content,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                separators=(",", ": "),
            )
        except (TypeError, ValueError) as error:
            raise ArtifactStoreError("artifact JSON content is not serializable") from error
        return self.write_text(kind, relative_path, rendered + "\n")

    def read_bytes(self, kind: ArtifactKind, relative_path: str) -> bytes:
        target = self._target(kind, relative_path)
        if not target.exists() or not target.is_file() or target.is_symlink():
            raise ArtifactStoreError("artifact does not exist")
        try:
            return target.read_bytes()
        except OSError as error:
            raise ArtifactStoreError("artifact could not be read") from error

    def list_artifacts(self, kind: ArtifactKind | None = None) -> tuple[ArtifactReceipt, ...]:
        kinds = (kind,) if kind is not None else tuple(ArtifactKind)
        receipts: list[ArtifactReceipt] = []
        for selected in kinds:
            directory = self._root / selected.value
            if not directory.exists():
                continue
            self._require_inside_root(directory)
            try:
                for path in directory.rglob("*"):
                    if path.is_symlink():
                        raise UnsafeArtifactPath("artifact tree contains a symbolic link")
                    if not path.is_file() or path.name.startswith(".mask-tmp-"):
                        continue
                    self._require_inside_root(path)
                    content = path.read_bytes()
                    relative = path.relative_to(directory).as_posix()
                    receipts.append(
                        ArtifactReceipt(
                            kind=selected,
                            relative_path=relative,
                            sha256=hashlib.sha256(content).hexdigest(),
                            size_bytes=len(content),
                            already_present=True,
                        )
                    )
            except OSError as error:
                raise ArtifactStoreError("artifact tree could not be inspected") from error
        return tuple(sorted(receipts, key=lambda item: (item.kind.value, item.relative_path)))

    def _target(
        self, kind: ArtifactKind, relative_path: str, *, create_parent: bool = False
    ) -> Path:
        if "\\" in relative_path or "\x00" in relative_path or ":" in relative_path:
            raise UnsafeArtifactPath("artifact path is not a safe relative POSIX path")
        candidate = PurePosixPath(relative_path)
        if candidate.is_absolute() or not candidate.parts:
            raise UnsafeArtifactPath("artifact path must be relative")
        for part in candidate.parts:
            stem = part.split(".", maxsplit=1)[0].upper()
            if (
                part in {".", ".."}
                or part.endswith(".")
                or not _SAFE_PART.fullmatch(part)
                or stem in _WINDOWS_RESERVED
            ):
                raise UnsafeArtifactPath("artifact path contains an unsafe component")
        parent = self._root / kind.value / Path(*candidate.parts[:-1])
        if create_parent:
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise ArtifactStoreError("artifact directory could not be prepared") from error
        self._require_inside_root(parent)
        target = parent / candidate.name
        self._require_inside_root(target)
        return target

    def _require_inside_root(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._root)
        except (OSError, ValueError) as error:
            raise UnsafeArtifactPath("artifact path escapes the selected run directory") from error

    def _usage(self) -> tuple[int, int]:
        artifacts = self.list_artifacts()
        return len(artifacts), sum(item.size_bytes for item in artifacts)
