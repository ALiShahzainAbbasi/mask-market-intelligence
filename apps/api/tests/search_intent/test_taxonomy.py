from __future__ import annotations

import pytest
from mask_api.modules.search_intent.contracts import KeywordIntent
from mask_api.modules.search_intent.taxonomy import (
    KEYWORD_INTENT_TAXONOMY_VERSION,
    classify_keyword_intent,
)


@pytest.mark.parametrize(
    ("keyword", "expected"),
    [
        ("What is field service management", KeywordIntent.INFORMATIONAL),
        ("how to reduce dispatch delays", KeywordIntent.PROBLEM),
        ("field service automation", KeywordIntent.SOLUTION),
        ("best field service software pricing", KeywordIntent.COMMERCIAL),
        ("field service software vs spreadsheets", KeywordIntent.COMPARISON),
        ("request a demo field service software", KeywordIntent.TRANSACTIONAL),
        ("ServiceTitan alternatives to spreadsheets", KeywordIntent.COMPETITOR_SWITCHING),
        ("HVAC dispatch", KeywordIntent.UNKNOWN),
        ("   ", KeywordIntent.UNKNOWN),
    ],
)
def test_taxonomy_classifies_only_explicit_lexical_intent(
    keyword: str, expected: KeywordIntent
) -> None:
    assert classify_keyword_intent(keyword) == expected
    assert KEYWORD_INTENT_TAXONOMY_VERSION == "keyword-intent-v1"


def test_switching_pattern_has_deterministic_precedence() -> None:
    assert (
        classify_keyword_intent("best replacement for field service software")
        == KeywordIntent.COMPETITOR_SWITCHING
    )
