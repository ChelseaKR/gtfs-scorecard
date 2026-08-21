"""Property-based invariants for the scoring math (FIX-05).

The example-based suites pin specific grades; these pin the *shape* of the
math across the input space Hypothesis can reach: monotonicity, bounds,
grade-band consistency, renormalization, and fix-priority stability. A
deliberate off-by-one in a deduction constant, a flipped comparison in the
grade ladder, or a broken renormalization should fail at least one of these
without anyone having authored that exact example.

Runtime is bounded by the "scorecard" profile registered below so these stay
part of the fast `make verify` gate.
"""

from __future__ import annotations

import datetime as dt

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from scorecard_pipeline.gtfs import FeedDates
from scorecard_pipeline.metrics import (
    COUNT_MULTIPLIER_TIERS,
    WIDESPREAD_MULTIPLIER,
    CategoryResult,
    Finding,
    _count_multiplier,
    correctness,
    freshness,
)
from scorecard_pipeline.rt import RT_KINDS, RtSample, RtWindow, realtime
from scorecard_pipeline.rt_drift import DriftStats, PlausibilityStats
from scorecard_pipeline.score import (
    _OPERATIONAL_CODES,
    CATEGORY_WEIGHTS,
    build_scorecard,
    letter_grade,
    published_overall,
)
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

# Bounded profile: enough examples to explore, small enough for `make verify`.
# deadline=None because per-example wall-clock varies across CI machines. The
# autouse isolated_repo_root fixture only sets an env var and is identical
# across examples, so the function-scoped-fixture health check is a false
# alarm here and is suppressed.
settings.register_profile(
    "scorecard",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("scorecard")

TODAY = dt.date(2026, 6, 11)


# --------------------------------------------------------------- strategies


def _report(groups: list[NoticeGroup]) -> ValidationReport:
    return ValidationReport(validator_version="8.0.1", notices=groups)


notice_groups: st.SearchStrategy[NoticeGroup] = st.builds(
    NoticeGroup,
    code=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=24),
    severity=st.sampled_from(("ERROR", "WARNING", "INFO")),
    total=st.integers(min_value=1, max_value=5000),
)

reports: st.SearchStrategy[ValidationReport] = st.builds(
    _report, st.lists(notice_groups, max_size=10)
)


def _dates(days_until_expiry: int, with_feed_info_dates: bool) -> FeedDates:
    """FeedDates expiring `days_until_expiry` days after TODAY."""
    end = TODAY + dt.timedelta(days=days_until_expiry)
    return FeedDates(
        has_feed_info=with_feed_info_dates,
        feed_publisher_name="Test",
        feed_version="v1",
        feed_start_date=dt.date(2020, 1, 1) if with_feed_info_dates else None,
        feed_end_date=end if with_feed_info_dates else None,
        last_service_date=end,
    )


_TRIP_IDS = ("t1", "t2", "t3", "t4", "t5")

rt_samples: st.SearchStrategy[RtSample] = st.builds(
    RtSample,
    kind=st.sampled_from(RT_KINDS),
    fetched_at=st.integers(min_value=1_750_000_000, max_value=1_750_000_600),
    ok=st.booleans(),
    header_timestamp=st.none() | st.integers(min_value=1_749_990_000, max_value=1_750_001_000),
    entity_count=st.integers(min_value=0, max_value=50),
    trip_ids=st.frozensets(st.sampled_from(_TRIP_IDS), max_size=5),
)

rt_windows: st.SearchStrategy[RtWindow] = st.builds(
    RtWindow, samples=st.lists(rt_samples, max_size=9)
)

drift_stats: st.SearchStrategy[DriftStats | None] = st.none() | st.builds(
    DriftStats,
    observations=st.integers(min_value=1, max_value=500),
    median_seconds=st.integers(min_value=-3600, max_value=3600),
    p90_abs_seconds=st.integers(min_value=0, max_value=7200),
    on_time_share=st.floats(min_value=0.0, max_value=1.0),
)

plausibility_stats: st.SearchStrategy[PlausibilityStats | None] = st.none() | st.builds(
    PlausibilityStats,
    vehicles_checked=st.integers(min_value=1, max_value=200),
    plausible_share=st.floats(min_value=0.0, max_value=1.0),
    worst_meters=st.integers(min_value=0, max_value=100_000),
)


# ------------------------------------------------------------- monotonicity


@given(report=reports, extra=notice_groups)
def test_adding_a_notice_never_raises_correctness(
    report: ValidationReport, extra: NoticeGroup
) -> None:
    """More problems can never mean a better correctness score."""
    before = correctness(report).score
    after = correctness(_report([*report.notices, extra])).score
    assert after <= before


@given(
    d1=st.integers(min_value=-800, max_value=800),
    d2=st.integers(min_value=-800, max_value=800),
    with_dates=st.booleans(),
)
def test_more_runway_never_lowers_fixed_freshness(d1: int, d2: int, with_dates: bool) -> None:
    """For fixed-route service, more days until expiry never scores worse.

    Restricted to service_type="fixed" on purpose: the seasonal/on-demand
    reframing floors a recently lapsed calendar at 50, which is deliberately
    non-monotonic around expiry day (metrics.freshness docstring).
    """
    lo, hi = sorted((d1, d2))
    score_lo = freshness(_dates(lo, with_dates), TODAY).score
    score_hi = freshness(_dates(hi, with_dates), TODAY).score
    assert score_lo <= score_hi


# ------------------------------------------------------------------- bounds


@given(report=reports)
def test_correctness_score_bounded_and_deductions_non_negative(
    report: ValidationReport,
) -> None:
    result = correctness(report)
    assert 0.0 <= result.score <= 100.0
    assert all(f.deduction >= 0.0 for f in result.findings)


@given(
    days=st.none() | st.integers(min_value=-1500, max_value=1500),
    service_type=st.sampled_from(("fixed", "seasonal", "demand_response")),
    with_dates=st.booleans(),
)
def test_freshness_score_bounded_and_deductions_non_negative(
    days: int | None, service_type: str, with_dates: bool
) -> None:
    if days is None:
        dates = FeedDates(False, None, None, None, None, None)  # no expiry knowable
    else:
        dates = _dates(days, with_dates)
    result = freshness(dates, TODAY, service_type=service_type)
    assert 0.0 <= result.score <= 100.0
    assert all(f.deduction >= 0.0 for f in result.findings)


@given(
    window=rt_windows,
    scheduled=st.none() | st.sets(st.sampled_from(_TRIP_IDS), max_size=5),
    drift=drift_stats,
    plausibility=plausibility_stats,
)
def test_realtime_score_bounded_and_deductions_non_negative(
    window: RtWindow,
    scheduled: set[str] | None,
    drift: DriftStats | None,
    plausibility: PlausibilityStats | None,
) -> None:
    """The realtime component weighting stays in [0,100] for any window shape,
    including windows where components drop out and renormalize."""
    result = realtime(window, scheduled, drift=drift, plausibility=plausibility)
    assert 0.0 <= result.score <= 100.0
    assert all(f.deduction >= 0.0 for f in result.findings)


# --------------------------------------------------------- grade-band ladder


@given(
    a=st.floats(min_value=0.0, max_value=100.0),
    b=st.floats(min_value=0.0, max_value=100.0),
)
def test_letter_grade_is_total_and_order_preserving(a: float, b: float) -> None:
    """Every score in [0,100] gets a letter, and a higher score never gets a
    worse letter than a lower one."""
    rank = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    assert letter_grade(a) in rank
    lo, hi = min(a, b), max(a, b)
    assert rank[letter_grade(hi)] >= rank[letter_grade(lo)]


# ------------------------------------------------------- renormalization


@given(
    scores=st.dictionaries(
        st.sampled_from(sorted(CATEGORY_WEIGHTS)),
        st.floats(min_value=0.0, max_value=100.0),
        min_size=1,
    )
)
def test_overall_lies_within_measured_category_scores(scores: dict[str, float]) -> None:
    """Renormalized weighting is a convex combination: the overall score can
    never leave the [min, max] envelope of the measured categories, and the
    carried grade always matches the ladder for the score that gets published.

    The ladder is applied to the published score, not the raw one. Hypothesis
    finds the difference on its own: correctness 67.625, freshness 1.75,
    completeness 67.625, realtime 95.25 weights out to 59.97..., which prints
    as 60.0. The published bands make 60 a D, and grading the raw value called
    it an F -- the exact defect that put "Grade F * 60.0 / 100" on Reseau Stan,
    Ukmerge and Vilnius District.
    """
    card = build_scorecard(
        [CategoryResult(name=name, score=score, summary="") for name, score in scores.items()]
    )
    values = list(scores.values())
    assert min(values) - 1e-9 <= card.overall_score <= max(values) + 1e-9
    published = published_overall(card.overall_score)
    assert card.grade == published["grade"] == letter_grade(published["score"])
    # And what to_json actually emits agrees with it, which is what a reader sees.
    assert card.to_json()["overall"] == published


# --------------------------------------------------------- fix priority


def _finding(code: str, severity: str, count: int, deduction: float) -> Finding:
    return Finding(
        code=code,
        severity=severity,
        count=count,
        what="w",
        why="y",
        fix="f",
        effort="e",
        deduction=deduction,
    )


@given(
    op_code=st.sampled_from(_OPERATIONAL_CODES),
    op_count=st.integers(min_value=1, max_value=10),
    op_deduction=st.floats(min_value=0.1, max_value=20.0),
    warn_count=st.integers(min_value=1, max_value=100_000),
    warn_deduction=st.floats(min_value=0.1, max_value=100.0),
)
def test_operational_codes_always_outrank_tier1_warnings(
    op_code: str,
    op_count: int,
    op_deduction: float,
    warn_count: int,
    warn_deduction: float,
) -> None:
    """A tier-0 operational finding (broken/expiring feed) is always the top
    fix, no matter how many points or instances a tier-1 warning carries."""
    operational = _finding(op_code, "WARNING", op_count, op_deduction)
    warning = _finding("very_widespread_warning", "WARNING", warn_count, warn_deduction)
    card = build_scorecard(
        [CategoryResult(name="freshness", score=50.0, summary="", findings=[warning, operational])]
    )
    assert card.top_fixes[0].code == op_code


# ------------------------------------------------------- count multiplier


@given(total=st.integers(min_value=1, max_value=100_000))
def test_count_multiplier_non_decreasing_and_bounded(total: int) -> None:
    at_total = _count_multiplier(total)
    one_more = _count_multiplier(total + 1)
    assert at_total <= one_more
    assert COUNT_MULTIPLIER_TIERS[0][1] <= at_total <= WIDESPREAD_MULTIPLIER


def test_count_multiplier_matches_published_tier_boundaries() -> None:
    """Each published tier applies from just above the previous threshold
    through its own threshold inclusive; past the last tier it is the
    open-ended widespread multiplier. Derived from COUNT_MULTIPLIER_TIERS
    itself so the test cannot drift from what score.methodology() publishes."""
    previous_threshold = 0
    for threshold, multiplier in COUNT_MULTIPLIER_TIERS:
        assert _count_multiplier(previous_threshold + 1) == multiplier
        assert _count_multiplier(threshold) == multiplier
        previous_threshold = threshold
    assert _count_multiplier(previous_threshold + 1) == WIDESPREAD_MULTIPLIER
