"""Frozen mini-corpus canary: exact grades for ten representative feeds (FIX-05).

Each entry is a small frozen input (validator report + feed dates; two entries
add a synthetic realtime window) scored end-to-end through build_scorecard.
The expected overall score and letter grade are asserted as literals, so a
change to any deduction constant, weight, band, or the renormalization shows
up here as an exact diff — a cheap cross-module regression canary.

One entry ("unitrans-trimmed") scores the repo's real trimmed feed fixture;
the rest freeze the report/date shapes the pipeline actually produces, spanning
every grade band. If a rubric change is intentional, update these literals in
the same commit and prepend a METHODOLOGY_CHANGELOG entry (score.py).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.gtfs import FeedDates, read_feed_dates
from scorecard_pipeline.metrics import CategoryResult, correctness
from scorecard_pipeline.metrics import freshness as _freshness_maybe
from scorecard_pipeline.rt import RtSample, RtWindow, realtime
from scorecard_pipeline.rt_drift import PlausibilityStats
from scorecard_pipeline.score import Scorecard, build_scorecard
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
FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"


def _report(*groups: NoticeGroup) -> ValidationReport:
    return ValidationReport(validator_version="8.0.1", notices=list(groups))


def _dates(days_until_expiry: int, with_feed_info_dates: bool = True) -> FeedDates:
    end = TODAY + dt.timedelta(days=days_until_expiry)
    return FeedDates(
        has_feed_info=with_feed_info_dates,
        feed_publisher_name="Test",
        feed_version="v1",
        feed_start_date=dt.date(2026, 1, 1) if with_feed_info_dates else None,
        feed_end_date=end if with_feed_info_dates else None,
        last_service_date=end,
    )


def _rt_sample(
    kind: str,
    ok: bool = True,
    lag: int | None = 30,
    trip_ids: frozenset[str] | None = None,
) -> RtSample:

    fetched = 1_760_000_000
    return RtSample(
        kind=kind,
        fetched_at=fetched,
        ok=ok,
        header_timestamp=None if lag is None else fetched - lag,
        entity_count=len(trip_ids or frozenset()),
        trip_ids=trip_ids or frozenset(),
        error=None if ok else "connection refused",
    )


def _corpus() -> dict[str, Scorecard]:
    """Ten frozen feeds, deterministic by construction (no clock, no network)."""
    cards: dict[str, Scorecard] = {}

    # 1. The rare clean feed: no notices, 90 days of runway.
    cards["clean-long-runway"] = build_scorecard(
        [correctness(_report()), freshness(_dates(90), TODAY)]
    )

    # 2. The real trimmed Unitrans snapshot, scored on its snapshot day
    #    (52 days of runway; freshness is the only measured category).
    cards["unitrans-trimmed"] = build_scorecard([freshness(read_feed_dates(str(FIXTURE)), TODAY)])

    # 3. A typical decent feed: two warning codes, 45 days of runway.
    cards["few-warnings"] = build_scorecard(
        [
            correctness(
                _report(
                    NoticeGroup("missing_trip_headsign", "WARNING", 3),
                    NoticeGroup("unused_stop", "WARNING", 12),
                )
            ),
            freshness(_dates(45), TODAY),
        ]
    )

    # 4. A feed in real trouble: three error codes across the count tiers,
    #    10 days from expiry.
    cards["errors-near-expiry"] = build_scorecard(
        [
            correctness(
                _report(
                    NoticeGroup("unusable_trip", "ERROR", 1),
                    NoticeGroup("stop_without_location", "ERROR", 7),
                    NoticeGroup("missing_required_file", "ERROR", 60),
                )
            ),
            freshness(_dates(10), TODAY),
        ]
    )

    # 5. Clean data whose calendar already ran out (fixed-route: hard zero).
    cards["expired-fixed"] = build_scorecard(
        [correctness(_report()), freshness(_dates(-30), TODAY)]
    )

    # 6. The same lapse declared seasonal: reframed and floored, not zeroed.
    cards["lapsed-seasonal"] = build_scorecard(
        [correctness(_report()), freshness(_dates(-30), TODAY, service_type="seasonal")]
    )

    # 7. No expiry date anywhere in the feed.
    cards["no-expiry-date"] = build_scorecard(
        [
            correctness(_report(NoticeGroup("missing_agency_phone", "WARNING", 1))),
            freshness(FeedDates(False, None, None, None, None, None), TODAY),
        ]
    )

    # 8. Long runway but feed_info.txt lacks its validity dates (-15).
    cards["missing-feed-info-dates"] = build_scorecard(
        [correctness(_report()), freshness(_dates(90, with_feed_info_dates=False), TODAY)]
    )

    # 9. Healthy realtime: all three feeds up, 30s lag, full trip coverage,
    #    every sampled vehicle on its route.
    healthy_window = RtWindow(
        samples=[
            _rt_sample("trip_updates", trip_ids=frozenset({"t1", "t2"})),
            _rt_sample("vehicle_positions"),
            _rt_sample("service_alerts", lag=None),
        ]
    )
    cards["realtime-healthy"] = build_scorecard(
        [
            correctness(_report()),
            freshness(_dates(90), TODAY),
            realtime(
                healthy_window,
                {"t1", "t2"},
                plausibility=PlausibilityStats(
                    vehicles_checked=12, plausible_share=1.0, worst_meters=8
                ),
            ),
        ]
    )

    # 10. Degraded realtime: vehicle positions down, 330s lag, half the
    #     scheduled trips missing, 2 of 10 vehicles off route — plus a
    #     middling static feed.
    degraded_window = RtWindow(
        samples=[
            _rt_sample("trip_updates", lag=330, trip_ids=frozenset({"t1", "t2"})),
            _rt_sample("vehicle_positions", ok=False, lag=None),
            _rt_sample("service_alerts", lag=None),
        ]
    )
    cards["realtime-degraded"] = build_scorecard(
        [
            correctness(
                _report(
                    NoticeGroup("unusable_trip", "ERROR", 1),
                    NoticeGroup("unused_stop", "WARNING", 60),
                )
            ),
            freshness(_dates(40), TODAY),
            realtime(
                degraded_window,
                {"t1", "t2", "t3", "t4"},
                plausibility=PlausibilityStats(
                    vehicles_checked=10, plausible_share=0.8, worst_meters=1200
                ),
            ),
        ]
    )

    return cards


# Frozen published fields. These are literals on purpose: adding artifact
# metadata must not move an overall/category score, grade, or top-fix ordering.
# Do not compute them from rubric constants, or the canary would drift with the
# change it exists to catch.
EXPECTED: dict[str, tuple[float, str]] = {
    "clean-long-runway": (100.0, "A"),
    "unitrans-trimmed": (86.7, "B"),
    "few-warnings": (84.5, "B"),
    "errors-near-expiry": (35.3, "F"),
    "expired-fixed": (63.6, "D"),
    "lapsed-seasonal": (81.8, "B"),
    "no-expiry-date": (61.1, "D"),
    "missing-feed-info-dates": (94.5, "A"),
    "realtime-healthy": (100.0, "A"),
    "realtime-degraded": (70.8, "C"),
}

EXPECTED_CATEGORY_SCORES: dict[str, dict[str, float]] = {
    "clean-long-runway": {"correctness": 100.0, "freshness": 100.0},
    "unitrans-trimmed": {"freshness": 86.7},
    "few-warnings": {"correctness": 90.0, "freshness": 75.0},
    "errors-near-expiry": {"correctness": 46.0, "freshness": 16.7},
    "expired-fixed": {"correctness": 100.0, "freshness": 0.0},
    "lapsed-seasonal": {"correctness": 100.0, "freshness": 50.0},
    "no-expiry-date": {"correctness": 96.0, "freshness": 0.0},
    "missing-feed-info-dates": {"correctness": 100.0, "freshness": 85.0},
    "realtime-healthy": {"correctness": 100.0, "freshness": 100.0, "realtime": 100.0},
    "realtime-degraded": {"correctness": 80.0, "freshness": 66.7, "realtime": 58.7},
}

EXPECTED_TOP_FIX_CODES: dict[str, list[str]] = {
    "clean-long-runway": [],
    "unitrans-trimmed": [],
    "few-warnings": ["unused_stop", "missing_trip_headsign"],
    "errors-near-expiry": [
        "scorecard_feed_expiring_soon",
        "missing_required_file",
        "stop_without_location",
    ],
    "expired-fixed": ["scorecard_feed_expired"],
    "lapsed-seasonal": ["scorecard_intermittent_calendar_ended"],
    "no-expiry-date": ["scorecard_no_expiry_date", "missing_agency_phone"],
    "missing-feed-info-dates": ["scorecard_missing_feed_info_dates"],
    "realtime-healthy": [],
    "realtime-degraded": [
        "unusable_trip",
        "scorecard_rt_vehicle_positions_unreachable",
        "scorecard_rt_trip_coverage",
    ],
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_corpus_feed_scores_exactly_as_frozen(name: str) -> None:
    card = _corpus()[name]
    published = card.to_json()
    expected_score, expected_grade = EXPECTED[name]
    assert published["overall"]["score"] == expected_score
    assert published["overall"]["grade"] == expected_grade
    measured_category_scores = {
        category: payload["score"]
        for category, payload in published["categories"].items()
        if payload["status"] == "measured"
    }
    assert measured_category_scores == EXPECTED_CATEGORY_SCORES[name]
    assert [fix["code"] for fix in published["top_fixes"]] == EXPECTED_TOP_FIX_CODES[name]


def test_corpus_and_expectations_cover_the_full_grade_ladder() -> None:
    cards = _corpus()
    assert sorted(cards) == sorted(EXPECTED)
    assert sorted(cards) == sorted(EXPECTED_CATEGORY_SCORES)
    assert sorted(cards) == sorted(EXPECTED_TOP_FIX_CODES)
    assert {grade for _, grade in EXPECTED.values()} == {"A", "B", "C", "D", "F"}
    # The most urgent corpus entry surfaces the operational fix first.
    assert cards["expired-fixed"].top_fixes[0].code == "scorecard_feed_expired"
