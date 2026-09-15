"""Shared multi-key Gemini rotation helper for the one-off extraction
driver scripts (scripts/extract_m2_*, extract_m3_*, extract_m5_*, and
future ones).

The owner has supplied several separate real Gemini API keys
(MASK_gemini_API_KEY plus MASK_gemini_API_KEY_fallback_1..4), each on its
own free-tier daily quota (verified live: 500 real
generate_content_free_tier_requests/day per key/model -- see
AUTONOMOUS-042/045). A single real extraction pass can exceed that on
its own (M2's real 600-comment run did). Rather than stopping the whole
run or burning real, wasted retries against a key that is provably
exhausted for the day, this helper rotates to the next real key the
moment one reports gemini.http_429 -- a different key is a different
quota bucket, so switching is immediate and free, unlike the same-key
backoff retry (_analyze_with_retry-style) that earlier scripts used for
transient errors.

This module is intentionally NOT part of apps/api/src: it is scripting
convenience for these one-off driver scripts, not tested, shared
application code. Extraction correctness (grounding, evidence-span
verification, deterministic scoring) is entirely unchanged -- this only
changes which real credential sends the request.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mask_api.modules.analysis.contracts import AnalysisRequest, AnalysisResult
from mask_api.modules.analysis.gemini import (
    GeminiAdapter,
    GeminiError,
    GeminiSettings,
    UrllibGeminiTransport,
)
from mask_api.modules.analysis.ports import AnalysisCache
from mask_api.research_runner.budgets import BudgetLedger
from pydantic import SecretStr

_FALLBACK_KEY_ENV_NAMES = (
    "MASK_gemini_API_KEY",
    "MASK_gemini_API_KEY_fallback_1",
    "MASK_gemini_API_KEY_fallback_2",
    "MASK_gemini_API_KEY_fallback_3",
    "MASK_gemini_API_KEY_fallback_4",
)


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def real_configured_gemini_keys() -> tuple[str, ...]:
    """Every real, non-empty Gemini API key configured in the environment,
    in the order they should be tried. Never logs or returns which
    specific env var name backed a given value -- callers must not print
    these strings."""
    keys = []
    for name in _FALLBACK_KEY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            keys.append(value)
    return tuple(keys)


class MultiKeyGeminiClient:
    """Rotates across every real configured Gemini key on quota exhaustion.

    Each key gets its own GeminiAdapter (so each has its own real API
    identity) but they share one BudgetLedger and one AnalysisCache: the
    ledger tracks this run's own total real call volume regardless of
    which key served a given call, and the cache is keyed by request
    content, not by key, so a result already obtained through one key is
    correctly reused rather than re-fetched through another.
    """

    def __init__(
        self,
        api_keys: tuple[str, ...],
        cache: AnalysisCache,
        *,
        timeout_seconds: float = 30.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not api_keys:
            raise ValueError("at least one real Gemini API key is required")
        self._adapters = tuple(
            GeminiAdapter(
                GeminiSettings(
                    enabled=True,
                    policy_approved=True,
                    api_key=SecretStr(key),
                    timeout_seconds=timeout_seconds,
                ),
                UrllibGeminiTransport(),
                cache,
                now=now or (lambda: datetime.now(UTC)),
            )
            for key in api_keys
        )
        self._key_index = 0
        self.key_switch_count = 0
        self.exhausted_key_count = 0

    def analyze(self, request: AnalysisRequest, ledger: BudgetLedger) -> AnalysisResult:
        """Try the current key; on gemini.http_429 (quota exhaustion),
        immediately advance to the next real key rather than waiting --
        a different key is a different quota bucket. Any other retryable
        error (network/5xx) gets one same-key backoff retry sequence
        before also advancing, since it might not be quota-related.
        Raises the last real GeminiError once every configured key has
        been tried and failed."""
        last_error: GeminiError | None = None
        attempts_on_current_key = 0
        while self._key_index < len(self._adapters):
            adapter = self._adapters[self._key_index]
            try:
                return adapter.analyze(request, ledger)
            except GeminiError as error:
                last_error = error
                if error.code == "gemini.http_429":
                    self.exhausted_key_count += 1
                    self._key_index += 1
                    self.key_switch_count += 1
                    attempts_on_current_key = 0
                    continue
                if error.retryable and attempts_on_current_key < 3:
                    attempts_on_current_key += 1
                    time.sleep(10.0 * attempts_on_current_key)
                    continue
                self._key_index += 1
                self.key_switch_count += 1
                attempts_on_current_key = 0
        assert last_error is not None
        raise last_error
