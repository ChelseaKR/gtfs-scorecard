"""Tests for the beyond-the-grade recommendations aggregator."""

from __future__ import annotations

from pathlib import Path

from scorecard_pipeline.metrics import Finding
from scorecard_pipeline.recommend import _safe, gather_recommendations

FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"


def test_gather_returns_serialized_findings_over_a_real_feed() -> None:
    result = gather_recommendations(str(FIXTURE))
    assert isinstance(result.rows, list)
    # Whatever the fixture yields, every item is a serialized finding dict.
    for rec in result.rows:
        assert "code" in rec and "what" in rec and "fix" in rec


def test_a_failing_check_is_skipped_not_fatal() -> None:
    """Sandboxed, so it never aborts a score — and reported, so it is never
    mistaken for a check that ran and found nothing. See
    tests/test_recommendations_not_measured.py."""

    def boom() -> list[Finding]:
        raise RuntimeError("nope")

    assert _safe("x", boom) is None


def test_gather_on_a_missing_file_yields_no_recs_and_no_raise() -> None:
    # Each check sandboxes its own failure, so a bad path yields no recs, no raise.
    result = gather_recommendations("/no/such/feed.zip")
    assert result.rows == []
    assert sorted(result.not_measured) == ["accessibility", "fares", "flex"]
