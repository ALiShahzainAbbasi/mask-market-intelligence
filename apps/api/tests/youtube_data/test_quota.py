from __future__ import annotations

import pytest
from mask_api.modules.youtube_data.contracts import YouTubeEndpoint
from mask_api.modules.youtube_data.quota import (
    YouTubeQuotaExceeded,
    YouTubeQuotaLedger,
    YouTubeQuotaLimits,
)


def test_consume_charges_the_exact_per_endpoint_cost() -> None:
    ledger = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=200))

    cost = ledger.consume(YouTubeEndpoint.SEARCH)

    assert cost == 100
    assert ledger.units_used == 100
    assert ledger.units_remaining == 100


def test_ensure_capacity_rejects_before_any_state_change() -> None:
    ledger = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=50))

    with pytest.raises(YouTubeQuotaExceeded):
        ledger.ensure_capacity(YouTubeEndpoint.SEARCH)

    assert ledger.units_used == 0


def test_consume_rejects_and_does_not_partially_charge_over_the_limit() -> None:
    ledger = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=99))

    with pytest.raises(YouTubeQuotaExceeded):
        ledger.consume(YouTubeEndpoint.SEARCH)

    assert ledger.units_used == 0


def test_cheap_comment_threads_calls_can_still_proceed_after_search_is_exhausted() -> None:
    ledger = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=100))
    ledger.consume(YouTubeEndpoint.SEARCH)

    with pytest.raises(YouTubeQuotaExceeded):
        ledger.consume(YouTubeEndpoint.SEARCH)
    assert ledger.units_used == 100

    limits_with_room = YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=101), units_used=100)
    cost = limits_with_room.consume(YouTubeEndpoint.COMMENT_THREADS)
    assert cost == 1


def test_negative_limit_or_starting_usage_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        YouTubeQuotaLimits(max_quota_units=-1)
    with pytest.raises(ValueError, match="negative"):
        YouTubeQuotaLedger(YouTubeQuotaLimits(max_quota_units=10), units_used=-1)
