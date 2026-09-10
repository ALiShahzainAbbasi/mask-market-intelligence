"""Deterministic v1 confidence aggregation and sample-adequacy scoring."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.confidence.contracts import (
    ConfidenceDimensions,
    ConfidenceLabel,
    ConfidenceResult,
)
from mask_api.modules.scoring.math import TEN, ZERO, ratio_score
from mask_api.research_runner.contracts import ConfidenceConfiguration, MethodId

_DIMENSION_WEIGHT_KEYS = (
    "source_diversity",
    "sample_adequacy",
    "evidence_quality",
    "recency",
    "cross_source_agreement",
)


class ConfidenceCalculationError(ValueError):
    """Inputs do not satisfy the approved v1 confidence calculation contract."""


def calculate_confidence(
    formula: ConfidenceConfiguration,
    dimensions: ConfidenceDimensions,
) -> ConfidenceResult:
    """Aggregate five already-normalized 0-10 dimensions into the v1 result.

    Any missing dimension keeps the whole result UNKNOWN; this function never
    substitutes a default or partial/renormalized weighting.
    """
    _validate_formula(formula)
    values: dict[str, Decimal | None] = {
        "source_diversity": dimensions.source_diversity_0_10,
        "sample_adequacy": dimensions.sample_adequacy_0_10,
        "evidence_quality": dimensions.evidence_quality_0_10,
        "recency": dimensions.recency_0_10,
        "cross_source_agreement": dimensions.cross_source_agreement_0_10,
    }
    missing = tuple(
        f"confidence.{name}_missing" for name in _DIMENSION_WEIGHT_KEYS if values[name] is None
    )
    if missing:
        return ConfidenceResult(unknown_reasons=missing)

    weighted_sum = sum(
        (values[name] * formula.weights[name] for name in _DIMENSION_WEIGHT_KEYS),  # type: ignore[operator]
        ZERO,
    )
    numeric_confidence = _clamp_100(weighted_sum * TEN)
    if numeric_confidence < formula.low_below:
        label = ConfidenceLabel.LOW
    elif numeric_confidence >= formula.high_at_least:
        label = ConfidenceLabel.HIGH
    else:
        label = ConfidenceLabel.MEDIUM
    return ConfidenceResult(numeric_confidence=numeric_confidence, label=label)


def sample_adequacy_score(
    formula: ConfidenceConfiguration,
    method_id: MethodId,
    actual: Decimal | dict[str, Decimal] | None,
) -> Decimal | None:
    """10 * how close the actual sample is to its v1 `sample_targets` entry.

    Returns None (UNKNOWN) when the method has no approved sample target, or
    the actual count itself is unknown; never invents or defaults either.
    `full_target_any_of`-style multi-metric targets (currently only M10) use
    the best (highest) of the per-metric ratios, matching that sample rule's
    own "any of" semantics.
    """
    if actual is None:
        return None
    target = formula.sample_targets.get(method_id)
    if target is None:
        return None
    if isinstance(target, dict):
        if not isinstance(actual, dict):
            raise ConfidenceCalculationError(
                f"{method_id} sample target is multi-metric; actual must be a dict too"
            )
        ratios = tuple(ratio_score(actual.get(key, ZERO), value) for key, value in target.items())
        return max(ratios) if ratios else None
    if isinstance(actual, dict):
        raise ConfidenceCalculationError(
            f"{method_id} sample target is single-metric; actual cannot be a dict"
        )
    return ratio_score(actual, target)


def _clamp_100(value: Decimal) -> Decimal:
    return max(ZERO, min(Decimal(100), value))


def _validate_formula(formula: ConfidenceConfiguration) -> None:
    if set(formula.weights) != set(_DIMENSION_WEIGHT_KEYS):
        raise ConfidenceCalculationError("confidence formula dimensions do not match v1")
