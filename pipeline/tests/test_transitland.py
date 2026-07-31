"""Tests for the Transitland Atlas DMFR discovery source."""

from __future__ import annotations

from scorecard_pipeline import transitland
from scorecard_pipeline.mobilitydb import propose_agencies

# A DMFR document shaped like a real Atlas file: a schedule feed with realtime
# URLs and an embedded operator, a key-gated feed, and a top-level operator that
# names a feed by association.
DMFR = {
    "feeds": [
        {
            "id": "f-9q9-demotransit",
            "spec": "gtfs",
            "urls": {
                "static_current": "https://demo.example.org/gtfs.zip",
                "realtime_trip_updates": "https://demo.example.org/tu.pb",
                "realtime_vehicle_positions": "https://demo.example.org/vp.pb",
            },
            "license": {"url": "https://creativecommons.org/licenses/by/4.0/"},
            "operators": [{"name": "Demo Transit Authority"}],
        },
        {
            "id": "f-9q9-keyedcity",
            "spec": "gtfs",
            "urls": {"static_current": "https://keyed.example.org/gtfs.zip"},
            "authorization": {"type": "query_param", "param_name": "key"},
        },
        {
            "id": "f-u33-berlin",
            "spec": "gtfs",
            "urls": {"static_current": "https://berlin.example.org/gtfs.zip"},
        },
        {"id": "f-9q9-gbfsonly", "spec": "gbfs", "urls": {}},
    ],
    "operators": [
        {
            "name": "Berlin Verkehr",
            "associated_feeds": [{"feed_onestop_id": "f-u33-berlin"}],
        }
    ],
}


def test_parse_dmfr_maps_a_schedule_feed_and_its_realtime() -> None:
    feeds = transitland.parse_dmfr([DMFR])
    by_id = {f.mdb_id: f for f in feeds}

    schedule = by_id["f-9q9-demotransit"]
    assert schedule.data_type == "gtfs"
    assert schedule.direct_download == "https://demo.example.org/gtfs.zip"
    assert schedule.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert schedule.authentication_type == ""  # open
    assert schedule.provider == "Demo Transit Authority"  # from the embedded operator
    # DMFR carries no ISO country; the location is left for a curator to fill.
    assert schedule.country == ""
    assert schedule.subdivision_code == ""

    tu = by_id["f-9q9-demotransit~tu"]
    assert tu.data_type == "gtfs-rt"
    assert tu.entity_type == "tu"
    assert tu.static_reference == "f-9q9-demotransit"  # wired back to its schedule feed
    assert tu.direct_download == "https://demo.example.org/tu.pb"
    assert by_id["f-9q9-demotransit~vp"].entity_type == "vp"


def test_parse_dmfr_flags_a_key_gated_feed() -> None:
    (keyed,) = [f for f in transitland.parse_dmfr([DMFR]) if f.mdb_id == "f-9q9-keyedcity"]
    # A query_param authorization means a key is required, so it is not open.
    assert keyed.authentication_type == "1"


def test_parse_dmfr_provider_falls_back_to_top_level_operator_then_slug() -> None:
    by_id = {f.mdb_id: f for f in transitland.parse_dmfr([DMFR])}
    # The Berlin feed has no embedded operator, so the top-level operator that
    # lists it supplies the name.
    assert by_id["f-u33-berlin"].provider == "Berlin Verkehr"
    # The keyed feed has neither; the provider degrades to the id slug.
    assert by_id["f-9q9-keyedcity"].provider == "keyedcity"


def test_parse_dmfr_drops_non_gtfs_specs() -> None:
    ids = {f.mdb_id for f in transitland.parse_dmfr([DMFR])}
    assert "f-9q9-gbfsonly" not in ids  # a gbfs feed is not a GTFS candidate


def test_parse_dmfr_feeds_flow_through_the_shared_proposer() -> None:
    # The whole point of matching CatalogFeed: a Transitland feed proposes a
    # registry entry through the same proposer as a Mobility Database feed, with
    # its realtime wired on and key-gated feeds skipped.
    feeds = transitland.parse_dmfr([DMFR])
    proposals = propose_agencies(feeds)
    by_url = {p.static_gtfs_url: p for p in proposals}

    demo = by_url["https://demo.example.org/gtfs.zip"]
    assert demo.rt_urls == {
        "trip_updates": "https://demo.example.org/tu.pb",
        "vehicle_positions": "https://demo.example.org/vp.pb",
    }
    berlin = by_url["https://berlin.example.org/gtfs.zip"]
    assert berlin.license_note == (
        "No stated data license in the source catalog; verify before publishing."
    )
    # The key-gated schedule feed is not proposed as a fetchable feed.
    assert "https://keyed.example.org/gtfs.zip" not in by_url


def test_parse_dmfr_ignores_empty_documents() -> None:
    assert transitland.parse_dmfr([]) == []
    assert transitland.parse_dmfr([{"feeds": []}]) == []
    assert transitland.parse_dmfr([{}]) == []
