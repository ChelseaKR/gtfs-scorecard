"""A recommendation check that crashed must not read as a clean bill of health.

``_safe`` caught every exception and returned ``[]``, which is byte-identical
to the answer a check gives when it ran and found nothing to suggest. So an
accessibility audit that died on a malformed pathways table published the same
page as a feed with no accessibility gaps at all, and nothing anywhere said
which of the two had happened.

The sandbox itself is right and stays: one broken table must not cost an agency
its score. What was missing was the record that the check did not run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline import recommend
from scorecard_pipeline.metrics import Finding
from scorecard_pipeline.recommend import _safe, gather_recommendations

FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"


def _finding(code: str) -> Finding:
    return Finding(
        code=code,
        severity="INFO",
        count=1,
        what="Something to consider.",
        why="It helps riders.",
        fix="Add the field.",
        effort="One setting.",
        deduction=0.0,
    )


def test_a_check_that_ran_and_found_nothing_is_not_a_check_that_crashed() -> None:
    assert _safe("clean", lambda: []) == []

    def boom() -> list[Finding]:
        raise RuntimeError("nope")

    assert _safe("broken", boom) is None


def test_a_crashed_check_is_named_rather_than_silently_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_path: str) -> list[Finding]:
        raise RuntimeError("malformed pathways.txt")

    from scorecard_pipeline import accessibility

    monkeypatch.setattr(accessibility, "accessibility_audit", boom)
    result = gather_recommendations(str(FIXTURE))
    assert result.not_measured == ("accessibility",)
    assert all(row["category"] != "accessibility" for row in result.rows)


def test_a_missing_feed_measures_nothing_at_all() -> None:
    """Every check failed, so every category is unmeasured, not clean."""
    result = gather_recommendations("/no/such/feed.zip")
    assert result.rows == []
    assert sorted(result.not_measured) == ["accessibility", "fares", "flex"]


def test_a_real_feed_measures_every_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """The narrowness test: nothing is reported unmeasured on a readable feed."""
    result = gather_recommendations(str(FIXTURE))
    assert result.not_measured == ()
    for row in result.rows:
        assert "code" in row and "what" in row and "fix" in row


def test_the_wire_shape_of_a_recommendation_row_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import fares

    monkeypatch.setattr(fares, "fares_v2_findings", lambda _p: [_finding("scorecard_fares_v2")])
    monkeypatch.setattr(recommend, "_safe", lambda label, fn: _safe(label, fn))
    result = gather_recommendations(str(FIXTURE))
    rows = [r for r in result.rows if r["code"] == "scorecard_fares_v2"]
    assert rows and rows[0]["category"] == "fares"
    assert "measured" not in rows[0]


# ------------------------------------------------------------- what the page says


def test_the_artifact_carries_the_gap_only_when_there_is_one() -> None:
    assert recommend.Recommendations([]).artifact_block() == {"recommendations": []}
    assert recommend.Recommendations([], ("accessibility",)).artifact_block() == {
        "recommendations": [],
        "recommendations_not_measured": ["accessibility"],
    }


def test_the_page_says_the_accessibility_audit_did_not_run() -> None:
    from scorecard_pipeline.render_site import _accessibility_depth_signals

    silent = _accessibility_depth_signals({"recommendations": []})
    assert silent == ""

    spoken = _accessibility_depth_signals(
        {"recommendations": [], "recommendations_not_measured": ["accessibility"]}
    )
    assert "not checked" in spoken.lower()
    assert "gap in our check" in spoken


def test_the_page_names_a_beyond_the_grade_check_that_did_not_run() -> None:
    from scorecard_pipeline.render_site import _recommendations_section

    silent = _recommendations_section({"recommendations": []})
    assert silent == ""

    spoken = _recommendations_section(
        {"recommendations": [], "recommendations_not_measured": ["fares", "flex"]}
    )
    assert "fare detail and on-demand service checks could not run" in spoken
