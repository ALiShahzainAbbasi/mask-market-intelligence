from collections.abc import Callable
from decimal import Decimal

import pytest
from mask_api.modules.scoring.math import (
    clamp10,
    decay,
    linear,
    log_scale,
    ratio_score,
    reverse_linear,
    safe_rate,
    weighted_mean,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-1", Decimal("0")),
        ("4.25", Decimal("4.25")),
        ("11", Decimal("10")),
    ],
)
def test_clamp10(value: str, expected: Decimal) -> None:
    assert clamp10(value) == expected


def test_linear_clamps_and_maps_midpoint() -> None:
    assert linear("-5", "0", "20") == Decimal("0")
    assert linear("10", "0", "20") == Decimal("5")
    assert linear("25", "0", "20") == Decimal("10")


def test_reverse_linear_clamps_and_maps_midpoint() -> None:
    assert reverse_linear("10", "30", "180") == Decimal("10")
    assert reverse_linear("105", "30", "180") == Decimal("5")
    assert reverse_linear("200", "30", "180") == Decimal("0")


def test_log_scale_uses_geometric_midpoint() -> None:
    assert log_scale("1", "1", "100") == Decimal("0")
    assert abs(log_scale("10", "1", "100") - Decimal("5")) < Decimal("1e-26")
    assert log_scale("1000", "1", "100") == Decimal("10")


def test_ratio_score_clamps_to_target() -> None:
    assert ratio_score("0", "0.5") == Decimal("0")
    assert ratio_score("0.25", "0.5") == Decimal("5.0")
    assert ratio_score("1", "0.5") == Decimal("10")


def test_decay_reaches_half_score_at_half_life() -> None:
    assert decay("0", "30") == Decimal("10")
    assert abs(decay("30", "30") - Decimal("5")) < Decimal("1e-26")


def test_weighted_mean_and_unknown_empty_input() -> None:
    assert weighted_mean(("2", "8"), ("1", "3")) == Decimal("6.5")
    assert weighted_mean((), ()) is None


def test_safe_rate_keeps_zero_numerator_distinct_from_unknown() -> None:
    assert safe_rate("0", "5") == Decimal("0")
    assert safe_rate("4", "2") == Decimal("2")
    assert safe_rate("4", "0") is None
    assert safe_rate("4", "-1") is None


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: linear("1", "2", "2"), "linear requires high > low"),
        (lambda: reverse_linear("1", "2", "2"), "reverse_linear requires bad > good"),
        (lambda: log_scale("0", "1", "10"), "log_scale requires value > 0"),
        (lambda: log_scale("1", "0", "10"), "log_scale requires 0 < low < high"),
        (lambda: ratio_score("1", "0"), "ratio_score requires target > 0"),
        (lambda: decay("-1", "30"), "decay requires days >= 0"),
        (lambda: weighted_mean(("1",), ()), "equal length"),
        (lambda: weighted_mean(("1",), ("0",)), "weights must be positive"),
        (lambda: clamp10("NaN"), "numeric inputs must be finite"),
    ],
)
def test_invalid_math_inputs_fail_explicitly(
    call: Callable[[], Decimal | None], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        call()
