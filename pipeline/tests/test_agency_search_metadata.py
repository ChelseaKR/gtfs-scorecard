"""Search-result metadata for agency pages: titles, descriptions, Dataset JSON-LD.

The titles are written for what people search before landing on an agency
page ("<agency> gtfs", "<agency> gtfs feed"), and the descriptions repeat the
page's own dated headline numbers. Two failure shapes are guarded here:

* a title cut partway through a word when the agency's own short form would fit;
* a description that states a grade the page does not carry, or turns a
  missing grade into a number.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _agency_name_forms,
    _agency_seo_metadata,
    _agency_short_name,
    _derived_page_title,
    _ellipsize_words,
    _plan_agency_seo_metadata,
    _render_agency,
    _render_fixlog_page,
    _seo_grade_facts,
)

_GRADE_CLAUSE = re.compile(r"grade [A-F], [0-9.]+ of 100, checked \d{4}-\d{2}-\d{2}")
_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "directory.json"


def _artifact(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "overall": {"grade": "C", "score": 74.0},
        "snapshot_date": "2026-10-02",
        "categories": {"realtime": {"status": "not_yet_measured"}},
    }
    base.update(overrides)
    return base


def _head(html: str) -> tuple[str, str]:
    title = unescape(html.split("<title>", 1)[1].split("</title>", 1)[0])
    desc = unescape(html.split('<meta name="description" content="', 1)[1].split('">', 1)[0])
    return title, desc


def _jsonld(html: str) -> dict[str, Any]:
    block = html.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    return dict(json.loads(block))


# --- titles ---------------------------------------------------------------


def test_title_names_the_feed_and_never_the_grade() -> None:
    meta = _agency_seo_metadata(
        "Metra", location_label="Illinois", grade_facts=("F", "37.7", "2026-10-02")
    )
    assert meta.title == "Metra (Illinois) GTFS feed: quality report and fixes"
    assert meta.identity == "Metra (Illinois)"
    assert "grade" not in meta.title.lower()
    assert "37.7" not in meta.title


def test_long_name_uses_its_own_short_form_instead_of_a_mid_word_cut() -> None:
    name = "San Francisco Municipal Transportation Agency (SFMTA - Muni)"
    meta = _agency_seo_metadata(name, location_label="California")
    assert meta.title == "SFMTA - Muni (California) GTFS feed quality report"
    assert "…" not in meta.title
    assert len(meta.title) <= 60


def test_long_name_without_a_short_form_is_cut_on_a_word_boundary() -> None:
    # Negative control for the short-form path: with no trailing parenthetical
    # there is nothing to substitute, so the title falls back to a cut, and the
    # cut lands after a whole word.
    name = "San Francisco Municipal Transportation Agency Regional Network"
    assert _agency_short_name(name) == ""
    meta = _agency_seo_metadata(name, location_label="California")
    assert len(meta.title) <= 60
    stem = meta.title.split("…", 1)[0]
    assert "…" in meta.title
    assert name.startswith(stem)
    assert name[len(stem)] == " ", f"cut mid-word: {meta.title!r}"


def test_short_form_requires_a_trailing_parenthetical_with_letters() -> None:
    assert _agency_short_name("Capital Area Transit (GoRaleigh)") == "GoRaleigh"
    # A digits-only parenthetical is never a name form; the outer part is.
    assert _agency_name_forms("Route 66 (2024)") == ["Route 66"]
    assert _agency_name_forms("Orbus (Otago Regional Council)") == [
        "Orbus",
        "Otago Regional Council",
    ]
    assert _agency_name_forms("Nagi Town Bus (なぎバス)") == ["Nagi Town Bus"]
    assert _agency_short_name("Metro (Bus) Service") == ""
    assert _ellipsize_words("Alpha Beta Gamma Delta", 12) == "Alpha Beta…"


def test_disambiguator_stays_in_the_title_ahead_of_the_suffix() -> None:
    meta = _agency_seo_metadata(
        "North County Transit District (NCTD)",
        location_label="California",
        disambiguator="MDB 3093",
    )
    assert "[MDB 3093]" in meta.title
    assert meta.title.startswith(meta.identity)
    assert len(meta.title) <= 60


# --- descriptions ---------------------------------------------------------


def test_description_repeats_the_pages_grade_score_and_date() -> None:
    facts = _seo_grade_facts(_artifact())
    assert facts == ("C", "74.0", "2026-10-02")
    meta = _agency_seo_metadata("Demo Transit", location_label="Oregon", grade_facts=facts)
    assert "grade C, 74.0 of 100, checked 2026-10-02" in meta.description
    assert len(meta.description) <= 155


@pytest.mark.parametrize(
    "overrides",
    [
        {"overall": None},
        {"overall": {"grade": "C"}},
        {"overall": {"grade": "C", "score": None}},
        {"overall": {"grade": "C", "score": True}},
        {"overall": {"grade": "C", "score": 140.0}},
        {"overall": {"grade": "?", "score": 74.0}},
        {"overall": {"grade": "", "score": 0}},
        {"snapshot_date": None},
        {"snapshot_date": "yesterday"},
    ],
)
def test_missing_or_malformed_grade_is_not_published_as_a_value(
    overrides: dict[str, Any],
) -> None:
    artifact = _artifact(**overrides)
    assert _seo_grade_facts(artifact) is None
    meta = _agency_seo_metadata(
        "Demo Transit", location_label="Oregon", grade_facts=_seo_grade_facts(artifact)
    )
    assert not _GRADE_CLAUSE.search(meta.description)
    assert "grade" not in meta.description.lower()
    assert " 0 of 100" not in meta.description
    assert "GTFS feed quality report" in meta.description


def test_grade_clause_detector_is_not_vacuous() -> None:
    # Negative control: the same detector the absence test relies on must fire
    # on a description that does carry a grade, or the test above proves nothing.
    meta = _agency_seo_metadata(
        "Demo Transit", location_label="Oregon", grade_facts=("C", "74.0", "2026-10-02")
    )
    assert _GRADE_CLAUSE.search(meta.description)


def test_rendered_page_head_matches_its_own_hero() -> None:
    html = _render_agency(_artifact(), dir_record={"state": "Oregon"})
    title, desc = _head(html)
    assert title == "Demo Transit (Oregon) GTFS feed: quality report and fixes"
    assert "grade C, 74.0 of 100, checked 2026-10-02" in desc
    # The hero shows the same score and the same check date.
    assert '<span class="score-big">74.0</span>' in html
    assert "checked 2026-10-02" in html


# --- structured data ------------------------------------------------------


def test_dataset_jsonld_is_free_located_and_never_rated() -> None:
    located = _jsonld(_render_agency(_artifact(), dir_record={"state": "Oregon"}))
    assert located["@type"] == "Dataset"
    assert located["isAccessibleForFree"] is True
    assert located["spatialCoverage"] == {"@type": "Place", "name": "Oregon"}
    for forbidden in ("aggregateRating", "review", "reviewRating"):
        assert forbidden not in json.dumps(located)

    unlocated = _jsonld(_render_agency(_artifact()))
    assert "spatialCoverage" not in unlocated


# --- clearance log reuses the planned identity ----------------------------


def test_clearance_log_title_reuses_the_planned_identity() -> None:
    meta = _agency_seo_metadata(
        "San Francisco Municipal Transportation Agency (SFMTA - Muni)",
        location_label="California",
    )
    receipts = [
        {
            "code": "expired_calendar",
            "what": "The old calendar was replaced.",
            "last_seen": "2026-06-30",
            "cleared": "2026-07-01",
        }
    ]
    page = _render_fixlog_page(_artifact(), receipts, seo_metadata=meta)
    title, _desc = _head(page)
    assert title == "SFMTA - Muni (California) GTFS clearance log"


_RECEIPTS = [
    {
        "code": "expired_calendar",
        "what": "The old calendar was replaced.",
        "last_seen": "2026-06-30",
        "cleared": "2026-07-01",
    }
]


def test_clearance_log_title_fits_when_the_identity_leaves_no_room() -> None:
    # Regression: the 2026-10-03 outage. #496 lets the agency title keep this
    # 42-character name whole with the 18-character " GTFS feed quality"
    # suffix, so the old "{identity} GTFS clearance log" came to 61 characters
    # and the render raised, aborting every page on the site.
    meta = _agency_seo_metadata("Athens-Clarke County Transit (ACC Transit)")
    assert meta.title == "Athens-Clarke County Transit (ACC Transit) GTFS feed quality"
    assert len(f"{meta.identity} GTFS clearance log") > 60  # the overflow is real

    page = _render_fixlog_page(_artifact(), _RECEIPTS, seo_metadata=meta)
    title, desc = _head(page)
    assert title == "ACC Transit GTFS clearance log"
    assert len(desc) <= 155
    assert "ACC Transit" in desc

    located = _agency_seo_metadata(
        "Athens-Clarke County Transit (ACC Transit)", location_label="Georgia"
    )
    page = _render_fixlog_page(_artifact(), _RECEIPTS, seo_metadata=located)
    assert _head(page)[0] == "ACC Transit (Georgia) GTFS clearance log"


def test_derived_title_keeps_the_disambiguator_and_cuts_on_a_word() -> None:
    meta = _agency_seo_metadata(
        "Athens-Clarke County Transit (ACC Transit)",
        location_label="Georgia",
        disambiguator="MDB 1234",
    )
    title, identity = _derived_page_title(meta, " GTFS clearance log")
    assert title == "ACC Transit [MDB 1234] GTFS clearance log"
    assert identity == "ACC Transit [MDB 1234]"

    # No shorter form to fall back on: the name is cut on a word boundary,
    # never mid-word, and the title still fits.
    long_name = "Consolidated Metropolitan Regional Transportation Authority District"
    title, _identity = _derived_page_title(_agency_seo_metadata(long_name), " GTFS clearance log")
    assert len(title) <= 60
    assert title.endswith("… GTFS clearance log")
    stem = title.removesuffix("… GTFS clearance log")
    assert long_name.startswith(stem) and long_name[len(stem)] == " "


# --- every real directory record fits -------------------------------------


def _clearance_title(meta: Any) -> str:
    return _head(_render_fixlog_page(_artifact(), _RECEIPTS, seo_metadata=meta))[0]


def _naive_clearance_title(meta: Any) -> str:
    """The pre-fix composition, kept as the negative control's oracle."""
    return f"{meta.identity} GTFS clearance log"


def _overlong_titles(planned: dict[str, Any], title_of: Any) -> list[str]:
    return sorted(agency_id for agency_id, m in planned.items() if len(title_of(m)) > 60)


def _planned_directory() -> dict[str, Any]:
    from scorecard_pipeline.config import AGENCIES

    records = json.loads(_DIRECTORY.read_text())["agencies"]
    artifacts = {
        str(r["id"]): {
            "overall": {"grade": r.get("grade"), "score": r.get("score")},
            "snapshot_date": r.get("snapshot_date"),
            "categories": {"realtime": {"status": "not_yet_measured"}},
        }
        for r in records
    }
    return _plan_agency_seo_metadata(records, artifacts, AGENCIES)


@pytest.mark.skipif(not _DIRECTORY.exists(), reason="published directory not in this checkout")
def test_every_published_record_renders_every_indexed_title_within_budget() -> None:
    # Every indexed page type whose title is built from an agency's identity:
    # the agency page and its clearance log. A record that overflows would
    # have stopped the whole render before this fix.
    planned = _planned_directory()
    assert _overlong_titles(planned, lambda m: m.title) == []
    assert _overlong_titles(planned, _clearance_title) == []
    for meta in planned.values():
        title = _clearance_title(meta)
        assert title.endswith(" GTFS clearance log")
        assert len(title) > len(" GTFS clearance log")
    titles = [_clearance_title(m).casefold() for m in planned.values()]
    assert len(set(titles)) == len(titles)


@pytest.mark.skipif(not _DIRECTORY.exists(), reason="published directory not in this checkout")
def test_negative_control_the_sweep_catches_the_pre_fix_composition() -> None:
    # The sweep above would be a gate that cannot fail if no real record ever
    # reached the overflow case. The pre-fix title composition must trip it.
    overlong = _overlong_titles(_planned_directory(), _naive_clearance_title)
    assert len(overlong) > 0


# --- every real directory record fits -------------------------------------


@pytest.mark.skipif(not _DIRECTORY.exists(), reason="published directory not in this checkout")
def test_every_published_record_gets_bounded_unique_metadata() -> None:
    from scorecard_pipeline.config import AGENCIES

    records = json.loads(_DIRECTORY.read_text())["agencies"]
    artifacts = {
        str(r["id"]): {
            "overall": {"grade": r.get("grade"), "score": r.get("score")},
            "snapshot_date": r.get("snapshot_date"),
            "categories": {"realtime": {"status": "not_yet_measured"}},
        }
        for r in records
    }
    planned = _plan_agency_seo_metadata(records, artifacts, AGENCIES)
    assert len(planned) == len(records)
    assert all(15 <= len(m.title) <= 60 for m in planned.values())
    assert all(50 <= len(m.description) <= 155 for m in planned.values())
    assert len({m.title.casefold() for m in planned.values()}) == len(planned)
    assert all(m.title.startswith(m.identity) for m in planned.values())
    # A grade never reaches a title (agency names such as "Belgrade" aside).
    assert not any(re.search(r"\bgrade\b", m.title, re.I) for m in planned.values())
