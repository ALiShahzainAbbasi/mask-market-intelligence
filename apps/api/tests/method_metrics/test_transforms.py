from __future__ import annotations

from decimal import Decimal

import pytest
from mask_api.modules.method_metrics.transforms import (
    TransformError,
    apply_transform,
    composite_weighted_linear,
    weighted_coverage_score,
    weighted_mean_sqrt_score,
)
from mask_api.research_runner.contracts import TransformConfiguration, TransformKind


def transform(kind: TransformKind, **kwargs: object) -> TransformConfiguration:
    return TransformConfiguration(kind=kind, **kwargs)  # type: ignore[arg-type]


def test_linear_clamps_at_bounds() -> None:
    config = transform(TransformKind.LINEAR, low=Decimal("0.30"), high=Decimal("0.90"))
    assert apply_transform(Decimal("0.30"), config) == Decimal("0")
    assert apply_transform(Decimal("0.90"), config) == Decimal("10")
    assert apply_transform(Decimal("0.10"), config) == Decimal("0")
    assert apply_transform(Decimal("1.00"), config) == Decimal("10")
    assert apply_transform(Decimal("0.60"), config) == Decimal("5")


def test_reverse_linear_inverts_and_clamps() -> None:
    config = transform(TransformKind.REVERSE_LINEAR, low=Decimal("30"), high=Decimal("180"))
    assert apply_transform(Decimal("30"), config) == Decimal("10")
    assert apply_transform(Decimal("180"), config) == Decimal("0")
    assert apply_transform(Decimal("0"), config) == Decimal("10")
    assert apply_transform(Decimal("300"), config) == Decimal("0")
    assert apply_transform(Decimal("105"), config) == Decimal("5")


def test_log_scale_floors_zero_and_negative_values_instead_of_raising() -> None:
    config = transform(TransformKind.LOG_SCALE, low=Decimal("500"), high=Decimal("100000"))
    assert apply_transform(Decimal("0"), config) == Decimal("0")
    assert apply_transform(Decimal("-5"), config) == Decimal("0")
    assert apply_transform(Decimal("500"), config) == Decimal("0")
    assert apply_transform(Decimal("100000"), config) == Decimal("10")


def test_multiply_scales_and_clamps() -> None:
    config = transform(TransformKind.MULTIPLY, multiplier=Decimal("2.5"))
    assert apply_transform(Decimal("4"), config) == Decimal("10.0")
    assert apply_transform(Decimal("0"), config) == Decimal("0")
    assert apply_transform(Decimal("5"), config) == Decimal("10")  # clamped above domain


def test_complement_inverts_against_the_multiplier_ceiling() -> None:
    config = transform(TransformKind.COMPLEMENT, multiplier=Decimal("10"))
    assert apply_transform(Decimal("0"), config) == Decimal("10")
    assert apply_transform(Decimal("10"), config) == Decimal("0")
    assert apply_transform(Decimal("1"), config) == Decimal("9")
    assert apply_transform(Decimal("20"), config) == Decimal("0")  # clamped below domain


def test_missing_bounds_raise_explicitly() -> None:
    config = TransformConfiguration.model_construct(kind=TransformKind.LINEAR, low=None, high=None)
    with pytest.raises(TransformError):
        apply_transform(Decimal("1"), config)


def test_weighted_mean_sqrt_score_picks_top_n_and_weights_by_sqrt_evidence() -> None:
    scores = (
        (Decimal("9"), 4),
        (Decimal("8"), 9),
        (Decimal("7"), 1),
        (Decimal("6"), 1),
        (Decimal("5"), 1),
        (Decimal("1"), 100),  # excluded: ranked 6th by score, sqrt weighting cannot rescue it
    )
    result = weighted_mean_sqrt_score(scores, top_n=5)
    expected_weights = (
        Decimal(4).sqrt(),
        Decimal(9).sqrt(),
        Decimal(1).sqrt(),
        Decimal(1).sqrt(),
        Decimal(1).sqrt(),
    )
    expected_numerator = sum(
        (score * weight for (score, _), weight in zip(scores[:5], expected_weights, strict=True)),
        Decimal("0"),
    )
    expected = expected_numerator / sum(expected_weights, Decimal("0"))
    assert result == expected


def test_weighted_mean_sqrt_score_is_none_for_no_values() -> None:
    assert weighted_mean_sqrt_score((), top_n=5) is None


def test_weighted_mean_sqrt_score_rejects_nonpositive_evidence_count() -> None:
    with pytest.raises(TransformError):
        weighted_mean_sqrt_score(((Decimal("5"), 0),), top_n=5)


def test_composite_weighted_linear_matches_m7_meta_fit_expression() -> None:
    score = composite_weighted_linear(
        (
            (Decimal("10"), Decimal("0.50"), Decimal("0"), Decimal("10")),
            (Decimal("0.60"), Decimal("0.50"), Decimal("0.10"), Decimal("0.60")),
        )
    )
    assert score == Decimal("10")
    score_zero = composite_weighted_linear(
        (
            (Decimal("0"), Decimal("0.50"), Decimal("0"), Decimal("10")),
            (Decimal("0.10"), Decimal("0.50"), Decimal("0.10"), Decimal("0.60")),
        )
    )
    assert score_zero == Decimal("0")


def test_composite_weighted_linear_rejects_weights_not_totalling_one() -> None:
    with pytest.raises(TransformError):
        composite_weighted_linear(((Decimal("1"), Decimal("0.40"), Decimal("0"), Decimal("1")),))


def test_weighted_coverage_score_matches_the_m9_audit_expression() -> None:
    # 10*(1*1 + 1*1 + 2*0)/4, matching a partially-covered three-capability registry.
    score = weighted_coverage_score(
        (
            (Decimal(1), Decimal("1")),
            (Decimal(1), Decimal("1")),
            (Decimal(0), Decimal("2")),
        )
    )
    assert score == Decimal("5")


def test_weighted_coverage_score_full_coverage_is_ten() -> None:
    score = weighted_coverage_score(((Decimal(1), Decimal("1")), (Decimal(1), Decimal("2"))))
    assert score == Decimal("10")


def test_weighted_coverage_score_is_none_for_no_requirements() -> None:
    assert weighted_coverage_score(()) is None
