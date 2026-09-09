"""Shared deterministic transform dispatch for the v1 method-metric formulas.

Every function here consumes an already-normalized raw value (the "source-to-metric"
step owned by each method's calculator module) and returns a 0-10 score. No function
here fetches evidence, calls a network/model provider, or knows about a specific
method; that keeps source adapters and calculations separate per AGENTS.md.
"""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.method_metrics.contracts import ComponentBreakdown, ComponentStatus
from mask_api.modules.method_metrics.provenance import SourcedMetric
from mask_api.modules.scoring.math import (
    ZERO,
    clamp10,
    linear,
    log_scale,
    reverse_linear,
    weighted_mean,
)
from mask_api.research_runner.contracts import (
    FormulaComponent,
    TransformConfiguration,
    TransformKind,
)


class TransformError(ValueError):
    """A component transform received a value its configured kind cannot accept."""


def apply_transform(value: Decimal, transform: TransformConfiguration) -> Decimal:
    """Apply one FormulaComponent transform to an already-normalized raw value.

    log_scale's domain excludes zero and negative values; a raw value at or below
    that floor is scored 0 (the domain minimum) rather than raising, since a
    legitimately observed zero count/amount is not an invalid input.
    """
    kind = transform.kind
    if kind == TransformKind.LINEAR:
        _require_bounds(transform, kind)
        return linear(value, transform.low, transform.high)  # type: ignore[arg-type]
    if kind == TransformKind.REVERSE_LINEAR:
        _require_bounds(transform, kind)
        return reverse_linear(value, transform.low, transform.high)  # type: ignore[arg-type]
    if kind == TransformKind.LOG_SCALE:
        _require_bounds(transform, kind)
        if value <= ZERO:
            return ZERO
        return log_scale(value, transform.low, transform.high)  # type: ignore[arg-type]
    if kind == TransformKind.MULTIPLY:
        if transform.multiplier is None:
            raise TransformError("multiply transform requires a multiplier")
        return clamp10(value * transform.multiplier)
    if kind == TransformKind.COMPLEMENT:
        if transform.multiplier is None:
            raise TransformError("complement transform requires a multiplier")
        return clamp10(transform.multiplier - value)
    raise TransformError(f"{kind} is not a supported single-value transform")


def _require_bounds(transform: TransformConfiguration, kind: TransformKind) -> None:
    if transform.low is None or transform.high is None:
        raise TransformError(f"{kind} transform requires low/high bounds")


def weighted_mean_sqrt_score(
    scores_and_counts: tuple[tuple[Decimal, int], ...],
    *,
    top_n: int,
) -> Decimal | None:
    """Weighted mean of the top-N scores by sqrt(evidence_count), per a v1 audit expression."""
    if not scores_and_counts:
        return None
    if any(count <= 0 for _, count in scores_and_counts):
        raise TransformError("weighted_mean_sqrt requires a positive evidence count per score")
    ranked = tuple(sorted(scores_and_counts, key=lambda item: (-item[0], -item[1])))
    top = ranked[:top_n]
    scores = tuple(score for score, _ in top)
    weights = tuple(Decimal(count).sqrt() for _, count in top)
    mean = weighted_mean(scores, weights)
    if mean is None:
        raise TransformError("weighted_mean_sqrt unexpectedly had no values")
    return clamp10(mean)


def composite_weighted_linear(
    parts: tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...],
) -> Decimal:
    """Weighted sum of independent linear sub-transforms, per a composite audit expression.

    Each part is (value, weight, low, high); weights must total exactly 1.
    """
    if not parts:
        raise TransformError("composite transform requires at least one part")
    total_weight = sum((weight for _, weight, _, _ in parts), ZERO)
    if total_weight != Decimal("1"):
        raise TransformError("composite transform weights must total exactly 1")
    return clamp10(
        sum(
            (weight * linear(value, low, high) for value, weight, low, high in parts),
            ZERO,
        )
    )


def simple_component_breakdown(
    component: str,
    metric: SourcedMetric | None,
    definition: FormulaComponent,
    *,
    missing_reason: str,
) -> ComponentBreakdown:
    """Build a breakdown entry from one directly-transformed SourcedMetric, or MISSING."""
    if metric is None:
        return ComponentBreakdown(
            component=component,
            status=ComponentStatus.MISSING,
            weight=definition.weight,
            reason=missing_reason,
        )
    score = apply_transform(metric.value, definition.transform)
    return ComponentBreakdown(
        component=component,
        status=ComponentStatus.AVAILABLE,
        raw_value=metric.value,
        transformed_score=score,
        weight=definition.weight,
        weighted_contribution=score * definition.weight,
        evidence_references=(metric.provenance.evidence_reference,),
    )
