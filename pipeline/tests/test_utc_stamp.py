"""utc_stamp: the reader-facing UTC timestamp, in American style."""

from __future__ import annotations

import datetime as dt

import pytest

from scorecard_pipeline.site_shell import utc_stamp


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (dt.datetime(2026, 11, 19, 13, 23, tzinfo=dt.UTC), "Nov 19, 2026, 1:23 PM UTC"),
        (dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.UTC), "Jul 8, 2026, 2:00 PM UTC"),
        # Midnight and noon are the two hours a 12-hour clock gets wrong.
        (dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC), "Jan 1, 2026, 12:05 AM UTC"),
        (dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.UTC), "Jul 10, 2026, 12:00 PM UTC"),
        (dt.datetime(2026, 12, 31, 23, 59), "Dec 31, 2026, 11:59 PM UTC"),
        (dt.datetime(2026, 3, 4, 9, 7, tzinfo=dt.UTC), "Mar 4, 2026, 9:07 AM UTC"),
    ],
)
def test_utc_stamp_reads_american(moment: dt.datetime, expected: str) -> None:
    assert utc_stamp(moment) == expected
