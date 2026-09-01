"""The corpus average says it leaves out the feeds that publish realtime.

#248. `comparisons.py` picks the largest homogeneous measured-category set for
any cross-feed aggregate, and the largest set is the one without realtime. So
every feed with measured realtime falls out of the corpus average on /pulse/,
out of `api/v1/trend.json`, and out of the change lists. Measured on
2026-08-06: 1,638 eligible, 145 excluded as
`measured_category_set_mismatch`, and 0 of the 24 agencies linked from /pulse/
had measured realtime.

The rule is right. A three-category overall score and a four-category one are
not the same measurement, and averaging them would be worse than excluding one.
The disclosure was the part that was missing, and it pointed against this
project's reader: an agency that adds a realtime feed, the upgrade the site
spends a page encouraging, disappears from the headline number on the day they
do it.

`comparison-policy.md` already said a feed without realtime is never excluded
for that reason. It said nothing about the inverse, which is the half a reader
needs.

The tests here pin that the sentence appears exactly when it is true, and that
it cannot be dropped while the cohort is still being excluded.
"""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _excluded_realtime_cohort,
    _realtime_cohort_note,
    _render_pulse_page,
)

# The shape `comparisons.eligible_records` publishes, with the numbers measured
# on the live corpus on 2026-08-06.
LIVE_COMPARISON: dict[str, Any] = {
    "eligible_count": 1638,
    "required_measured_categories": ["correctness", "freshness", "completeness"],
    "measured_category_cohorts": {
        "correctness+freshness+completeness": 1638,
        "correctness+freshness+completeness+realtime": 145,
    },
    "exclusion_counts": {"measured_category_set_mismatch": 145},
}

POINTS = [
    {"date": "2026-06-01", "average_score": 68.2, "agency_count": 1638, "expired_pct": 5},
    {"date": "2026-07-01", "average_score": 68.1, "agency_count": 1638, "expired_pct": 4},
]
SUMMARY = {
    "score_delta": -0.1,
    "first": {"date": "2026-06-01"},
    "last": {"date": "2026-07-01", "average_score": 68.1},
}


def _board(comparison: dict[str, Any]) -> dict[str, Any]:
    return {
        "top": [],
        "bottom": [],
        "most_improved": [],
        "most_declined": [],
        "comparison": comparison,
    }


def test_the_live_cohort_is_counted() -> None:
    assert _excluded_realtime_cohort(LIVE_COMPARISON) == 145


def test_the_pulse_page_says_the_realtime_cohort_is_excluded() -> None:
    html = _render_pulse_page(_board(LIVE_COMPARISON), [], POINTS, SUMMARY, [])
    assert "Feeds with measured realtime are not in this average." in html
    assert "145 feeds were scored on four categories this run" in html
    assert 'href="/realtime/"' in html
    # The framing the rubric already commits to: absence of realtime is neutral,
    # and so is presence. Neither is a mark against the agency.
    assert "by publishing realtime, not by getting worse" in html


def test_one_excluded_feed_reads_as_one() -> None:
    comparison = {
        **LIVE_COMPARISON,
        "measured_category_cohorts": {
            "correctness+freshness+completeness": 1638,
            "correctness+freshness+completeness+realtime": 1,
        },
    }
    assert "1 feed was scored on four categories" in _realtime_cohort_note(comparison)


def test_nothing_is_claimed_when_no_realtime_cohort_was_dropped() -> None:
    """The sentence appears because it is true, not because it is boilerplate."""
    comparison = {
        **LIVE_COMPARISON,
        "measured_category_cohorts": {"correctness+freshness+completeness": 1638},
        "exclusion_counts": {},
    }
    assert _realtime_cohort_note(comparison) == ""
    html = _render_pulse_page(_board(comparison), [], POINTS, SUMMARY, [])
    assert "Feeds with measured realtime are not in this average." not in html


def test_no_claim_when_realtime_is_itself_the_selected_cohort() -> None:
    """If the aggregate does measure realtime, there is nothing to disclose."""
    comparison = {
        **LIVE_COMPARISON,
        "required_measured_categories": [
            "correctness",
            "freshness",
            "completeness",
            "realtime",
        ],
    }
    assert _excluded_realtime_cohort(comparison) == 0


@pytest.mark.parametrize(
    "comparison",
    [
        {},
        {"required_measured_categories": []},
        {"required_measured_categories": ["correctness"], "measured_category_cohorts": None},
        {
            "required_measured_categories": ["correctness"],
            "measured_category_cohorts": {"correctness+realtime": "many"},
        },
    ],
)
def test_a_malformed_comparison_block_claims_nothing(comparison: dict[str, Any]) -> None:
    """Fail closed: an unreadable cohort block states no number at all."""
    assert _realtime_cohort_note(comparison) == ""


def test_the_disclosure_is_absent_without_the_note() -> None:
    """Proof the page test bites: the sentence is the only thing carrying it."""
    html = _render_pulse_page(_board({"eligible_count": 1638}), [], POINTS, SUMMARY, [])
    assert "Feeds with measured realtime" not in html
