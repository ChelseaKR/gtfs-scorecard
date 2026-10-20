"""Program rollup search snippets: bounded, singular-aware, and honest about counts."""

from scorecard_pipeline.render_site import _DESC_MAX, _rollup_description


def test_plural_with_attention() -> None:
    assert _rollup_description("Kansas agencies", 4, 3) == (
        "Kansas agencies: GTFS grades for 4 transit feeds, 3 needing attention, "
        "plus the fixes they share."
    )


def test_singular_and_none_needing_attention() -> None:
    text = _rollup_description("Yolo County", 1, 0)
    assert "1 transit feed," in text
    assert "none needing attention" in text


def test_longest_realistic_name_fits_the_description_bound() -> None:
    text = _rollup_description("District of Columbia agencies", 99999, 99999)
    assert len(text) <= _DESC_MAX
