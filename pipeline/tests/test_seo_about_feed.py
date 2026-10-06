"""'About this feed' (measured fields only) and 'Similar feeds' links."""

from __future__ import annotations

import copy
import json
import re
from html import unescape
from pathlib import Path
from typing import Any

from scorecard_pipeline.render_site import (
    SIMILAR_FEEDS_LIMIT,
    _about_feed_section,
    _render_agency,
    _similar_feeds_section,
    similar_feeds,
)

FIXTURE = Path(__file__).parent / "fixtures" / "golden_site" / "data" / "artifacts"
A, B = "a" * 64, "b" * 64


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _artifact() -> dict[str, Any]:
    art: dict[str, Any] = {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "mode_profile": {
            "measured": True,
            "route_count": 14,
            "trip_count": 374,
            "modes": [{"key": "bus", "label": "Bus"}],
        },
        "geo": {"stop_count": 289},
        "categories": {
            "freshness": {
                "status": "measured",
                "details": {"feed_start_date": "2025-01-23", "effective_expiry_date": "2026-12-31"},
            },
            "realtime": {
                "status": "measured",
                "details": {
                    "configured_kinds": ["trip_updates", "vehicle_positions", "service_alerts"],
                    "reachable_kinds": ["trip_updates", "vehicle_positions"],
                },
            },
        },
    }
    return art


def test_lead_states_only_measured_facts() -> None:
    history = [{"date": "2026-09-01", "feed_sha256": A}, {"date": "2026-09-05", "feed_sha256": B}]
    text = _text(_about_feed_section(_artifact(), history))
    assert "About this feed" in text
    assert (
        "Demo Transit’s published feed lists 14 bus routes, 374 scheduled trips and 289 stops."
        in text
    )
    assert "Its service dates run from 2025-01-23 through 2026-12-31." in text
    assert (
        "It publishes realtime trip updates, vehicle positions and service alerts; "
        "when we checked, 2 of 3 answered." in text
    )
    assert "The published file last changed on 2026-09-05." in text


def test_unchanged_file_is_stated_only_when_every_check_has_the_same_hash() -> None:
    same = [{"date": "2026-06-16", "feed_sha256": A}, {"date": "2026-10-03", "feed_sha256": A}]
    assert "has not changed since our first check on 2026-06-16" in _text(
        _about_feed_section(_artifact(), same)
    )
    unknown = [{"date": "2026-06-16"}, {"date": "2026-10-03", "feed_sha256": A}]
    text = _text(_about_feed_section(_artifact(), unknown))
    assert "changed" not in text
    assert "last changed" not in _text(_about_feed_section(_artifact(), [same[0]]))


def test_unmeasured_fields_drop_their_sentence_never_a_zero() -> None:
    art = _artifact()
    art["mode_profile"]["measured"] = False
    art["geo"] = {}
    art["categories"]["freshness"]["status"] = "not_yet_measured"
    art["categories"]["realtime"] = {"status": "not_yet_measured"}
    assert _about_feed_section(art, []) == ""

    art = _artifact()
    art["geo"] = {"stop_count": None}
    art["mode_profile"]["trip_count"] = True  # a bool is not a count
    text = _text(_about_feed_section(art, []))
    assert "14 bus routes." in text
    assert " 0 " not in f" {text} "
    assert "stops" not in text


def test_no_realtime_sentence_when_realtime_was_not_measured() -> None:
    art = _artifact()
    art["categories"]["realtime"] = {"status": "not_yet_measured", "details": {}}
    text = _text(_about_feed_section(art, []))
    assert "realtime" not in text.lower()


def test_multimodal_feed_names_its_modes() -> None:
    art = _artifact()
    art["mode_profile"]["modes"] = [{"label": "Bus"}, {"label": "Rail"}]
    assert "14 routes (bus and rail)" in _text(_about_feed_section(art, []))


# --- similar feeds ----------------------------------------------------------


def _rec(
    i: str, name: str, place: str = "California", mode: str = "bus", tier: str = "small"
) -> dict[str, Any]:
    return {
        "id": i,
        "name": name,
        "country": "US",
        "subdivision_name": place,
        "primary_mode": mode,
        "size_tier": tier,
    }


DIRECTORY = [
    _rec("self", "Self Transit"),
    _rec("z-small-bus", "Zeta Bus"),
    _rec("a-small-bus", "Alpha Bus"),
    _rec("big-bus", "Big Bus", tier="large"),
    _rec("ferry", "A Ferry", mode="ferry"),
    _rec("elsewhere", "Elsewhere Bus", place="Oregon"),
]


def test_similar_feeds_prefer_same_mode_and_size_then_alphabetical() -> None:
    ids = [r["id"] for r in similar_feeds(DIRECTORY[0], DIRECTORY)]
    assert ids == ["a-small-bus", "z-small-bus", "big-bus", "ferry"]


def test_similar_feeds_are_bounded_and_need_a_location() -> None:
    many = [DIRECTORY[0]] + [_rec(f"p{i}", f"Peer {i}") for i in range(20)]
    assert len(similar_feeds(many[0], many)) == SIMILAR_FEEDS_LIMIT
    assert similar_feeds({"id": "x", "country": "US", "subdivision_name": ""}, DIRECTORY) == []
    assert similar_feeds(None, DIRECTORY) == []


def test_similar_section_links_without_ranking() -> None:
    html = _similar_feeds_section(DIRECTORY[0], similar_feeds(DIRECTORY[0], DIRECTORY))
    assert "Similar feeds in California" in html
    assert 'href="/agency/a-small-bus/"' in html
    assert "not ranked" in html
    assert _similar_feeds_section(DIRECTORY[0], []) == ""


def test_scorecard_renders_both_sections() -> None:
    art = json.loads((FIXTURE / "yolobus" / "latest.json").read_text())
    record = _rec("yolobus", "Yolobus")
    html = _render_agency(
        copy.deepcopy(art),
        dir_record=record,
        similar=similar_feeds(record, [record, *DIRECTORY[1:3]]),
    )
    assert 'id="about-feed-h"' in html
    assert 'href="/agency/a-small-bus/"' in html


def test_unclassified_mode_is_not_named() -> None:
    art = _artifact()
    art["mode_profile"]["modes"] = [{"key": "other", "label": "Other / unclassified"}]
    text = _text(_about_feed_section(art, []))
    assert "14 routes, 374 scheduled trips" in text
    assert "unclassified" not in text


def test_similar_feeds_list_each_name_once() -> None:
    twins = [*DIRECTORY, _rec("a-small-bus-2", "Alpha Bus"), _rec("self-2", "Self Transit")]
    ids = [r["id"] for r in similar_feeds(DIRECTORY[0], twins)]
    assert ids == ["a-small-bus", "z-small-bus", "big-bus", "ferry"]
