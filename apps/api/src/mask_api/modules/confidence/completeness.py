"""Deterministic evidence-completeness classification (SCORING.md section 7)."""

from __future__ import annotations

from mask_api.modules.confidence.contracts import MethodCompletenessState

_STATUS_TO_COMPLETENESS = {
    "complete": MethodCompletenessState.PROVEN,
    "provisional": MethodCompletenessState.WEAK,
    "unknown": MethodCompletenessState.MISSING,
}


class CompletenessClassificationError(ValueError):
    """A method status does not map to an approved completeness state."""


def classify_completeness(
    status: str,
    *,
    not_applicable: bool = False,
) -> MethodCompletenessState:
    """Map one method's computed status to Proven/Weak/Missing/Not applicable.

    `not_applicable` is for a method a rubric explicitly excuses for this
    market/gate (for example M8/M10 with validation disabled); it overrides
    the status, matching SCORING.md's "permitted only when the rubric
    explicitly allows it and a reviewer approves the reason."
    """
    if not_applicable:
        return MethodCompletenessState.NOT_APPLICABLE
    try:
        return _STATUS_TO_COMPLETENESS[status]
    except KeyError as error:
        raise CompletenessClassificationError(f"unrecognized method status: {status!r}") from error
