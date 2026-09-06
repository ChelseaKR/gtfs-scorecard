"""No weighted trips means no expired share, not a zero one.

``weighted_impact`` returned ``expired_trips_pct: 0.0`` when the weighted trip
total was zero, one line above ``weighted_average_score``, which correctly
returns None on the same denominator. 0.0% reads as "none of these trips ride
on an expired feed" — the best possible answer — where the truth was that there
were no trips to divide by. It is published to /api/v1/ridership-impact.json
and read back onto the page.
"""

from __future__ import annotations

from scorecard_pipeline.ridership import weighted_impact


def _record(
    ntd: str, *, grade: str = "A", score: float = 90.0, expiry: str = "current"
) -> dict[str, object]:
    return {"ntd_id": ntd, "grade": grade, "score": score, "expiry_status": expiry}


def test_no_weighted_trips_yields_no_expired_share() -> None:
    """A matched reporter whose annual trips are zero: nothing to take a share of."""
    impact = weighted_impact([_record("00001")], {"1": 0})
    assert impact["matched_ntd_reporters"] == 1
    assert impact["total_annual_trips"] == 0
    assert impact["expired_trips_pct"] is None
    # The neighbouring metric already answered this way on the same denominator.
    assert impact["weighted_average_score"] is None


def test_no_matches_at_all_yields_no_expired_share() -> None:
    impact = weighted_impact([], {})
    assert impact["expired_trips_pct"] is None
    assert impact["weighted_average_score"] is None


def test_a_real_denominator_still_gives_a_real_share() -> None:
    """The narrowness test: an honest 0.0% survives, and so does a non-zero one."""
    clean = weighted_impact([_record("00001")], {"1": 100})
    assert clean["expired_trips_pct"] == 0.0

    mixed = weighted_impact(
        [_record("00001"), _record("00002", expiry="lapsed")],
        {"1": 300, "2": 100},
    )
    assert mixed["total_annual_trips"] == 400
    assert mixed["expired_trips_pct"] == 25.0


def test_the_page_does_not_print_a_share_it_does_not_have() -> None:
    from scorecard_pipeline.render_site import _ridership_impact_line

    impact = weighted_impact([_record("00001")], {"1": 0})
    html = _ridership_impact_line(impact)
    assert "None%" not in html
    assert "0.0%" not in html
    assert "no annual trips" in html
