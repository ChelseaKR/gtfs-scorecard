"""Tests for plain-language notice translations."""

from __future__ import annotations

from scorecard_pipeline.notices import RULES_URL, TRANSLATIONS, translate

# Every code the pilot feeds (Unitrans, Yolobus, 2026-06-11) actually surfaced
# must have a curated translation — no generic fallbacks in the live demo.
PILOT_OBSERVED_CODES = [
    "unused_shape",
    "stop_without_stop_time",
    "expired_calendar",
    "service_has_no_active_day_of_the_week",
    "trip_coverage_not_active_for_next7_days",
    "unknown_column",
    "mixed_case_recommended_field",
    "missing_recommended_file",
]


def test_pilot_observed_codes_are_curated() -> None:
    missing = [c for c in PILOT_OBSERVED_CODES if c not in TRANSLATIONS]
    assert not missing, f"add curated translations for: {missing}"


def test_curated_entries_are_complete() -> None:
    for code, t in TRANSLATIONS.items():
        for part in (t.what, t.why, t.fix, t.effort):
            assert part.strip(), f"{code} has an empty translation field"


def test_fallback_is_readable_and_links_rules() -> None:
    t = translate("some_future_notice_code")
    assert "Some future notice code" in t.what
    assert RULES_URL in t.fix


def test_non_ascii_identifier_guidance_preserves_rider_facing_language() -> None:
    t = translate("non_ascii_or_non_printable_char")

    assert "valid UTF-8 data" in t.why
    assert "support in older apps" in t.why
    assert "original language" in t.fix
    assert "internal IDs" in t.what
