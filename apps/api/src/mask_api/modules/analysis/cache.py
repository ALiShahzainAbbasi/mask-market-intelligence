"""Immutable local analysis cache behind the provider-neutral cache port."""

from __future__ import annotations

from pydantic import ValidationError

from mask_api.modules.analysis.contracts import (
    AnalysisCacheRecord,
    AnalysisRequest,
    AnalysisResult,
    AnalysisStatus,
)
from mask_api.research_runner.artifacts import ArtifactKind, ArtifactStoreError
from mask_api.research_runner.ports import ArtifactStore


class AnalysisCacheError(RuntimeError):
    """A completed analysis cache record was invalid or unavailable."""


class ArtifactAnalysisCache:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self._artifacts = artifacts

    def get(self, request: AnalysisRequest) -> AnalysisResult | None:
        prefix = f"analysis/{request.cache_key[:24]}/"
        records: list[AnalysisCacheRecord] = []
        try:
            for receipt in self._artifacts.list_artifacts(ArtifactKind.CACHE):
                if not receipt.relative_path.startswith(prefix):
                    continue
                payload = self._artifacts.read_bytes(ArtifactKind.CACHE, receipt.relative_path)
                record = AnalysisCacheRecord.model_validate_json(payload)
                if record.request.cache_key != request.cache_key:
                    raise AnalysisCacheError("analysis cache key does not match its path")
                records.append(record)
        except (ArtifactStoreError, ValidationError, ValueError) as error:
            raise AnalysisCacheError("analysis cache could not be read") from error
        if not records:
            return None
        return max(records, key=lambda record: record.result.created_at).result

    def put(self, request: AnalysisRequest, result: AnalysisResult) -> None:
        if result.status != AnalysisStatus.COMPLETED:
            raise AnalysisCacheError("only completed validated analysis can be cached")
        record = AnalysisCacheRecord(request=request, result=result)
        relative_path = f"analysis/{request.cache_key[:24]}/{result.response_sha256[:24]}.json"
        try:
            self._artifacts.write_bytes(
                ArtifactKind.CACHE,
                relative_path,
                record.model_dump_json(indent=2, exclude_computed_fields=True).encode("utf-8")
                + b"\n",
            )
        except ArtifactStoreError as error:
            raise AnalysisCacheError("analysis cache could not be written") from error
