"""Deterministic automated research score and cross-method confidence."""

from __future__ import annotations

from decimal import Decimal

from mask_api.modules.confidence import clamp_100, label_for_confidence
from mask_api.modules.confidence.contracts import ConfidenceResult, MethodStatusSnapshot
from mask_api.modules.scoring.math import ZERO, clamp10
from mask_api.research_runner.contracts import ConfidenceConfiguration, MethodId

_RISK_BASE_WEIGHT = Decimal("0.70")
_RISK_CONFIDENCE_WEIGHT = Decimal("0.30")
_RISK_CONFIDENCE_SCALE = Decimal("100")


class MarketScoringError(ValueError):
    """Inputs do not satisfy the approved v1 market-scoring contract."""


def calculate_automated_research_score(
    overall_weights: dict[MethodId, Decimal],
    methods: dict[MethodId, MethodStatusSnapshot],
) -> tuple[Decimal | None, Decimal, tuple[MethodId, ...], tuple[MethodId, ...]]:
    """The raw (never renormalized) weighted sum of available method scores.

    Returns (score, observed_weight, contributing_methods, missing_methods).
    `score` is None only when no method has contributed anything yet.
    """
    if set(overall_weights) != set(MethodId):
        raise MarketScoringError("overall weights do not cover M1-M10")
    contributing = tuple(
        method for method in MethodId if method in methods and methods[method].score is not None
    )
    missing = tuple(method for method in MethodId if method not in contributing)
    observed_weight = sum((overall_weights[method] for method in contributing), ZERO)
    if not contributing:
        return None, observed_weight, contributing, missing
    weighted_sum = sum(
        (methods[method].score * overall_weights[method] for method in contributing),  # type: ignore[operator]
        ZERO,
    )
    return clamp10(weighted_sum), observed_weight, contributing, missing


def aggregate_confidence(
    *,
    confidence_config: ConfidenceConfiguration,
    overall_weights: dict[MethodId, Decimal],
    required_methods: tuple[MethodId, ...],
    methods: dict[MethodId, MethodStatusSnapshot],
) -> ConfidenceResult:
    """Weighted-mean confidence across `required_methods`, renormalized across them.

    SCORING.md section 6: "For a complete gate profile, calculate the
    weighted mean of required methods' numeric confidence using the approved
    overall method weights renormalized across that fixed gate profile. This
    renormalization is allowed only for confidence aggregation, not to
    conceal a missing score. Every required method must have confidence;
    otherwise gate confidence is unavailable." The same rule computes the
    full ten-method overall confidence when `required_methods` is every
    MethodId.
    """
    if not required_methods:
        raise MarketScoringError("confidence aggregation requires at least one method")
    if any(method not in overall_weights for method in required_methods):
        raise MarketScoringError("required methods must each have an approved overall weight")

    total_weight = sum((overall_weights[method] for method in required_methods), ZERO)
    if total_weight <= ZERO:
        raise MarketScoringError("required methods must have positive total weight")

    missing = tuple(
        method
        for method in required_methods
        if method not in methods
        or methods[method].confidence is None
        or methods[method].confidence.numeric_confidence is None  # type: ignore[union-attr]
    )
    if missing:
        return ConfidenceResult(
            unknown_reasons=tuple(f"confidence.{method.value}_missing" for method in missing)
        )

    weighted_sum = sum(
        (
            methods[method].confidence.numeric_confidence * overall_weights[method]  # type: ignore[union-attr,operator]
            for method in required_methods
        ),
        ZERO,
    )
    numeric_confidence = clamp_100(weighted_sum / total_weight)
    return ConfidenceResult(
        numeric_confidence=numeric_confidence,
        label=label_for_confidence(numeric_confidence, confidence_config),
    )


def risk_adjusted_method_score(
    raw_score: Decimal | None,
    confidence: ConfidenceResult | None,
) -> Decimal | None:
    """RawMethodScore x (0.70 + 0.30 x Confidence/100); a secondary decision metric.

    Never replaces the raw score: this exists only for report display. It is
    UNKNOWN whenever either input is UNKNOWN -- an unavailable confidence
    normalizer must never be treated as a confidence of zero (that would
    silently punish the raw score for missing data neither approved nor
    invented here).
    """
    if raw_score is None or confidence is None or confidence.numeric_confidence is None:
        return None
    confidence_fraction = confidence.numeric_confidence / _RISK_CONFIDENCE_SCALE
    return clamp10(raw_score * (_RISK_BASE_WEIGHT + _RISK_CONFIDENCE_WEIGHT * confidence_fraction))
