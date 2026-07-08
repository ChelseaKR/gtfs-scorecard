"""Tests for behavioral lapse-risk scoring (EXP-13)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from scorecard_pipeline.lapse_risk import (
    MIN_HISTORY_ENTRIES,
    TIER_ELEVATED,
    TIER_HIGH,
    TIER_INSUFFICIENT_HISTORY,
    TIER_NONE,
    assess,
)

START = dt.date(2026, 6, 1)


def _history(days_series: Sequence[int | None]) -> list[dict[str, Any]]:
    """Build a history list from a series of days_until_expiry, one per day."""
    out = []
    for i, days in enumerate(days_series):
        entry: dict[str, Any] = {"date": (START + dt.timedelta(days=i)).isoformat()}
        if days is not None:
            entry["days_until_expiry"] = days
        out.append(entry)
    return out


def test_too_little_history_is_insufficient() -> None:
    history = _history(list(range(100, 100 - (MIN_HISTORY_ENTRIES - 1), -1)))
    risk = assess(history)
    assert risk.tier == TIER_INSUFFICIENT_HISTORY
    assert risk.observed_days == MIN_HISTORY_ENTRIES - 1
    assert risk.reasons and risk.reasons[0].code == "insufficient_history"


def test_malformed_entries_are_skipped_not_counted() -> None:
    history = _history(list(range(100, 100 - MIN_HISTORY_ENTRIES, -1)))
    history.append({"date": "not-a-date", "days_until_expiry": 5})
    history.append({"date": "2026-07-01"})  # missing days_until_expiry
    risk = assess(history)
    assert risk.observed_days == MIN_HISTORY_ENTRIES


def test_steady_decline_with_no_renewal_has_no_risk_signal() -> None:
    # 20 days of ordinary day-to-day decline, no jumps, never lapses.
    history = _history(list(range(100, 80, -1)))
    risk = assess(history)
    assert risk.tier == TIER_NONE
    assert risk.reasons == []


def test_late_renewal_and_recurring_lapse_flagged_high() -> None:
    # Two full lapse-and-late-renewal cycles inside the observed window.
    series: list[int] = [5, 4, 3, 2, 1, 0, -1, -2, 50]
    series += list(range(49, 44, -1))  # 49..45
    series += [5, 4, 3, 2, 1, 0, -1, -2, 60]
    series += list(range(59, 54, -1))  # 59..55
    history = _history(series)
    risk = assess(history)
    assert risk.tier == TIER_HIGH
    codes = {r.code for r in risk.reasons}
    assert "late_renewal_history" in codes
    assert "recurring_lapse" in codes


def test_slowing_renewal_cadence_flagged_without_ever_lapsing() -> None:
    # Three renewals, well before the window ever runs out, with a much wider
    # gap between the second and third renewal than between the first two.
    series: list[int] = [50, 49, 48]  # offsets 0-2
    series.append(200)  # offset 3: renewal 1 (gain well past the slack)
    series += [199, 198, 197, 196, 195, 194, 193]  # offsets 4-10
    series.append(400)  # offset 11: renewal 2 (gap from renewal 1 = 8 days)
    # offsets 12-50: steady decline for 39 days, staying well above zero.
    series += list(range(399, 399 - 39, -1))
    series.append(600)  # offset 51: renewal 3 (gap from renewal 2 = 40 days)
    history = _history(series)
    risk = assess(history)
    assert risk.tier == TIER_ELEVATED
    codes = {r.code for r in risk.reasons}
    assert codes == {"slowing_cadence"}


def test_reasons_are_dated_and_plain_language() -> None:
    series: list[int] = [5, 4, 3, 2, 1, 0, -1, -2, 50, 49, 48, 47]
    history = _history(series)
    risk = assess(history)
    assert risk.tier in (TIER_ELEVATED, TIER_HIGH)
    for reason in risk.reasons:
        assert reason.detail  # non-empty, human-readable
        assert reason.code
