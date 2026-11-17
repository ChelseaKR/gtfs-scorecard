"""ADR 0078: half the agency pages name the source feed URL in their search copy.

The split is a hash of the agency id. A page gets the test copy only when it
is in the test half, renders a "Source feed" link and shows a grade. Guarded
here: the split is stable and close to half; the copy matches the approved
wording; the control half renders exactly as it would without the test; and a
page that links no source never names one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _SEARCH_INTENT_COPY,
    _agency_seo_metadata,
    _plan_agency_seo_metadata,
    _source_shown_ids,
    _source_title_test_ids,
    _source_withheld,
    source_title_test_arm,
)

_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "directory.json"
_FACTS = ("C", "75.2", "2026-11-17")


def _artifact(grade: str | None = "C", rt: str = "not_yet_measured") -> dict[str, Any]:
    return {
        "overall": {"grade": grade, "score": 75.2},
        "snapshot_date": "2026-11-17",
        "categories": {"realtime": {"status": rt}},
    }


def _ids(arm: bool, count: int, prefix: str = "agency") -> list[str]:
    found: list[str] = []
    n = 0
    while len(found) < count:
        candidate = f"{prefix}-{n}"
        if source_title_test_arm(candidate) is arm and candidate not in _SEARCH_INTENT_COPY:
            found.append(candidate)
        n += 1
    return found


def _records(ids: list[str]) -> list[dict[str, Any]]:
    return [
        {"id": agency_id, "name": f"Transit {agency_id}", "state": "IA", "country": "US"}
        for agency_id in ids
    ]


# --- the split ------------------------------------------------------------


def test_the_split_is_a_stable_hash_of_the_id() -> None:
    # Pinned so a refactor cannot reshuffle the halves mid-test. These are the
    # README's examples; flipping any of them would end the experiment.
    assert source_title_test_arm("king-county-metro") is True
    assert source_title_test_arm("golden-gate-transit") is True
    assert source_title_test_arm("unitrans") is True
    assert source_title_test_arm("yolobus") is False
    assert all(source_title_test_arm("unitrans") for _ in range(5))


@pytest.mark.skipif(not _DIRECTORY.exists(), reason="published directory not in this checkout")
def test_the_split_puts_about_half_the_published_records_in_each_arm() -> None:
    ids = [str(r["id"]) for r in json.loads(_DIRECTORY.read_text())["agencies"]]
    share = sum(source_title_test_arm(agency_id) for agency_id in ids) / len(ids)
    assert 0.45 <= share <= 0.55


# --- the copy -------------------------------------------------------------


def test_test_copy_matches_the_approved_wording() -> None:
    meta = _agency_seo_metadata(
        "Burlington Urban Service",
        location_label="Iowa",
        grade_facts=_FACTS,
        source_feed_copy=True,
    )
    assert meta.title == "Burlington Urban Service (Iowa) GTFS feed: URL, grade, fixes"
    assert meta.description == (
        "Burlington Urban Service (Iowa) GTFS feed: grade C, 75.2 of 100, checked "
        "2026-11-17. Source feed URL, validator findings, service dates and fixes."
    )
    long_suffix = _agency_seo_metadata(
        "Metra", location_label="Illinois", grade_facts=_FACTS, source_feed_copy=True
    )
    assert long_suffix.title == "Metra (Illinois) GTFS feed: source URL, grade and fixes"
    short_suffix = _agency_seo_metadata(
        "Golden Gate Transit",
        location_label="California",
        grade_facts=_FACTS,
        source_feed_copy=True,
    )
    assert short_suffix.title == "Golden Gate Transit (California) GTFS feed URL and grade"


def test_test_copy_names_realtime_only_when_it_was_measured() -> None:
    meta = _agency_seo_metadata(
        "Metra", grade_facts=_FACTS, rt_measured=True, source_feed_copy=True
    )
    assert meta.description.endswith(
        "Source feed URL, validator findings, service dates, realtime and fixes."
    )


def test_test_title_says_grade_but_never_carries_one() -> None:
    meta = _agency_seo_metadata(
        "Metra",
        location_label="Illinois",
        grade_facts=("F", "37.7", "2026-10-02"),
        source_feed_copy=True,
    )
    assert "37.7" not in meta.title
    assert not re.search(r"\bgrade [A-F]\b", meta.title)


def test_long_names_keep_the_control_fallbacks() -> None:
    name = "Luxembourg national transport"
    control = _agency_seo_metadata(name, location_label="Luxembourg", grade_facts=_FACTS)
    test = _agency_seo_metadata(
        name, location_label="Luxembourg", grade_facts=_FACTS, source_feed_copy=True
    )
    assert (
        test.title
        == control.title
        == "Luxembourg national transport (Luxembourg) GTFS feed quality"
    )
    # The whole name stays in the description; the longer tail is dropped instead.
    assert test.description.startswith(f"{name} (Luxembourg) GTFS feed:")
    assert test.description.endswith("See the findings and fixes.")


def test_no_grade_means_no_test_copy() -> None:
    # The test title says "grade", so a page with no grade keeps the control copy.
    control = _agency_seo_metadata("Metra", location_label="Illinois")
    asked = _agency_seo_metadata("Metra", location_label="Illinois", source_feed_copy=True)
    assert asked == control


# --- who gets it ----------------------------------------------------------


def test_only_test_half_pages_with_a_source_link_and_a_grade_qualify() -> None:
    test_ids = _ids(True, 3)
    control_ids = _ids(False, 2)
    artifacts = {i: _artifact() for i in test_ids + control_ids}
    artifacts[test_ids[2]] = _artifact(grade=None)
    shown = {test_ids[0], test_ids[2], *control_ids}
    chosen = _source_title_test_ids(test_ids + control_ids, artifacts, shown)
    # test_ids[1] links no source; test_ids[2] shows no grade; controls never.
    assert chosen == frozenset({test_ids[0]})


def test_search_intent_pages_are_in_neither_half() -> None:
    artifacts = {agency_id: _artifact() for agency_id in _SEARCH_INTENT_COPY}
    assert (
        _source_title_test_ids(_SEARCH_INTENT_COPY, artifacts, set(_SEARCH_INTENT_COPY))
        == frozenset()
    )


def test_planner_changes_only_qualifying_test_pages() -> None:
    from scorecard_pipeline.config import AGENCIES

    ids = _ids(True, 4) + _ids(False, 4)
    records = _records(ids)
    artifacts = {i: _artifact() for i in ids}
    without = _plan_agency_seo_metadata(records, artifacts, AGENCIES)
    shown = set(ids) - {ids[3]}
    with_test = _plan_agency_seo_metadata(records, artifacts, AGENCIES, source_shown=shown)
    for agency_id in ids[4:]:
        # The control half is byte-identical to a render without the test.
        assert with_test[agency_id] == without[agency_id]
    for agency_id in ids[:3]:
        meta = with_test[agency_id]
        assert "URL" in meta.title
        assert "Source feed URL" in meta.description
        assert meta.title.startswith(meta.identity)
        # The clearance log and the Dataset name are not part of the test.
        assert meta.clearance_title == without[agency_id].clearance_title
        assert meta.dataset_name == without[agency_id].dataset_name
    # In the test half but no source link on the page: no source wording.
    assert with_test[ids[3]] == without[ids[3]]


def test_a_test_page_that_would_collide_keeps_its_planned_copy() -> None:
    from scorecard_pipeline.config import AGENCIES

    first, second = _ids(True, 2)
    # Same name and place: the planner disambiguates them, and the test copy
    # is rebuilt with the same qualifier, so the two stay distinct.
    records = [
        {"id": first, "name": "Twin Transit", "state": "IA", "country": "US"},
        {"id": second, "name": "Twin Transit", "state": "IA", "country": "US"},
    ]
    artifacts = {first: _artifact(), second: _artifact()}
    planned = _plan_agency_seo_metadata(records, artifacts, AGENCIES, source_shown={first, second})
    titles = {m.title.casefold() for m in planned.values()}
    descriptions = {m.description.casefold() for m in planned.values()}
    assert len(titles) == 2 and len(descriptions) == 2


def test_an_unreadable_opt_out_ledger_withholds_every_source() -> None:
    assert _source_withheld("unitrans", None, None) is True
    assert _source_withheld("unitrans", frozenset({"unitrans"}), None) is True
    assert _source_withheld("unitrans", frozenset(), None) is False


def test_source_shown_follows_the_page_link_rule() -> None:
    public = {"feed": {"static_url": "https://example.org/gtfs.zip"}}
    keyed = {"feed": {"static_url": "https://example.org/gtfs.zip?api_key=REDACTED"}}
    local = {"feed": {"static_url": "gtfs.zip"}}
    artifacts = {"open": public, "keyed": keyed, "local": local, "opted-out": public}
    shown = _source_shown_ids(artifacts, frozenset({"opted-out"}), {})
    assert shown == frozenset({"open"})
    # An unreadable ledger withholds every link, so no page gets the test copy.
    assert _source_shown_ids(artifacts, None, {}) == frozenset()


@pytest.mark.skipif(not _DIRECTORY.exists(), reason="published directory not in this checkout")
def test_every_published_record_fits_with_the_test_copy() -> None:
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
    every_id = {str(r["id"]) for r in records}
    planned = _plan_agency_seo_metadata(records, artifacts, AGENCIES, source_shown=every_id)
    assert all(15 <= len(m.title) <= 60 for m in planned.values())
    assert all(50 <= len(m.description) <= 155 for m in planned.values())
    assert len({m.title.casefold() for m in planned.values()}) == len(planned)
    assert len({m.description.casefold() for m in planned.values()}) == len(planned)
    control = _plan_agency_seo_metadata(records, artifacts, AGENCIES)
    in_arm = [i for i in every_id if source_title_test_arm(i)]
    # Most of the test half gets the new title; zero would mean the test never ran.
    assert sum("URL" in planned[i].title for i in in_arm) > len(in_arm) // 2
    assert sum("Source feed URL" in planned[i].description for i in in_arm) > 0
    # The test never cuts a name in a description that the control shows whole.
    assert not [
        i for i in in_arm if planned[i].description.count("…") > control[i].description.count("…")
    ]
    # And the control half is untouched.
    assert all(planned[i] == control[i] for i in every_id - set(in_arm))
