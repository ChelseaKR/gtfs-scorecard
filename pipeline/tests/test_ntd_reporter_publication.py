"""The reporter counts reach /ntd/, in reporter units, or not at all.

#278. `/ntd/` answers "45.0% of 1,125 tracked feeds look ready to certify", and
says so plainly: the denominator is this project's registry. The question an FTA
reviewer or a Caltrans district liaison asks first is the other one, which
reporters obligated to publish GTFS have nothing discoverable at all, and that
population was unreachable from a feed-outward join.

`ntd_coverage.py` and the committed RY2024 snapshot answered it on 2026-08-15,
and `data/ntd/PROVENANCE.md` then said in as many words that nothing read them:
"Neither is read by the pipeline, the site, or the public API." These tests pin
the publication and the three guardrails the issue attaches to it.

The reconciliation guard is the load-bearing one. Reporter counts and feed-record
counts are different units, so a snapshot that does not declare its unit, or
whose tiers do not sum to its own denominator, publishes nothing at all rather
than a number a reader would take for the real denominator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.ntd_coverage import (
    REPORTER_UNIT,
    SNAPSHOT_NAME,
    TIER_ORDER,
    published_reporter_coverage,
    snapshot_path,
)
from scorecard_pipeline.render_site import _render_ntd_page

# The committed snapshot, by repository path. The autouse `isolated_repo_root`
# fixture points SCORECARD_ROOT at a throwaway directory, which is what
# `snapshot_path()` reads, so these tests name the real file explicitly.
COMMITTED = Path(__file__).resolve().parents[2] / "data" / "ntd" / SNAPSHOT_NAME


def _snapshot() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(COMMITTED.read_text(encoding="utf-8"))
    return payload


def _coverage() -> dict[str, Any] | None:
    return published_reporter_coverage(COMMITTED)


def test_snapshot_path_points_at_the_committed_file() -> None:
    """The default the renderer uses resolves to the file these tests read."""
    assert snapshot_path().parts[-3:] == ("data", "ntd", SNAPSHOT_NAME)


def _written(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_committed_snapshot_reconciles_and_publishes() -> None:
    coverage = _coverage()
    assert coverage is not None
    assert coverage["unit"] == REPORTER_UNIT
    assert coverage["obligated_reporters"] == 1253
    assert coverage["tracked_by_registry"] == 573
    assert coverage["discoverable_elsewhere"] == 39
    assert coverage["no_discoverable_feed_low"] == 473
    assert coverage["no_discoverable_feed_high"] == 641
    assert coverage["needs_human_review"] == 168


def test_the_tiers_sum_to_the_stated_population() -> None:
    coverage = _coverage()
    assert coverage is not None
    assert sum(coverage["by_tier"].values()) == coverage["obligated_reporters"]


def test_a_snapshot_that_does_not_declare_reporter_units_publishes_nothing(
    tmp_path: Path,
) -> None:
    """A feed-record count must never render under a reporter label."""
    payload = {**_snapshot(), "unit": "feed_records"}
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_a_snapshot_whose_tiers_do_not_reconcile_publishes_nothing(tmp_path: Path) -> None:
    payload = _snapshot()
    payload["by_tier"] = {
        **payload["by_tier"],
        "no_candidate": payload["by_tier"]["no_candidate"] + 1,
    }
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


@pytest.mark.parametrize("dropped", TIER_ORDER)
def test_a_snapshot_missing_a_tier_publishes_nothing(tmp_path: Path, dropped: str) -> None:
    """The tier-set guard, isolated so that only it can produce the verdict.

    The first version of this dropped `atlas_ntd_id` and left the denominator
    alone. That count is 33, so the sum stopped reconciling and the *next*
    guard returned None first: deleting the tier-set comparison outright left
    this test green. It was asserting the reconciliation guard twice and the
    tier-set guard never.

    Each case here subtracts the dropped tier's own count from
    `obligated_reporters`, so the remaining tiers sum to their denominator by
    construction and the reconciliation guard cannot fire. Every tier is
    covered rather than one named by hand, so this does not quietly weaken
    again if the tier it happened to name changes count. Without the tier-set
    guard, a dropped zero-count tier reaches the tier lookups below it and
    raises `KeyError` out of `_render_ntd_page`, which is a site render that
    dies instead of a page that says nothing.
    """
    payload = _snapshot()
    removed = payload["by_tier"][dropped]
    payload["by_tier"] = {k: v for k, v in payload["by_tier"].items() if k != dropped}
    payload["obligated_reporters"] -= removed
    assert sum(payload["by_tier"].values()) == payload["obligated_reporters"]
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(obligated_reporters="1,253"),
        lambda p: p.update(obligated_reporters=True),
        lambda p: p.update(by_tier=["not", "a", "mapping"]),
        lambda p: p["by_tier"].update(no_candidate="many"),
    ],
)
def test_a_malformed_snapshot_publishes_nothing(tmp_path: Path, mutate: Any) -> None:
    payload = _snapshot()
    mutate(payload)
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_an_absent_or_unreadable_snapshot_publishes_nothing(tmp_path: Path) -> None:
    assert published_reporter_coverage(tmp_path / "nothing.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert published_reporter_coverage(broken) is None


def _page(coverage: dict[str, Any] | None) -> str:
    payload: dict[str, Any] = {
        "total": 1125,
        "ready": 506,
        "at_risk": 140,
        "not_ready": 479,
        "pct_ready": 45.0,
        "by_state": {},
        "one_fix_from_ready": [],
        "one_fix_total": 0,
    }
    if coverage is not None:
        payload["reporter_coverage"] = coverage
    return _render_ntd_page(payload)


def test_the_page_states_all_three_reporter_counts_with_their_denominator() -> None:
    html = _page(_coverage())
    assert 'id="reporters"' in html
    assert "1,253 NTD reporters" in html
    assert "between <strong>473 and\n      641</strong>" in html.replace("\r", "")
    for count in ("573", "39", "168"):
        assert f"<td>{count}</td>" in html


def test_the_page_keeps_the_tracked_feed_measurement_unchanged() -> None:
    """The existing 45.0%-of-1,125 line is a different, honest measurement."""
    html = _page(_coverage())
    assert "45.0% of 1125 tracked feeds" in html


def test_the_page_says_the_two_denominators_are_different_units() -> None:
    html = _page(_coverage())
    assert "These are counts of NTD reporters." in html
    assert "is a different denominator from the tracked-feed" in html
    assert "The two are never\n      added." in html.replace("\r", "")


def test_a_reporter_with_no_feed_is_a_measurement_limit_not_a_finding() -> None:
    """The neutral-treatment rule, with more force: the fix may not be theirs."""
    html = _page(_coverage())
    assert "is a limit of what open catalogues\n      can see, not a finding about that agency" in (
        html.replace("\r", "")
    )
    assert "may belong to FTA's own\n      crosswalk" in html.replace("\r", "")


def test_the_page_publishes_nothing_about_reporters_without_a_snapshot() -> None:
    html = _page(None)
    assert 'id="reporters"' not in html
    assert "Reporters, not feeds" not in html
    assert "These are counts of NTD reporters." not in html
    # And the feed-side page is otherwise unchanged.
    assert "45.0% of 1125 tracked feeds" in html


# --- the section dates its own denominator, or it does not render ------------


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("report_year"), id="no report year"),
        pytest.param(lambda p: p.update(report_year=""), id="blank report year"),
        pytest.param(lambda p: p.update(report_year="   "), id="whitespace report year"),
        pytest.param(lambda p: p.pop("retrieved_utc"), id="no retrieval date"),
        pytest.param(lambda p: p.update(retrieved_utc=""), id="blank retrieval date"),
        pytest.param(lambda p: p.update(retrieved_utc="2026"), id="truncated retrieval date"),
    ],
)
def test_a_snapshot_that_cannot_date_itself_publishes_nothing(tmp_path: Path, mutate: Any) -> None:
    """A reconciling tier set is not enough to publish.

    The section's own fine print reads "Report Year {year}, retrieved {date}",
    and that sentence is how a reader judges whether the 1,253 is current. With
    the field missing it rendered "Report Year , retrieved " -- a provenance
    claim with nothing behind it, printed beside counts that are real. The
    counts would still reconcile, which is exactly why this needs its own guard.
    """
    payload = _snapshot()
    mutate(payload)
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_the_committed_snapshot_dates_itself() -> None:
    """The guard above is only safe if the real snapshot clears it."""
    coverage = _coverage()
    assert coverage is not None
    assert coverage["report_year"] == "2024"
    assert coverage["retrieved_utc"].startswith("2026-08-15")
