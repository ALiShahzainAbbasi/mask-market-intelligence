"""Shared source-grounded metric provenance for deterministic method calculators."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MethodMetricsValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ObservationState(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    INTERVIEW_CONFIRMED = "interview_confirmed"


class MetricProvenance(MethodMetricsValue):
    """Where one normalized scalar metric value came from; never invented."""

    source_id: str = Field(min_length=1, max_length=100)
    evidence_reference: str = Field(min_length=1, max_length=500)
    observation_state: ObservationState
    geography: str = Field(min_length=1, max_length=500)
    population: str = Field(min_length=1, max_length=200)
    period: str = Field(min_length=1, max_length=100)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unit: str = Field(min_length=1, max_length=100)


class SourcedMetric(MethodMetricsValue):
    """One explicitly available normalized source value and its provenance."""

    value: Decimal
    provenance: MetricProvenance

    @model_validator(mode="after")
    def finite_value(self) -> SourcedMetric:
        if not self.value.is_finite():
            raise ValueError("a sourced metric value must be finite")
        return self


class ProvenanceCompatibilityError(ValueError):
    """Two or more sourced metrics used in one calculation are not comparable."""


def require_shared_geography(metrics: tuple[SourcedMetric, ...]) -> None:
    """Reject components whose provenance disagrees about the target geography."""
    geographies = {metric.provenance.geography for metric in metrics}
    if len(geographies) > 1:
        raise ProvenanceCompatibilityError(
            f"incompatible geography across sourced metrics: {sorted(geographies)}"
        )


def require_shared_population(metrics: tuple[SourcedMetric, ...]) -> None:
    """Reject components whose provenance disagrees about the target population."""
    populations = {metric.provenance.population for metric in metrics}
    if len(populations) > 1:
        raise ProvenanceCompatibilityError(
            f"incompatible population definition across sourced metrics: {sorted(populations)}"
        )


def require_shared_currency(metrics: tuple[SourcedMetric, ...]) -> None:
    """Reject monetary components whose provenance disagrees about currency."""
    currencies = {metric.provenance.currency for metric in metrics if metric.provenance.currency}
    if len(currencies) > 1:
        raise ProvenanceCompatibilityError(
            f"incompatible currency across sourced metrics: {sorted(currencies)}"
        )


def require_shared_period(metrics: tuple[SourcedMetric, ...]) -> None:
    """Reject components whose provenance disagrees about the reporting period."""
    periods = {metric.provenance.period for metric in metrics}
    if len(periods) > 1:
        raise ProvenanceCompatibilityError(
            f"incompatible reporting period across sourced metrics: {sorted(periods)}"
        )


def canonical_sha256(model: BaseModel) -> str:
    """Stable hash of a model's validated value, independent of key order/whitespace."""
    serialized = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
