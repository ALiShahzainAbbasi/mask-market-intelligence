"""Low-cost deterministic keyword intent classification."""

from __future__ import annotations

import re

from mask_api.modules.search_intent.contracts import KeywordIntent

KEYWORD_INTENT_TAXONOMY_VERSION = "keyword-intent-v1"

_INTENT_PATTERNS: tuple[tuple[KeywordIntent, tuple[re.Pattern[str], ...]], ...] = (
    (
        KeywordIntent.COMPETITOR_SWITCHING,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"\balternatives?\s+to\b",
                r"\breplacements?\s+for\b",
                r"\bswitch(?:ing)?\s+from\b",
                r"\bmigrate\s+from\b",
            )
        ),
    ),
    (
        KeywordIntent.COMPARISON,
        tuple(re.compile(pattern) for pattern in (r"\bversus\b", r"\bvs\.?\b")),
    ),
    (
        KeywordIntent.TRANSACTIONAL,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"\bbuy\b",
                r"\bbook\b",
                r"\bget\s+(?:a\s+)?quote\b",
                r"\bfree\s+trial\b",
                r"\brequest\s+(?:a\s+)?demo\b",
                r"\bsign\s*up\b",
            )
        ),
    ),
    (
        KeywordIntent.COMMERCIAL,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"\bbest\b",
                r"\bpricing\b",
                r"\bprice\b",
                r"\bcost\b",
                r"\breviews?\b",
                r"\bcomparison\b",
                r"\btop\b",
            )
        ),
    ),
    (
        KeywordIntent.SOLUTION,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"\bsoftware\b",
                r"\bplatform\b",
                r"\btools?\b",
                r"\bautomation\b",
            )
        ),
    ),
    (
        KeywordIntent.PROBLEM,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"\bhow\s+to\s+(?:fix|reduce|prevent|stop|solve|improve)\b",
                r"\bproblems?\b",
                r"\bchallenges?\b",
                r"\bmanual\s+process\b",
                r"\bslow\b",
                r"\bdelays?\b",
                r"\berrors?\b",
            )
        ),
    ),
    (
        KeywordIntent.INFORMATIONAL,
        tuple(
            re.compile(pattern)
            for pattern in (
                r"^what\s+(?:is|are)\b",
                r"^how\s+(?:does|do|is|are)\b",
                r"\bguide\b",
                r"\btutorial\b",
                r"\bexamples?\b",
                r"\bdefinition\b",
            )
        ),
    ),
)


def classify_keyword_intent(keyword: str) -> KeywordIntent:
    """Classify explicit lexical intent; ambiguous terms remain UNKNOWN."""

    normalized = " ".join(keyword.casefold().split())
    if not normalized:
        return KeywordIntent.UNKNOWN
    for intent, patterns in _INTENT_PATTERNS:
        if any(pattern.search(normalized) for pattern in patterns):
            return intent
    return KeywordIntent.UNKNOWN
