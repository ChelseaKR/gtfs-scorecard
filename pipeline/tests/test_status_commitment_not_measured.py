"""A liveness record with no failure streak must not be counted as clean.

``refresh_success_record`` read ``int(record.get("consecutive_failures") or 0)``.
A record that never carried the field, or carried null, or carried something
that is not a count, therefore read as a zero-failure record and was counted
healthy. That figure is the public uptime commitment on /status/ and in
``api/v1/status.json``: "Currently checking clean: N% of tracked feed records".

The record is what we know about a feed's liveness. A record that does not say
is not a record that says zero.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from scorecard_pipeline.metrics import UNREACHABLE_STREAK_CHECKS
from scorecard_pipeline.status_commitment import refresh_success_record

NOW = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC)
CHECKED = "2026-09-05T06:00:00+00:00"


def _record(failures: Any = 0, *, checked: bool = True) -> dict[str, Any]:
    rec: dict[str, Any] = {"url": "https://example.gov/gtfs.zip"}
    if failures is not ...:
        rec["consecutive_failures"] = failures
    if checked:
        rec["checked_at"] = CHECKED
    return rec


def test_a_record_with_no_failure_count_is_not_counted_clean() -> None:
    out = refresh_success_record({"a": _record(...)}, NOW)
    assert out["feeds_tracked"] == 1
    assert out["not_measured"] == 1
    assert out["healthy"] == 0
    assert out["degraded"] == 0
    assert out["unreachable"] == 0
    # No measured record, so there is no share to publish.
    assert out["currently_clean_pct"] is None
    assert out["success_rate_pct"] is None


def test_a_null_or_unusable_failure_count_is_also_unmeasured() -> None:
    for value in (None, "0", "many", 1.5, -1, True):
        out = refresh_success_record({"a": _record(value)}, NOW)
        assert out["not_measured"] == 1, value
        assert out["healthy"] == 0, value


def test_the_published_share_uses_the_records_that_actually_say() -> None:
    """One clean, one failing, one silent: the share is 1 of 2, not 2 of 3."""
    out = refresh_success_record(
        {"clean": _record(0), "failing": _record(1), "silent": _record(...)}, NOW
    )
    assert out["feeds_tracked"] == 3
    assert out["not_measured"] == 1
    assert (out["healthy"], out["degraded"], out["unreachable"]) == (1, 1, 0)
    assert out["currently_clean_pct"] == 50.0
    assert out["success_rate_pct"] == 50.0


def test_measured_records_are_unchanged() -> None:
    """The narrowness test: real counts still land in the same three buckets."""
    out = refresh_success_record(
        {
            "clean": _record(0),
            "degraded": _record(1),
            "gone": _record(UNREACHABLE_STREAK_CHECKS),
        },
        NOW,
    )
    assert out["not_measured"] == 0
    assert (out["healthy"], out["degraded"], out["unreachable"]) == (1, 1, 1)
    assert out["currently_clean_pct"] == 33.3
    assert out["hours_since_last_check"]["median"] == 6.0


def test_an_empty_state_still_publishes_no_share() -> None:
    out = refresh_success_record({}, NOW)
    assert out["feeds_tracked"] == 0
    assert out["not_measured"] == 0
    assert out["currently_clean_pct"] is None


# ------------------------------------------------------------- what /status/ says


def _doc(feeds: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from scorecard_pipeline.status_commitment import build_status_commitment

    return build_status_commitment(feeds, NOW, "https://example.test")


def test_the_status_page_states_the_denominator_it_actually_used() -> None:
    from scorecard_pipeline.render_site import _status_commitment_section

    all_measured = _status_commitment_section(_doc({"a": _record(0), "b": _record(1)}))
    assert "<strong>50.0%</strong> of tracked feed records" in all_measured
    assert "Not measured:" not in all_measured

    with_a_gap = _status_commitment_section(
        _doc({"a": _record(0), "b": _record(1), "c": _record(...)})
    )
    assert "<strong>50.0%</strong> of 2 feed records with a direct-check result" in with_a_gap
    assert "1</strong> feed record carry no direct-check result" in with_a_gap
    assert "rather than counted as clean" in with_a_gap


def test_the_status_page_says_so_when_nothing_is_measured() -> None:
    from scorecard_pipeline.render_site import _status_commitment_section

    html = _status_commitment_section(_doc({"a": _record(...)}))
    assert "no current clean share to report" in html
    assert "%</strong>" not in html.split("Flagged unreachable")[1]
