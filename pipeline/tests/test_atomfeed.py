"""Tests for the static Atom alert feeds."""

from __future__ import annotations

import datetime as dt
from typing import Any
from xml.etree import ElementTree as ET

from scorecard_pipeline.atomfeed import (
    Entry,
    agency_change_feed,
    render_atom,
    site_change_feed,
)
from scorecard_pipeline.timemachine import Event

_ATOM = "{http://www.w3.org/2005/Atom}"
_BASE = "https://gtfsscorecard.org"


def _entry(eid: str, title: str, day: str, category: str = "grade_drop") -> Entry:
    return Entry(
        id=eid,
        title=title,
        updated=dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC),
        summary="something happened",
        link=f"{_BASE}/agency/x/",
        category=category,
    )


def test_render_atom_is_well_formed_xml() -> None:
    xml = render_atom(
        feed_id="tag:test:feed",
        title="Test feed",
        subtitle="A test",
        self_url=f"{_BASE}/changes/feed.xml",
        alternate_url=f"{_BASE}/changes/",
        entries=[_entry("tag:test:1", "First", "2026-06-12")],
    )
    root = ET.fromstring(xml)
    assert root.tag == f"{_ATOM}feed"
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 1
    assert entries[0].find(f"{_ATOM}title").text == "First"  # type: ignore[union-attr]


def test_render_atom_escapes_special_characters() -> None:
    xml = render_atom(
        feed_id="tag:test:feed",
        title="A & B <transit>",
        subtitle="x",
        self_url=f"{_BASE}/changes/feed.xml",
        alternate_url=f"{_BASE}/changes/",
        entries=[_entry("tag:test:1", "Cooke & Sons", "2026-06-12")],
    )
    # Parses cleanly (so escaping is valid) and round-trips the raw text.
    root = ET.fromstring(xml)
    assert root.find(f"{_ATOM}title").text == "A & B <transit>"  # type: ignore[union-attr]
    assert "&amp;" in xml and "&lt;transit&gt;" in xml


def test_entries_sorted_newest_first() -> None:
    xml = render_atom(
        feed_id="tag:test:feed",
        title="t",
        subtitle="s",
        self_url=f"{_BASE}/changes/feed.xml",
        alternate_url=f"{_BASE}/changes/",
        entries=[
            _entry("tag:test:old", "Old", "2026-06-01"),
            _entry("tag:test:new", "New", "2026-06-20"),
        ],
    )
    root = ET.fromstring(xml)
    titles = [e.find(f"{_ATOM}title").text for e in root.findall(f"{_ATOM}entry")]  # type: ignore[union-attr]
    assert titles == ["New", "Old"]


def test_render_atom_is_deterministic() -> None:
    args: dict[str, Any] = dict(
        feed_id="tag:test:feed",
        title="t",
        subtitle="s",
        self_url=f"{_BASE}/changes/feed.xml",
        alternate_url=f"{_BASE}/changes/",
        entries=[_entry("tag:test:1", "A", "2026-06-12")],
    )
    assert render_atom(**args) == render_atom(**args)


def _change(
    agency_id: str, name: str, from_grade: str, to_grade: str, regressed: bool
) -> dict[str, Any]:
    return {
        "id": agency_id,
        "name": name,
        "from_grade": from_grade,
        "to_grade": to_grade,
        "from_score": 82.0,
        "to_score": 74.0,
        "score_delta": -8.0,
        "regressed": regressed,
        "since": "2026-06-11",
        "date": "2026-06-12",
    }


def test_site_feed_tags_a_drop_as_grade_drop() -> None:
    changes = [_change("acme", "Acme Transit", "B", "C", regressed=True)]
    xml = site_change_feed(changes, base_url=_BASE)
    root = ET.fromstring(xml)
    entry = root.find(f"{_ATOM}entry")
    assert entry is not None
    cat = entry.find(f"{_ATOM}category")
    assert cat is not None and cat.get("term") == "grade_drop"
    link = entry.find(f"{_ATOM}link")
    assert link is not None and link.get("href") == f"{_BASE}/agency/acme/"


def test_site_feed_caps_entries() -> None:
    changes = [_change(f"a{i}", f"Agency {i}", "B", "C", regressed=True) for i in range(80)]
    xml = site_change_feed(changes, base_url=_BASE, max_entries=10)
    root = ET.fromstring(xml)
    assert len(root.findall(f"{_ATOM}entry")) == 10


def _export_change_record(agency_id: str = "acme", name: str = "Acme Transit") -> dict[str, Any]:
    return {
        "id": agency_id,
        "name": name,
        "date": "2026-06-12",
        "changes": ["Route 5 (E Street Express) is no longer in the export."],
    }


def test_site_feed_includes_export_change_entries() -> None:
    xml = site_change_feed([], base_url=_BASE, export_changes=[_export_change_record()])
    root = ET.fromstring(xml)
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 1
    cat = entries[0].find(f"{_ATOM}category")
    assert cat is not None and cat.get("term") == "export_change"
    summary = entries[0].find(f"{_ATOM}summary")
    assert summary is not None and "Route 5" in (summary.text or "")
    link = entries[0].find(f"{_ATOM}link")
    assert link is not None and link.get("href") == f"{_BASE}/agency/acme/"


def test_site_feed_interleaves_grade_and_export_change_entries_by_date() -> None:
    # A grade change and an export change on different dates should sort
    # newest-first together, not as two separate blocks.
    older_grade_change = _change("older", "Older Agency", "B", "C", regressed=True)
    older_grade_change["date"] = "2026-06-01"
    newer_export = _export_change_record("newer", "Newer Agency")
    xml = site_change_feed([older_grade_change], base_url=_BASE, export_changes=[newer_export])
    root = ET.fromstring(xml)
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 2
    titles = [e.find(f"{_ATOM}title").text for e in entries]  # type: ignore[union-attr]
    assert titles[0] == "Newer Agency: export structure changed"


def test_site_feed_caps_export_change_entries() -> None:
    records = [_export_change_record(f"a{i}", f"Agency {i}") for i in range(80)]
    xml = site_change_feed([], base_url=_BASE, export_changes=records, max_entries=10)
    root = ET.fromstring(xml)
    assert len(root.findall(f"{_ATOM}entry")) == 10


def test_site_feed_caps_each_kind_separately_and_keeps_every_grade_move() -> None:
    # The two lists are capped independently, so the document holds up to
    # 2 * max_entries. That is the point: `changes` is priority-ordered
    # (regressions first), so a day with many export changes must not be able
    # to push the grade drops out of a single merged, date-sorted cap.
    changes = [_change(f"g{i}", f"Grade Agency {i}", "B", "C", regressed=True) for i in range(20)]
    records = [_export_change_record(f"e{i}", f"Export Agency {i}") for i in range(20)]
    xml = site_change_feed(changes, base_url=_BASE, export_changes=records, max_entries=5)
    root = ET.fromstring(xml)
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 10
    categories = [
        e.find(f"{_ATOM}category").get("term")  # type: ignore[union-attr]
        for e in entries
    ]
    assert categories.count("export_change") == 5
    assert categories.count("grade_drop") == 5


def test_export_change_entry_id_does_not_collide_with_a_grade_change_entry() -> None:
    # Same agency, same date, two different events. Atom ids must differ or a
    # reader shows only one of them.
    xml = site_change_feed(
        [_change("acme", "Acme Transit", "B", "C", regressed=True)],
        base_url=_BASE,
        export_changes=[_export_change_record()],
    )
    root = ET.fromstring(xml)
    ids = [e.find(f"{_ATOM}id").text for e in root.findall(f"{_ATOM}entry")]  # type: ignore[union-attr]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_export_change_entry_without_changes_still_summarizes() -> None:
    record: dict[str, Any] = {
        "id": "acme",
        "name": "Acme Transit",
        "date": "2026-06-12",
        "changes": [],
    }
    xml = site_change_feed([], base_url=_BASE, export_changes=[record])
    root = ET.fromstring(xml)
    summary = root.find(f"{_ATOM}entry/{_ATOM}summary")
    assert summary is not None
    assert "export structure changed" in (summary.text or "")


def test_agency_feed_tags_export_change_event() -> None:
    events = [
        Event(
            date="2026-06-12",
            kind="export_change",
            detail="Route 5 (E Street Express) is no longer in the export.",
        )
    ]
    xml = agency_change_feed("acme", "Acme Transit", events, base_url=_BASE)
    root = ET.fromstring(xml)
    cat = root.find(f"{_ATOM}entry/{_ATOM}category")
    assert cat is not None and cat.get("term") == "export_change"


def test_agency_feed_from_history_events() -> None:
    events = [
        Event(
            date="2026-06-12",
            kind="grade_change",
            detail="Grade went B to C, freshness fell 9 points.",
        ),
        Event(
            date="2026-06-10",
            kind="expiry",
            detail="Feed entered the expiry window (20 days of service left).",
        ),
    ]
    xml = agency_change_feed("acme", "Acme Transit", events, base_url=_BASE)
    root = ET.fromstring(xml)
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 2
    # The grade drop is tagged so a reader/webhook can filter for the alert.
    terms = {e.find(f"{_ATOM}category").get("term") for e in entries}  # type: ignore[union-attr]
    assert "grade_drop" in terms


def test_agency_feed_tags_drop_with_no_driver_phrase() -> None:
    # A grade move with no category driver ends in a period ("Grade went C to D.");
    # the trailing period must not stop the drop from being tagged.
    events = [Event(date="2026-06-12", kind="grade_change", detail="Grade went C to D.")]
    xml = agency_change_feed("acme", "Acme Transit", events, base_url=_BASE)
    root = ET.fromstring(xml)
    cat = root.find(f"{_ATOM}entry/{_ATOM}category")
    assert cat is not None and cat.get("term") == "grade_drop"


def test_agency_feed_grade_rise_not_tagged_drop() -> None:
    events = [
        Event(
            date="2026-06-12",
            kind="grade_change",
            detail="Grade went C to B, correctness rose 7 points.",
        )
    ]
    xml = agency_change_feed("acme", "Acme Transit", events, base_url=_BASE)
    root = ET.fromstring(xml)
    cat = root.find(f"{_ATOM}entry/{_ATOM}category")
    assert cat is not None and cat.get("term") != "grade_drop"


def test_empty_feed_is_valid() -> None:
    xml = site_change_feed([], base_url=_BASE)
    root = ET.fromstring(xml)
    assert root.findall(f"{_ATOM}entry") == []
    assert root.find(f"{_ATOM}updated") is not None


def test_zero_comparison_change_feed_is_explicitly_unavailable() -> None:
    xml = site_change_feed([], base_url=_BASE, comparison={"eligible_count": 0})
    root = ET.fromstring(xml)
    subtitle = root.find(f"{_ATOM}subtitle")
    assert subtitle is not None
    assert "unavailable until current-contract checks" in (subtitle.text or "")
    assert "not a no-change claim" in (subtitle.text or "")


def test_guarded_change_feed_names_its_feed_record_denominator() -> None:
    xml = site_change_feed(
        [_change("acme", "Acme Transit", "B", "C", regressed=True)],
        base_url=_BASE,
        comparison={"eligible_count": 12},
    )
    root = ET.fromstring(xml)
    subtitle = root.find(f"{_ATOM}subtitle")
    assert subtitle is not None
    assert "12 current-contract, comparison-eligible feed records" in (subtitle.text or "")


def test_site_feed_subtitle_names_export_changes_as_part_of_its_scope() -> None:
    # A reader shows the subtitle as the feed's description. If it promised
    # only grade and score moves, an export_change entry would read as
    # something the feed was not supposed to carry.
    guarded = site_change_feed([], base_url=_BASE, comparison={"eligible_count": 12})
    assert "structural export changes" in (
        ET.fromstring(guarded).find(f"{_ATOM}subtitle").text or ""  # type: ignore[union-attr]
    )
    # Callers that pass no comparison metadata get the legacy subtitle, which
    # must describe the same scope.
    legacy = site_change_feed([], base_url=_BASE)
    assert "export changed" in (
        ET.fromstring(legacy).find(f"{_ATOM}subtitle").text or ""  # type: ignore[union-attr]
    )


def test_agency_feed_subtitle_names_export_structure_changes() -> None:
    xml = agency_change_feed("acme", "Acme Transit", [], base_url=_BASE)
    subtitle = ET.fromstring(xml).find(f"{_ATOM}subtitle")
    assert subtitle is not None
    assert "export-structure changes" in (subtitle.text or "")
    assert "Acme Transit" in (subtitle.text or "")


def test_feed_has_author_for_atom_validity() -> None:
    # RFC 4287 4.1.1: a feed whose entries carry no author MUST declare a
    # feed-level author, or it is not valid Atom.
    xml = render_atom(
        feed_id="tag:test:feed",
        title="t",
        subtitle="s",
        self_url=f"{_BASE}/changes/feed.xml",
        alternate_url=f"{_BASE}/changes/",
        entries=[_entry("tag:test:1", "A", "2026-06-12")],
    )
    root = ET.fromstring(xml)
    author = root.find(f"{_ATOM}author")
    assert author is not None
    assert author.find(f"{_ATOM}name").text == "GTFS Scorecard"  # type: ignore[union-attr]
