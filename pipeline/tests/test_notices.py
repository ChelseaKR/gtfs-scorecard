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


# The most common untranslated validator notices across the scored corpus
# (feeds-affected, from a scan of data/artifacts/*/latest.json). Each must
# resolve to a curated translation, not the generic auto-humanized fallback.
CORPUS_TOP_UNTRANSLATED_CODES = [
    "unknown_file",
    "service_window_outside_feed_period",
    "missing_feed_contact_email_and_url",
    "stop_too_far_from_shape_using_user_distance",
    "big_gap_in_service",
    "missing_required_column",
    "equal_shape_distance_same_coordinates",
    "trip_distance_exceeds_shape_distance_below_threshold",
    "route_long_name_contains_short_name",
    "stops_match_shape_out_of_order",
    "leading_or_trailing_whitespaces",
    "trip_headsign_matches_intermediate_stop",
]


def test_corpus_top_codes_are_curated_not_fallback() -> None:
    for code in CORPUS_TOP_UNTRANSLATED_CODES:
        assert code in TRANSLATIONS, f"missing curated translation for {code}"
        t = translate(code)
        # The fallback marks its what with this parenthetical and sends the
        # reader to the rules page; a curated entry does neither.
        assert "flagged by the MobilityData validator" not in t.what, code
        assert RULES_URL not in t.fix, code
        assert t is TRANSLATIONS[code], code


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


def test_every_published_fix_page_has_a_curated_translation() -> None:
    """A written fix guide implies the plain language exists, so the scorecard must use it.

    Three codes shipped a fix page in `docs/fixes/` with no entry in TRANSLATIONS, so every
    scorecard rendered the generic "flagged by the MobilityData validator" fallback for them while
    the plain-language wording sat finished one directory away. One of the three,
    `missing_timepoint_value`, accounted for 58.4% of all finding instances in the national corpus
    -- the single line agencies saw most often was the one this table exists to replace.

    The gap was invisible because nothing connected the two surfaces: adding a fix page and adding
    a translation were separate acts with no check that they agreed. This is that check.
    """
    from pathlib import Path

    fixes_dir = Path(__file__).resolve().parents[2] / "docs" / "fixes"
    assert fixes_dir.is_dir(), f"expected fix guides at {fixes_dir}"

    # `scorecard_*` pages document this project's own checks, which are generated in the pipeline
    # with their own wording (see metrics.py, completeness.py) and never pass through TRANSLATIONS.
    # Only MobilityData validator codes belong to this table.
    documented = {
        p.stem
        for p in fixes_dir.glob("*.md")
        if not p.stem.startswith("scorecard_") and p.stem not in {"index", "README"}
    }
    assert documented, "no validator fix pages found; this test would pass vacuously"

    missing = sorted(documented - set(TRANSLATIONS))
    assert not missing, (
        "these codes have a published fix page but no curated translation, so the scorecard "
        f"shows the generic fallback for them: {missing}"
    )
