"""Tests for the standing cross-corpus vendor-regression radar (EXP-07)."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline import tool_profiles
from scorecard_pipeline.vendor_regression_radar import (
    AgencyRun,
    detect_regressions,
    render_private_worklist,
    render_public_digest,
)

TRILLIUM_URL = "https://oregon-gtfs.trilliumtransit.com/feed.zip"
# Same host, a feed Trillium serves but did not build: its own feed_info names
# another producer. It must never join the Trillium cohort (ADR 0045).
TRILLIUM_HOSTED_ONLY_URL = "https://oregon-gtfs.trilliumtransit.com/hosted-only.zip"
REMIX_URL = "https://gtfs.remix.com/feed.zip"
GENERIC_URL = "https://smallagency.example.org/gtfs.zip"

_DECLARATIONS = {
    TRILLIUM_URL: ("Trillium Solutions, Inc.", "https://trilliumtransit.com"),
    TRILLIUM_HOSTED_ONLY_URL: ("GMV Syncromatics", "https://gmvsyncromatics.com"),
}


@pytest.fixture(autouse=True)
def _publisher_declarations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cohorts follow the feeds' own publisher declarations, not the host.

    Stubbed here so these tests describe the cohorts they mean rather than
    whatever the committed snapshot happens to say about a look-alike URL.
    """
    monkeypatch.setattr(tool_profiles, "_recorded_declaration", _DECLARATIONS.get)


def _artifact(date: str, *codes: str, category: str = "correctness") -> dict[str, Any]:
    findings = [{"code": c, "count": 3, "what": f"what for {c}"} for c in codes]
    return {
        "snapshot_date": date,
        "rubric_version": "1.2",
        "scoring_profile_id": "gtfs-scorecard-1.2",
        "scoring_profile_rubric_version": "1.2",
        "validator_version": "8.0.1",
        "categories": {category: {"status": "measured", "findings": findings}},
    }


def _run(
    agency_id: str,
    static_url: str,
    curr_codes: tuple[str, ...],
    prev_codes: tuple[str, ...] | None = (),
    date: str = "2026-07-08",
    category: str = "correctness",
) -> AgencyRun:
    return AgencyRun(
        agency_id=agency_id,
        agency_name=agency_id.replace("-", " ").title(),
        static_url=static_url,
        curr_artifact=_artifact(date, *curr_codes, category=category),
        prev_artifact=(
            None if prev_codes is None else _artifact("2026-07-07", *prev_codes, category=category)
        ),
    )


def test_shared_new_code_across_cohort_is_flagged() -> None:
    # Four agencies behind Trillium; three acquire the same new code today.
    runs = [
        _run("agency-a", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-b", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-c", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-d", TRILLIUM_URL, ()),
    ]
    regressions = detect_regressions(runs)
    assert len(regressions) == 1
    reg = regressions[0]
    assert reg.tool_key == "trillium"
    assert reg.code == "fares_missing"
    assert reg.new_agencies == 3
    assert reg.cohort_size == 4
    assert reg.affected_names == ("Agency A", "Agency B", "Agency C")


def test_a_merely_hosted_feed_does_not_join_the_hosts_cohort() -> None:
    # Three Trillium-built feeds acquire a code today; a fourth feed on the same
    # host was built by someone else and shares neither the cohort nor the blame.
    runs = [
        _run("agency-a", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-b", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-c", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-d", TRILLIUM_URL, ()),
        _run("hosted-only", TRILLIUM_HOSTED_ONLY_URL, ("fares_missing",)),
    ]
    regressions = detect_regressions(runs)
    assert len(regressions) == 1
    assert regressions[0].tool_key == "trillium"
    assert regressions[0].cohort_size == 4
    assert "Hosted Only" not in regressions[0].affected_names


def test_below_absolute_floor_is_not_flagged() -> None:
    # A ten-agency cohort where only one agency picks up a new code: far too
    # small a share of a random independent event to read as a shared cause.
    runs = [_run(f"agency-{i}", TRILLIUM_URL, ("x",) if i == 0 else ()) for i in range(10)]
    assert detect_regressions(runs) == []


def test_below_share_threshold_is_not_flagged() -> None:
    # Three of twenty agencies (15%) is under the share threshold even though
    # it clears the absolute floor.
    runs = [_run(f"agency-{i}", TRILLIUM_URL, ("x",) if i < 3 else ()) for i in range(20)]
    assert detect_regressions(runs) == []


def test_cohort_smaller_than_minimum_detects_nothing() -> None:
    # Only two agencies behind this tool at all, even though both show the
    # same new code: too small a cohort to say anything about the tool.
    runs = [
        _run("agency-a", REMIX_URL, ("x",)),
        _run("agency-b", REMIX_URL, ("x",)),
    ]
    assert detect_regressions(runs) == []


def test_unmatched_host_never_grouped() -> None:
    # Generic hosting carries no producing-tool signal, so even an identical
    # same-day pattern across many agencies on unrecognized hosts is silent.
    runs = [_run(f"agency-{i}", GENERIC_URL, ("x",)) for i in range(5)]
    assert detect_regressions(runs) == []


def test_first_scan_agency_excluded_from_cohort() -> None:
    # An agency with no prior artifact has nothing to compare against, and
    # must not count toward the cohort size or the spike.
    runs = [
        _run("agency-a", TRILLIUM_URL, ("x",)),
        _run("agency-b", TRILLIUM_URL, ("x",)),
        _run("agency-c", TRILLIUM_URL, ("x",), prev_codes=None),
    ]
    assert detect_regressions(runs) == []


def test_reader_profile_changes_are_excluded_from_vendor_regression_cohort() -> None:
    runs = [
        _run("agency-a", TRILLIUM_URL, ("x",)),
        _run("agency-b", TRILLIUM_URL, ("x",)),
        _run("agency-c", TRILLIUM_URL, ("x",)),
    ]
    for run in runs:
        run.curr_artifact["fetch"] = {"reader_archive_profile": "flat-single-root-v1"}

    assert detect_regressions(runs) == []


def test_different_current_dates_are_not_pooled_as_one_same_day_spike() -> None:
    runs = []
    for day in ("2026-07-08", "2026-07-09", "2026-07-10"):
        runs.extend(
            [
                _run(f"affected-{day}", TRILLIUM_URL, ("x",), date=day),
                _run(f"steady-{day}", TRILLIUM_URL, (), date=day),
            ]
        )

    assert detect_regressions(runs) == []


def test_preexisting_code_is_not_a_regression() -> None:
    # A code present yesterday and today is not new; it should never surface
    # as a same-day spike even if the whole cohort shares it.
    runs = [_run(f"agency-{i}", TRILLIUM_URL, ("x",), prev_codes=("x",)) for i in range(5)]
    assert detect_regressions(runs) == []


def test_calendar_countdown_code_excluded_even_under_correctness() -> None:
    # feed_expiration_date30_days is a raw validator notice filed under
    # "correctness" in the artifact schema, but it is a calendar countdown
    # like any freshness finding: agencies behind one host often republish on
    # a similar cadence, so it would cross for many of them on the same day
    # for reasons having nothing to do with a producing-tool bug.
    runs = [_run(f"agency-{i}", TRILLIUM_URL, ("feed_expiration_date30_days",)) for i in range(5)]
    assert detect_regressions(runs) == []


def test_calendar_countdown_code_excluded_under_freshness_category() -> None:
    runs = [
        _run(f"agency-{i}", TRILLIUM_URL, ("scorecard_feed_expiring_soon",), category="freshness")
        for i in range(5)
    ]
    assert detect_regressions(runs) == []


def test_private_worklist_names_agencies() -> None:
    runs = [
        _run("agency-a", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-b", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-c", TRILLIUM_URL, ("fares_missing",)),
    ]
    worklist = render_private_worklist(detect_regressions(runs))
    assert "Agency A" in worklist
    assert "Agency B" in worklist
    assert "Agency C" in worklist
    assert "fares_missing" in worklist
    assert "Do not publish" in worklist


def test_public_digest_never_names_an_agency() -> None:
    runs = [
        _run("agency-a", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-b", TRILLIUM_URL, ("fares_missing",)),
        _run("agency-c", TRILLIUM_URL, ("fares_missing",)),
    ]
    digest = render_public_digest(detect_regressions(runs))
    assert "Agency A" not in digest
    assert "Agency B" not in digest
    assert "Agency C" not in digest
    assert "Trillium" in digest
    assert "~3 feeds" in digest


def test_empty_input_renders_no_pattern_message() -> None:
    assert "No same-day vendor-regression pattern" in render_private_worklist([])
    assert "No correlated same-day regression" in render_public_digest([])
