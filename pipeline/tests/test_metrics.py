"""Tests for the Correctness and Freshness scoring metrics."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from scorecard_pipeline.gtfs import FeedDates
from scorecard_pipeline.metrics import (
    SERVICE_HORIZON_REVIEW_YEARS,
    STALE_FEED_DAYS,
    UNREACHABLE_STREAK_CHECKS,
    CategoryResult,
    correctness,
    expiry_status,
    operating_signal,
    resolve_service_horizon_status,
    service_horizon_status,
)
from scorecard_pipeline.metrics import (
    freshness as _freshness_maybe,
)
from scorecard_pipeline.validate import NoticeGroup, ValidationReport


# `freshness` returns None when the archive held no table that can carry a
# service date. Every fixture below has one, so this wrapper keeps the existing
# call sites unchanged while turning an unexpected "not measurable" into a loud
# failure instead of an attribute error.
def freshness(*args: Any, **kwargs: Any) -> CategoryResult:
    result = _freshness_maybe(*args, **kwargs)
    assert result is not None, "this fixture has date tables and must measure freshness"
    return result


TODAY = dt.date(2026, 6, 11)


def report(*groups: NoticeGroup) -> ValidationReport:
    return ValidationReport(validator_version="8.0.1", notices=list(groups))


def feed_dates(
    end: dt.date | None,
    last_service: dt.date | None = None,
    has_feed_info: bool = True,
    seasonal_boundary: bool = False,
) -> FeedDates:

    return FeedDates(
        has_feed_info=has_feed_info,
        feed_publisher_name="Test",
        feed_version="v1",
        feed_start_date=dt.date(2026, 1, 1) if has_feed_info and end else None,
        feed_end_date=end,
        last_service_date=last_service or end,
        seasonal_boundary=seasonal_boundary,
    )


class TestCorrectness:
    def test_clean_feed_scores_100(self) -> None:
        result = correctness(report())
        assert result.score == 100.0
        assert result.findings == []

    def test_errors_cost_more_than_warnings(self) -> None:
        err = correctness(report(NoticeGroup("unusable_trip", "ERROR", 1)))
        warn = correctness(report(NoticeGroup("unused_stop", "WARNING", 1)))
        assert err.score < warn.score

    def test_widespread_notice_costs_more_but_sublinearly(self) -> None:
        one = correctness(report(NoticeGroup("unused_stop", "WARNING", 1)))
        many = correctness(report(NoticeGroup("unused_stop", "WARNING", 500)))
        assert many.score < one.score
        # 500 instances of one warning must not zero the score
        assert many.score > 80.0

    def test_score_floor_is_zero(self) -> None:
        groups = [NoticeGroup(f"error_{i}", "ERROR", 100) for i in range(20)]
        assert correctness(report(*groups)).score == 0.0

    def test_findings_carry_plain_language(self) -> None:
        result = correctness(report(NoticeGroup("missing_trip_headsign", "WARNING", 3)))
        finding = result.findings[0]
        assert "headsign" in finding.what.lower()
        assert finding.fix
        assert finding.why
        # The effort hint is part of the promised finding copy (CLAUDE.md: every
        # fix ships with an effort hint) and _fix_owner reads it to decide whether
        # the work belongs to the agency or its export tool.
        assert finding.effort
        assert finding.to_json()["owner"] == "Likely your export tool"

    def test_summary_reports_how_much_the_validator_found(self) -> None:
        # The summary carries three numbers a reader acts on: how many kinds of
        # issue, how many instances in total, and the split by severity.
        flagged = correctness(
            report(
                NoticeGroup("a", "ERROR", 2),
                NoticeGroup("b", "WARNING", 3),
                NoticeGroup("c", "INFO", 4),
            )
        )
        assert "3 kinds" in flagged.summary
        assert "9 instances" in flagged.summary
        assert "(2 error, 3 warning, 4 informational)" in flagged.summary
        assert "no problems" not in flagged.summary
        single = correctness(report(NoticeGroup("a", "ERROR", 1)))
        assert "1 kind of issue across 1 instance " in single.summary
        # A feed with nothing flagged says so, and only then.
        assert "no problems" in correctness(report()).summary

    def test_details_carry_validator_provenance_and_counts(self) -> None:
        # A grade has to name the validator version that produced it
        # (METHODOLOGY_CHANGELOG 1.1), and the per-severity instance counts are
        # what the findings table and the national rollups read.
        result = correctness(report(NoticeGroup("a", "ERROR", 2), NoticeGroup("b", "WARNING", 3)))
        assert result.details == {
            "validator_version": "8.0.1",
            "instances_by_severity": {"ERROR": 2, "WARNING": 3, "INFO": 0},
            "distinct_codes": 2,
        }


class TestFreshness:
    def test_long_runway_scores_100(self) -> None:
        result = freshness(feed_dates(TODAY + dt.timedelta(days=90)), TODAY)
        assert result.score == 100.0

    def test_score_falls_as_expiry_nears(self) -> None:
        far = freshness(feed_dates(TODAY + dt.timedelta(days=45)), TODAY)
        near = freshness(feed_dates(TODAY + dt.timedelta(days=10)), TODAY)
        assert far.score > near.score > 0.0

    def test_expired_feed_scores_zero(self) -> None:
        result = freshness(feed_dates(TODAY - dt.timedelta(days=3)), TODAY)
        assert result.score == 0.0
        assert "ended" in result.summary

    def test_recently_lapsed_seasonal_feed_is_softened_not_zeroed(self) -> None:
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=30)), TODAY, service_type="seasonal"
        )
        assert result.score >= 50.0  # floored, not a silent-expiry zero
        codes = {f.code for f in result.findings}
        assert "scorecard_intermittent_calendar_ended" in codes
        assert "scorecard_feed_expired" not in codes
        assert all(f.severity != "ERROR" for f in result.findings)

    def test_long_dead_seasonal_feed_still_serious(self) -> None:
        # Over a year expired is genuine abandonment, not a between-seasons gap.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=STALE_FEED_DAYS + 10)),
            TODAY,
            service_type="seasonal",
        )
        assert result.score == 0.0
        assert "scorecard_feed_expired" in {f.code for f in result.findings}

    def test_fixed_service_not_softened(self) -> None:
        result = freshness(feed_dates(TODAY - dt.timedelta(days=30)), TODAY, service_type="fixed")
        assert result.score == 0.0
        assert "scorecard_feed_expired" in {f.code for f in result.findings}

    def test_detected_seasonal_boundary_softens_recent_lapse(self) -> None:
        # Undeclared ("fixed") service, but the calendars themselves encode a
        # service boundary: planned-transition framing, not a lapse alarm.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=30), seasonal_boundary=True),
            TODAY,
            service_type="fixed",
        )
        assert result.score >= 50.0
        codes = {f.code for f in result.findings}
        assert "scorecard_planned_service_boundary" in codes
        assert "scorecard_feed_expired" not in codes
        assert "scorecard_intermittent_calendar_ended" not in codes
        assert all(f.severity != "ERROR" for f in result.findings)
        assert result.details["seasonal_boundary"] is True
        assert "next service period is published" in result.summary

    def test_detected_boundary_past_stale_floor_still_serious(self) -> None:
        # The detection must never become a loophole: dead over a year is a
        # lapsed feed no matter what the old calendars encoded.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=STALE_FEED_DAYS + 10), seasonal_boundary=True),
            TODAY,
            service_type="fixed",
        )
        assert result.score == 0.0
        assert "scorecard_feed_expired" in {f.code for f in result.findings}

    def test_declared_seasonal_keeps_its_own_finding_code(self) -> None:
        # A declared seasonal feed keeps the intermittent code even when the
        # boundary was also detected from the calendars.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=30), seasonal_boundary=True),
            TODAY,
            service_type="seasonal",
        )
        codes = {f.code for f in result.findings}
        assert "scorecard_intermittent_calendar_ended" in codes
        assert "scorecard_planned_service_boundary" not in codes

    def test_continuous_calendar_behavior_unchanged(self) -> None:
        # No detected boundary (the default) leaves fixed-service scoring alone.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=30), seasonal_boundary=False),
            TODAY,
            service_type="fixed",
        )
        assert result.score == 0.0
        assert "scorecard_feed_expired" in {f.code for f in result.findings}
        assert result.details["seasonal_boundary"] is False

    def test_missing_feed_info_dates_deducts(self) -> None:
        with_info = freshness(feed_dates(TODAY + dt.timedelta(days=90)), TODAY)
        without = freshness(
            FeedDates(
                has_feed_info=False,
                feed_publisher_name=None,
                feed_version=None,
                feed_start_date=None,
                feed_end_date=None,
                last_service_date=TODAY + dt.timedelta(days=90),
            ),
            TODAY,
        )
        assert without.score == with_info.score - 15.0
        assert without.findings[0].code == "scorecard_missing_feed_info_dates"

    def test_no_dates_at_all_is_zero_with_explanation(self) -> None:
        result = freshness(FeedDates(False, None, None, None, None, None), TODAY)
        assert result.score == 0.0
        assert result.findings[0].code == "scorecard_no_expiry_date"

    def test_expiry_uses_earlier_of_feed_info_and_service(self) -> None:
        # feed_info claims 90 days but service actually ends in 10
        result = freshness(
            feed_dates(
                TODAY + dt.timedelta(days=90),
                last_service=TODAY + dt.timedelta(days=10),
            ),
            TODAY,
        )
        # effective_expiry picks the min of feed_info end and last service date
        assert result.details["days_until_expiry"] == 10
        assert result.score < 100.0

    def test_normal_multi_year_horizon_is_unchanged(self) -> None:
        expiry = TODAY.replace(year=TODAY.year + 5)
        result = freshness(feed_dates(expiry), TODAY)
        assert result.score == 100.0
        assert result.summary == f"Service data covers the next {(expiry - TODAY).days} days."
        assert result.details["service_horizon_status"] == "within_review_threshold"
        assert result.findings == []

    def test_exact_review_boundary_is_not_flagged(self) -> None:
        expiry = TODAY.replace(year=TODAY.year + SERVICE_HORIZON_REVIEW_YEARS)
        result = freshness(feed_dates(expiry), TODAY)
        assert service_horizon_status(expiry, TODAY) == "within_review_threshold"
        assert result.details["service_horizon_status"] == "within_review_threshold"
        assert result.findings == []

    def test_day_after_review_boundary_is_flagged_without_changing_score(self) -> None:
        boundary = TODAY.replace(year=TODAY.year + SERVICE_HORIZON_REVIEW_YEARS)
        expiry = boundary + dt.timedelta(days=1)
        result = freshness(feed_dates(expiry), TODAY)
        assert result.score == 100.0
        assert result.details["service_horizon_status"] == "unusually_distant"
        assert result.details["effective_expiry_date"] == expiry.isoformat()
        assert result.details["days_until_expiry"] == (expiry - TODAY).days
        assert result.findings == []
        assert "unusually distant" in result.summary

    def test_year_2100_horizon_is_an_advisory_not_a_finding(self) -> None:
        from scorecard_pipeline.score import build_scorecard

        result = freshness(feed_dates(dt.date(2100, 12, 31)), TODAY)
        assert result.score == 100.0
        assert result.findings == []
        assert "may be intentional" in result.summary
        assert build_scorecard([result]).top_fixes == []

    def test_horizon_advisory_does_not_change_findings_top_fixes_or_rollups(self) -> None:
        from scorecard_pipeline.feeddiff import diff_artifacts
        from scorecard_pipeline.findings_national import agency_findings, national_problems
        from scorecard_pipeline.fixlog import diff_receipts
        from scorecard_pipeline.score import build_scorecard

        normal = freshness(feed_dates(TODAY + dt.timedelta(days=90)), TODAY)
        distant = freshness(feed_dates(dt.date(2100, 12, 31)), TODAY)
        normal_card = build_scorecard([normal])
        distant_card = build_scorecard([distant])
        assert distant.score == normal.score
        assert distant.to_json()["findings"] == normal.to_json()["findings"] == []
        assert distant_card.top_fixes == normal_card.top_fixes == []

        def artifact(result: CategoryResult, snapshot: str) -> dict[str, object]:
            return {
                "snapshot_date": snapshot,
                "overall": {"grade": "A", "score": 100.0},
                "feed": {"sha256": "same", "size_bytes": 1},
                "categories": {"freshness": result.to_json()},
            }

        before = artifact(normal, "2026-06-10")
        after = artifact(distant, "2026-06-11")
        assert agency_findings(after) == []
        assert (
            national_problems([agency_findings(after)], total_agencies=1)["prevalence_by_code"]
            == {}
        )
        finding_diff = diff_artifacts(before, after)
        assert finding_diff.new == finding_diff.resolved == finding_diff.changed == []
        assert diff_receipts(before, after) == []

    # ---- day boundaries on the freshness ladder (docs/rubric.md "Freshness") --
    # Each case below sits exactly on a threshold the rubric states. The examples
    # elsewhere in this class all sit well inside a band, so the thresholds
    # themselves were unpinned.

    def test_expiry_day_itself_counts_as_already_expired(self) -> None:
        # Day zero is the day riders lose trip planning, so it reads as expired,
        # not as "one more day". expiry_status() draws the same line.
        result = freshness(feed_dates(TODAY), TODAY)
        assert result.score == 0.0
        assert [f.code for f in result.findings] == ["scorecard_feed_expired"]
        assert "ended 0 day(s) ago" in result.summary
        assert expiry_status(0) == "lapsed"

    def test_expiry_day_is_softened_for_intermittent_service(self) -> None:
        # The softening covers the same day-zero boundary: a seasonal calendar
        # that runs out today may simply be between service periods.
        result = freshness(feed_dates(TODAY), TODAY, service_type="seasonal")
        assert result.score == 50.0
        assert [f.code for f in result.findings] == ["scorecard_intermittent_calendar_ended"]

    def test_a_day_of_runway_left_is_never_reported_as_ended(self) -> None:
        # One day out the feed still works today, so it is expiring, not expired,
        # for every service type. The softened floor must not apply either.
        for service_type in ("fixed", "seasonal", "demand_response"):
            result = freshness(
                feed_dates(TODAY + dt.timedelta(days=1)), TODAY, service_type=service_type
            )
            assert [f.code for f in result.findings] == ["scorecard_feed_expiring_soon"]
            assert "runs out in 1 day(s)" in result.summary
            assert result.score < 50.0

    def test_exactly_one_year_expired_is_never_softened(self) -> None:
        # STALE_FEED_DAYS is the inclusive line: a feed dead a full year is stale,
        # whatever its service type, so the softening cannot hide it.
        result = freshness(
            feed_dates(TODAY - dt.timedelta(days=STALE_FEED_DAYS)), TODAY, service_type="seasonal"
        )
        assert result.score == 0.0
        assert "scorecard_feed_expired" in {f.code for f in result.findings}
        assert expiry_status(-STALE_FEED_DAYS) == "stale"

    def test_thirty_days_of_runway_still_meets_the_caltrans_floor(self) -> None:
        # Caltrans v4.0 asks for at least 30 days of future service. A feed
        # sitting exactly on that floor scores 50 and is not warned about; one
        # day less is.
        at_floor = freshness(feed_dates(TODAY + dt.timedelta(days=30)), TODAY)
        assert at_floor.score == 50.0
        assert at_floor.findings == []
        assert at_floor.summary == "Service data covers the next 30 days."
        below = freshness(feed_dates(TODAY + dt.timedelta(days=29)), TODAY)
        assert [f.code for f in below.findings] == ["scorecard_feed_expiring_soon"]

    def test_on_demand_service_is_softened_and_named_like_seasonal(self) -> None:
        # "demand_response" is the second declared intermittent type; a recently
        # lapsed on-demand calendar gets the same floor and its own wording.
        on_demand = freshness(
            feed_dates(TODAY - dt.timedelta(days=30)), TODAY, service_type="demand_response"
        )
        assert on_demand.score == 50.0
        assert [f.code for f in on_demand.findings] == ["scorecard_intermittent_calendar_ended"]
        assert "on-demand service's published calendar ended 30 day(s) ago" in on_demand.summary
        seasonal = freshness(
            feed_dates(TODAY - dt.timedelta(days=30)), TODAY, service_type="seasonal"
        )
        assert "seasonal service's published calendar ended 30 day(s) ago" in seasonal.summary

    def test_feed_info_needs_both_validity_dates(self) -> None:
        # One date alone cannot bound a validity window, so a feed_end_date
        # without a feed_start_date is still incomplete.
        end = TODAY + dt.timedelta(days=90)
        only_end = FeedDates(
            has_feed_info=True,
            feed_publisher_name="Test",
            feed_version="v1",
            feed_start_date=None,
            feed_end_date=end,
            last_service_date=end,
        )
        result = freshness(only_end, TODAY)
        assert result.score == 85.0
        assert [f.code for f in result.findings] == ["scorecard_missing_feed_info_dates"]
        # feed_info.txt is present, so the copy must not claim the file is absent.
        assert "the file itself is absent" not in result.findings[0].what

    def test_leap_day_boundary_uses_calendar_years(self) -> None:
        leap_today = dt.date(2028, 2, 29)
        boundary = dt.date(2038, 2, 28)
        assert service_horizon_status(boundary, leap_today) == "within_review_threshold"
        assert service_horizon_status(boundary + dt.timedelta(days=1), leap_today) == (
            "unusually_distant"
        )


class TestFreshnessPublishedFields:
    """What a freshness result promises its readers: points that match the score,
    a null countdown when nothing is knowable, and findings the artifact schema
    will accept."""

    def test_finding_points_match_the_points_the_category_lost(self) -> None:
        # A finding card says "about +N points". For every freshness finding
        # except the deliberately softened expiring-soon card, N is the whole
        # gap between the category's score and 100.
        no_expiry = freshness(FeedDates(False, None, None, None, None, None), TODAY)
        assert no_expiry.score == 0.0
        assert no_expiry.findings[0].deduction == 100.0

        expired = freshness(feed_dates(TODAY - dt.timedelta(days=30)), TODAY)
        assert expired.score == 0.0
        assert expired.findings[0].deduction == 100.0

        lapsed = freshness(
            feed_dates(TODAY - dt.timedelta(days=30)), TODAY, service_type="seasonal"
        )
        assert lapsed.findings[0].deduction == pytest.approx(100.0 - lapsed.score)

        boundary = freshness(
            feed_dates(TODAY - dt.timedelta(days=30), seasonal_boundary=True), TODAY
        )
        assert boundary.findings[0].deduction == pytest.approx(100.0 - boundary.score)

        end = TODAY + dt.timedelta(days=90)
        with_dates = freshness(feed_dates(end), TODAY)
        without = freshness(FeedDates(False, None, None, None, None, end), TODAY)
        missing = next(f for f in without.findings if f.code == "scorecard_missing_feed_info_dates")
        assert missing.deduction == 15.0 == with_dates.score - without.score

    def test_the_score_floor_is_zero_when_deductions_stack(self) -> None:
        # An expired feed that also lacks feed_info dates loses more than it has;
        # freshness bottoms out at 0 rather than going negative or leaving a
        # residue behind.
        result = freshness(
            FeedDates(False, None, None, None, None, TODAY - dt.timedelta(days=30)), TODAY
        )
        assert result.score == 0.0
        assert {f.code for f in result.findings} == {
            "scorecard_feed_expired",
            "scorecard_missing_feed_info_dates",
        }

    def test_expiring_soon_card_advertises_a_softened_point_estimate(self) -> None:
        # This one card understates its impact on purpose (a feed one day from
        # expiry still works today), so it must stay below the raw category loss
        # and fall by one point per day of runway lost. Changing the curve is a
        # governed methodology change, which is why the numbers are pinned here.
        ten_days = freshness(feed_dates(TODAY + dt.timedelta(days=10)), TODAY)
        soon = ten_days.findings[0]
        assert soon.code == "scorecard_feed_expiring_soon"
        assert soon.deduction == 70.0
        assert soon.deduction < 100.0 - ten_days.score
        one_day = freshness(feed_dates(TODAY + dt.timedelta(days=1)), TODAY)
        assert one_day.findings[0].deduction == 79.0

    def test_an_unknown_expiry_publishes_a_null_countdown(self) -> None:
        # Two dozen modules read details["days_until_expiry"] as a number or
        # null. A feed with no readable end date must publish null, never a
        # placeholder, or every consumer of the countdown misreads it.
        result = freshness(FeedDates(False, None, None, None, None, None), TODAY)
        assert result.details["days_until_expiry"] is None
        assert result.details["effective_expiry_date"] is None
        assert result.details["service_horizon_status"] == "unknown"
        assert result.details["service_horizon_review_years"] == SERVICE_HORIZON_REVIEW_YEARS

    def test_every_finding_the_category_can_emit_is_publishable(self) -> None:
        # The artifact schema requires severity, count, and the four
        # plain-language fields on every finding, and severity decides the fix
        # tier in score._fix_tier. One case per finding code, so a branch that
        # drops a field or mis-labels a severity fails here.
        expected_severity = {
            "scorecard_no_expiry_date": "ERROR",
            "scorecard_feed_expired": "ERROR",
            "scorecard_feed_expiring_soon": "WARNING",
            "scorecard_intermittent_calendar_ended": "WARNING",
            "scorecard_planned_service_boundary": "WARNING",
            "scorecard_missing_feed_info_dates": "WARNING",
        }
        lapsed = TODAY - dt.timedelta(days=30)
        results = [
            freshness(FeedDates(False, None, None, None, None, None), TODAY),
            freshness(feed_dates(lapsed), TODAY),
            freshness(feed_dates(TODAY + dt.timedelta(days=10)), TODAY),
            freshness(feed_dates(lapsed), TODAY, service_type="seasonal"),
            freshness(feed_dates(lapsed), TODAY, service_type="demand_response"),
            freshness(feed_dates(lapsed, seasonal_boundary=True), TODAY),
            freshness(FeedDates(False, None, None, None, None, TODAY), TODAY),
            freshness(feed_dates(TODAY + dt.timedelta(days=90)), TODAY),
            freshness(feed_dates(dt.date(2100, 12, 31)), TODAY),
        ]
        seen: set[str] = set()
        for result in results:
            assert result.summary.strip()
            for f in result.findings:
                seen.add(f.code)
                assert f.severity == expected_severity[f.code]
                assert f.what.strip()
                assert f.why.strip()
                assert f.fix.strip()
                assert f.effort.strip()
                # Every freshness finding is about the feed as a whole, and the
                # site prints the instance count on the card, so it is one.
                assert f.count == 1
                assert f.deduction >= 0.0
        assert seen == set(expected_severity)


class TestResolveServiceHorizonStatus:
    def test_derives_production_legacy_day_counts(self) -> None:
        assert (
            resolve_service_horizon_status({"date": "2026-07-10", "days_until_expiry": 26_837})
            == "unusually_distant"
        )
        assert (
            resolve_service_horizon_status(
                {"snapshot_date": "2026-07-13", "days_until_expiry": 26_834}
            )
            == "unusually_distant"
        )

    def test_prefers_effective_expiry_and_uses_strict_calendar_boundary(self) -> None:
        snapshot = dt.date(2026, 7, 13)
        boundary = snapshot.replace(year=2036)
        assert (
            resolve_service_horizon_status(
                {"effective_expiry_date": boundary.isoformat()}, snapshot
            )
            == "within_review_threshold"
        )
        assert (
            resolve_service_horizon_status(
                {"effective_expiry_date": (boundary + dt.timedelta(days=1)).isoformat()},
                snapshot,
            )
            == "unusually_distant"
        )

    def test_explicit_status_is_authoritative(self) -> None:
        values = {
            "service_horizon_status": "unknown",
            "days_until_expiry": 26_834,
        }
        assert resolve_service_horizon_status(values, "2026-07-13") == "unknown"

    def test_every_published_status_value_is_taken_as_written(self) -> None:
        # All three published values are authoritative, not just "unknown": a
        # record that states its status is never re-derived from its dates, so a
        # later threshold change cannot silently restate an old artifact.
        distant = {"snapshot_date": "2026-07-13", "days_until_expiry": 26_834}
        near = {"snapshot_date": "2026-07-13", "days_until_expiry": 100}
        assert (
            resolve_service_horizon_status(
                {**distant, "service_horizon_status": "within_review_threshold"}
            )
            == "within_review_threshold"
        )
        assert (
            resolve_service_horizon_status({**distant, "service_horizon_status": "unknown"})
            == "unknown"
        )
        assert (
            resolve_service_horizon_status({**near, "service_horizon_status": "unusually_distant"})
            == "unusually_distant"
        )

    def test_a_whole_number_written_as_a_float_still_resolves(self) -> None:
        # JSON gives no integer type, so a legacy record's day count can arrive
        # as 26834.0. A whole number is usable however it was written; only a
        # fractional or non-finite count is unusable.
        snapshot = "2026-07-13"
        assert (
            resolve_service_horizon_status({"days_until_expiry": 26_834.0}, snapshot)
            == "unusually_distant"
        )
        assert (
            resolve_service_horizon_status({"days_until_expiry": 100.0}, snapshot)
            == "within_review_threshold"
        )

    def test_bad_or_missing_legacy_inputs_stay_unknown(self) -> None:
        snapshot = "2026-07-13"
        for values, checked in (
            ({}, None),
            ({"days_until_expiry": 26_834}, None),
            ({"date": "not-a-date", "days_until_expiry": 26_834}, None),
            ({"days_until_expiry": True}, snapshot),
            ({"days_until_expiry": 2.5}, snapshot),
            ({"days_until_expiry": float("inf")}, snapshot),
            ({"days_until_expiry": 10**20}, snapshot),
        ):
            assert resolve_service_horizon_status(values, checked) == "unknown"


class TestExpiryStatus:
    def test_unknown_when_no_date(self) -> None:
        assert expiry_status(None) == "unknown"

    def test_current_when_well_ahead(self) -> None:
        assert expiry_status(60) == "current"
        assert expiry_status(31) == "current"

    def test_expiring_soon_window(self) -> None:
        assert expiry_status(30) == "expiring_soon"
        assert expiry_status(1) == "expiring_soon"

    def test_lapsed_is_recent(self) -> None:
        # Day of expiry counts as lapsed, not expiring.
        assert expiry_status(0) == "lapsed"
        assert expiry_status(-14) == "lapsed"
        assert expiry_status(-(STALE_FEED_DAYS - 1)) == "lapsed"

    def test_stale_past_a_year(self) -> None:
        assert expiry_status(-STALE_FEED_DAYS) == "stale"
        assert expiry_status(-1628) == "stale"


class TestOperatingSignal:
    def test_empty_for_a_current_or_expiring_feed(self) -> None:
        assert operating_signal("current", 0) == ""
        assert operating_signal("expiring_soon", 40) == ""
        assert operating_signal("unknown", 0) == ""

    def test_reachable_when_failures_below_the_streak(self) -> None:
        assert operating_signal("lapsed", 0) == "reachable"
        assert operating_signal("stale", UNREACHABLE_STREAK_CHECKS - 1) == "reachable"

    def test_unreachable_at_the_streak_threshold(self) -> None:
        assert operating_signal("stale", UNREACHABLE_STREAK_CHECKS) == "unreachable"
        assert operating_signal("lapsed", UNREACHABLE_STREAK_CHECKS + 10) == "unreachable"


def test_finding_to_json_carries_point_value() -> None:
    result = correctness(report(NoticeGroup("unusable_trip", "ERROR", 1)))
    fix = result.findings[0].to_json()
    assert fix["points"] == 12.0  # the deduction this finding caused


def test_fix_owner_classifies_export_vs_team() -> None:
    from scorecard_pipeline.metrics import _fix_owner

    assert _fix_owner("One export setting.", "Re-export.", "Expired.") == "Likely your export tool"
    assert (
        _fix_owner("A field survey of the busiest stops.", "Set wheelchair_boarding.", "Blank.")
        == "Likely your team"
    )
    assert _fix_owner("Two fields.", "Add agency_phone.", "Missing.") == ""
