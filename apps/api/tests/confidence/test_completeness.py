from __future__ import annotations

import pytest
from mask_api.modules.confidence.completeness import (
    CompletenessClassificationError,
    classify_completeness,
)
from mask_api.modules.confidence.contracts import MethodCompletenessState


def test_complete_status_is_proven() -> None:
    assert classify_completeness("complete") == MethodCompletenessState.PROVEN


def test_provisional_status_is_weak() -> None:
    assert classify_completeness("provisional") == MethodCompletenessState.WEAK


def test_unknown_status_is_missing() -> None:
    assert classify_completeness("unknown") == MethodCompletenessState.MISSING


def test_not_applicable_overrides_any_status() -> None:
    assert (
        classify_completeness("unknown", not_applicable=True)
        == MethodCompletenessState.NOT_APPLICABLE
    )
    assert (
        classify_completeness("complete", not_applicable=True)
        == MethodCompletenessState.NOT_APPLICABLE
    )


def test_unrecognized_status_raises() -> None:
    with pytest.raises(CompletenessClassificationError):
        classify_completeness("bogus")
