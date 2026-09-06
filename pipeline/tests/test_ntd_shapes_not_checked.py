"""A feed with no trips is unmeasurable for shapes, not failing it.

``assess_shapes_readiness`` answered "not ready" when ``trips.txt`` has no
rows, and said so in its own detail line: "shape coverage can't be checked".
Both halves were published. The prose said we could not check, and the status
beside it put the feed in the failing bucket of ``pct_ready`` on every NTD
rollup, and a "Not ready" badge on its page.

``NOT_CHECKED`` already exists for exactly this, with a rendered label ("Not
checked yet"), its own badge class, and a deliberate absence from ``_RANK``,
where membership is what "we measured it" means. It was simply not used here.
"""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.ntd import (
    AT_RISK,
    NOT_CHECKED,
    NOT_READY,
    READY,
    assess_shapes_readiness,
    shapes_portfolio_summary,
    shapes_status,
)
from scorecard_pipeline.rollups import _shapes_status


def _artifact(total: int, with_shape: int, *, agency_id: str = "a") -> dict[str, Any]:
    return {
        "agency": {"id": agency_id, "name": agency_id, "state": "CA", "country": "US"},
        "shapes_readiness": {
            "status": "unused: recomputed from the counts",
            "total_trips": total,
            "trips_with_shape": with_shape,
        },
    }


def test_a_feed_with_no_trips_is_not_checked_rather_than_not_ready() -> None:
    r = assess_shapes_readiness(total_trips=0, trips_with_shape=0)
    assert r.status == NOT_CHECKED
    assert not r.fix
    assert "could not be checked" in r.detail


def test_an_unmeasurable_feed_leaves_the_ntd_rollup_denominator() -> None:
    """Not a pass and not a failure: it is not in the population at all."""
    assert shapes_status(_artifact(0, 0)) is None
    assert _shapes_status(_artifact(0, 0)) is None


def test_pct_ready_no_longer_counts_an_unmeasurable_feed_as_a_failure() -> None:
    summary = shapes_portfolio_summary(
        [_artifact(10, 10, agency_id="covered"), _artifact(0, 0, agency_id="empty")]
    )
    assert summary.total == 1
    assert summary.ready == 1
    assert summary.not_ready == 0
    assert summary.pct_ready == 100.0
    assert summary.by_state["CA"]["total"] == 1


def test_the_three_measurable_verdicts_are_unchanged() -> None:
    """The narrowness test: only the zero-trip case moves."""
    assert assess_shapes_readiness(12, 0).status == NOT_READY
    assert assess_shapes_readiness(10, 6).status == AT_RISK
    assert assess_shapes_readiness(10, 10).status == READY
    assert shapes_status(_artifact(12, 0)) == NOT_READY
    assert _shapes_status(_artifact(10, 10)) == READY


def test_the_copy_still_never_claims_current_noncompliance() -> None:
    r = assess_shapes_readiness(0, 0)
    text = f"{r.detail} {r.fix}".lower()
    for mandate in ("you are not compliant", "you are in violation", "you must"):
        assert mandate not in text
