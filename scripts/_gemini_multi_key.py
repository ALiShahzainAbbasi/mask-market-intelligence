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
exhausted for the day, this helper rotates to the next real key once one
reports a real, sustained gemini.http_429.

It does not switch on the very first 429: Gemini's real API returns the
same HTTP 429 for a per-day quota cap AND a much shorter per-minute
burst limit, and GeminiError does not carry enough detail to tell them
apart. An early version switched immediately and, live, mis-marked keys
exhausted after nothing but a transient per-minute burst -- see
MultiKeyGeminiClient.analyze()'s docstring for the exact real failure
and the short-backoff-before-switching fix.

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
        """Try the current key.

        Gemini's real API returns the same HTTP 429 / gemini.http_429 for
        two genuinely different real conditions this project has both
        observed live: a per-day quota cap (RESOURCE_EXHAUSTED,
        "limit: 500 ... free_tier_requests", real and confirmed in
        AUTONOMOUS-042/045 -- does not clear until the next day) and a
        short per-minute burst limit (clears within roughly a minute).
        GeminiError does not carry the response body needed to tell them
        apart, so a 429 gets a short same-key backoff first (in case it
        is the per-minute kind) before this key is treated as exhausted
        for the day and this client switches to the next real key --
        verified necessary live: an earlier version that switched keys on
        the very first 429 mis-marked keys exhausted after nothing but a
        real per-minute burst, and then crashed once every key's index
        had incorrectly advanced past the end.

        Any OTHER retryable error (network/5xx) also gets the same same-
        key backoff retry sequence, since it is unrelated to quota and
        switching keys would not fix it. A non-retryable error (e.g. a
        malformed response to this specific request) is raised
        immediately without touching key_index: it says nothing about the
        key's remaining quota, only about this one request.

        self._key_index is not reset per call, so a key confirmed
        exhausted for the day stays skipped for later calls too. Raises
        GeminiError("gemini.all_keys_exhausted") once every configured
        key has been confirmed exhausted."""
        if self._key_index >= len(self._adapters):
            raise GeminiError("gemini.all_keys_exhausted")
        same_key_429_count = 0
        attempts_on_current_key = 0
        while self._key_index < len(self._adapters):
            adapter = self._adapters[self._key_index]
            try:
                result = adapter.analyze(request, ledger)
                same_key_429_count = 0
                return result
            except GeminiError as error:
                if error.code == "gemini.http_429":
                    same_key_429_count += 1
                    if same_key_429_count <= 2:
                        time.sleep(20.0 * same_key_429_count)
                        continue
                    self.exhausted_key_count += 1
                    self._key_index += 1
                    self.key_switch_count += 1
                    attempts_on_current_key = 0
                    same_key_429_count = 0
                    continue
                if error.retryable and attempts_on_current_key < 3:
                    attempts_on_current_key += 1
                    time.sleep(10.0 * attempts_on_current_key)
                    continue
                raise
        raise GeminiError("gemini.all_keys_exhausted")
