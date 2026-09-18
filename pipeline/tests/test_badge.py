"""Tests for the embeddable SVG grade badge."""

from __future__ import annotations

from scorecard_pipeline.badge import render_badge


def test_badge_is_svg_with_accessible_title() -> None:
    svg = render_badge("B", 84.0)
    assert svg.startswith("<svg")
    assert 'role="img"' in svg
    assert "<title>GTFS quality: B 84</title>" in svg
    assert 'aria-label="GTFS quality: B 84"' in svg


def test_badge_without_score_shows_letter_only() -> None:
    svg = render_badge("A")
    assert ">A<" in svg
    assert "<title>GTFS quality: A</title>" in svg


def test_distinct_grades_get_distinct_colors() -> None:
    colors = {g: render_badge(g) for g in "ABCDF"}
    # the second fill in each badge is the grade-colored segment
    fills = {g: svg.split('fill="')[2].split('"')[0] for g, svg in colors.items()}
    assert len(set(fills.values())) == 5


def test_unknown_grade_falls_back() -> None:
    svg = render_badge("?", None)
    assert "<svg" in svg  # does not raise


def test_expired_badge_appends_status_segment() -> None:
    svg = render_badge("F", 30.0, expiry_status="stale")
    assert "feed expired" in svg
    assert "<title>GTFS quality: F 30 (feed expired)</title>" in svg
    assert 'aria-label="GTFS quality: F 30 (feed expired)"' in svg


def test_expiring_soon_badge_shows_warning_text() -> None:
    svg = render_badge("C", 72.0, expiry_status="expiring_soon")
    assert "expires soon" in svg


def test_current_feed_badge_has_no_status_segment() -> None:
    svg = render_badge("A", 95.0, expiry_status="current")
    assert "feed expired" not in svg
    assert "expires soon" not in svg
    assert "<title>GTFS quality: A 95</title>" in svg
