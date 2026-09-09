"""Version-independent deterministic math; presentation rounding belongs elsewhere."""

from __future__ import annotations

from decimal import Decimal, localcontext

type DecimalInput = Decimal | int | str
UNKNOWN = None
ZERO = Decimal("0")
ONE = Decimal("1")
TEN = Decimal("10")


def _decimal(value: DecimalInput) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError("numeric inputs must be finite")
    return result


def _unit_interval(value: Decimal) -> Decimal:
    return max(ZERO, min(ONE, value))


def clamp10(value: DecimalInput) -> Decimal:
    """Clamp a numeric score to the inclusive 0-10 interval."""
    return max(ZERO, min(TEN, _decimal(value)))


def linear(value: DecimalInput, low: DecimalInput, high: DecimalInput) -> Decimal:
    """Map a raw value linearly to 0-10 using fixed inclusive boundaries."""
    raw, lower, upper = _decimal(value), _decimal(low), _decimal(high)
    if upper <= lower:
        raise ValueError("linear requires high > low")
    return TEN * _unit_interval((raw - lower) / (upper - lower))


def reverse_linear(value: DecimalInput, good: DecimalInput, bad: DecimalInput) -> Decimal:
    """Map a lower-is-better raw value to 0-10."""
    raw, lower, upper = _decimal(value), _decimal(good), _decimal(bad)
    if upper <= lower:
        raise ValueError("reverse_linear requires bad > good")
    return TEN * (ONE - _unit_interval((raw - lower) / (upper - lower)))


def log_scale(value: DecimalInput, low: DecimalInput, high: DecimalInput) -> Decimal:
    """Map a positive skewed value logarithmically to 0-10."""
    raw, lower, upper = _decimal(value), _decimal(low), _decimal(high)
    if lower <= ZERO or upper <= lower:
        raise ValueError("log_scale requires 0 < low < high")
    if raw <= ZERO:
        raise ValueError("log_scale requires value > 0")
    with localcontext() as context:
        context.prec = 28
        position = (raw.ln() - lower.ln()) / (upper.ln() - lower.ln())
    return TEN * _unit_interval(position)


def ratio_score(value: DecimalInput, target: DecimalInput) -> Decimal:
    """Map a ratio to 0-10 where reaching the positive target means 10."""
    raw, expected = _decimal(value), _decimal(target)
    if expected <= ZERO:
        raise ValueError("ratio_score requires target > 0")
    return TEN * _unit_interval(raw / expected)


def decay(days: DecimalInput, half_life: DecimalInput) -> Decimal:
    """Return the 0-10 exponential recency score for a non-negative age."""
    age, period = _decimal(days), _decimal(half_life)
    if age < ZERO or period <= ZERO:
        raise ValueError("decay requires days >= 0 and half_life > 0")
    with localcontext() as context:
        context.prec = 28
        factor = ((-age / period) * Decimal(2).ln()).exp()
    return TEN * factor


def weighted_mean(
    values: tuple[DecimalInput, ...],
    weights: tuple[DecimalInput, ...],
) -> Decimal | None:
    """Return UNKNOWN for no observations; otherwise require positive stored weights."""
    if len(values) != len(weights):
        raise ValueError("weighted_mean values and weights must have equal length")
    if not values:
        return UNKNOWN
    numeric_values = tuple(_decimal(value) for value in values)
    numeric_weights = tuple(_decimal(weight) for weight in weights)
    if any(weight <= ZERO for weight in numeric_weights):
        raise ValueError("weighted_mean weights must be positive")
    return sum(
        (value * weight for value, weight in zip(numeric_values, numeric_weights, strict=True)),
        ZERO,
    ) / sum(numeric_weights, ZERO)


def safe_rate(numerator: DecimalInput, denominator: DecimalInput) -> Decimal | None:
    """Return UNKNOWN when the denominator is zero or negative."""
    den = _decimal(denominator)
    return _decimal(numerator) / den if den > ZERO else UNKNOWN
