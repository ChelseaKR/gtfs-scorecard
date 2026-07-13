"""Tests for the Mobility Database sync: parsing, proposing, rendering."""

from __future__ import annotations

import pytest
import yaml

from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.mobilitydb import (
    apply_replacements,
    apply_state_backfill,
    canonical_state,
    find_replacements,
    parse_catalog,
    propose_agencies,
    render_replacements_md,
    render_yaml,
    replacement_url,
    resolve_states,
    slugify,
)


def test_canonical_state_normalizes_and_drops_non_states() -> None:
    assert canonical_state("California") == "California"
    assert canonical_state("Chicago") == "Illinois"  # known city -> state fixup
    assert canonical_state("Some County") == ""
    assert canonical_state("") == ""


def test_resolve_states_fills_only_missing_with_a_catalog_match() -> None:
    feeds = parse_catalog(CATALOG)

    def entry(aid: str, **extra: object) -> dict[str, object]:
        return {"id": aid, "name": aid, "static_gtfs_url": "https://ex.org/g.zip", **extra}

    agencies = parse_agencies(
        {
            "agencies": [
                entry("dct", mdb_id="100"),
                entry("pdx", mdb_id="300"),
                entry("already", mdb_id="200", state="Nevada"),
                entry("nomdb"),
                entry("badmdb", mdb_id="999"),
            ]
        }
    )
    # dct -> California, pdx -> Oregon. "already" has a curator state (skipped),
    # "nomdb" has no mdb_id, "badmdb" isn't in the catalog.
    assert resolve_states(agencies, feeds) == {"dct": "California", "pdx": "Oregon"}


def test_apply_state_backfill_inserts_state_and_leaves_others_untouched() -> None:
    yaml_text = (
        "agencies:\n"
        "  - id: dct\n"
        "    name: DCT\n"
        "    static_gtfs_url: https://ex.org/d.zip\n"
        "  - id: keep\n"
        "    name: Keep\n"
        "    static_gtfs_url: https://ex.org/k.zip\n"
    )
    updated, changed = apply_state_backfill(yaml_text, {"dct": "California"})
    assert changed == ["dct"]
    assert "  - id: dct\n    state: California\n" in updated
    # Re-parses, and only dct gained a state.
    agencies = parse_agencies(yaml.safe_load(updated))
    by_id = {a.id: a for a in agencies}
    assert by_id["dct"].state == "California"
    assert by_id["keep"].state == ""


# A trimmed catalog with two CA schedule feeds, one with paired RT (open) and
# one with key-gated RT, plus an out-of-state feed and a non-GTFS row.
CATALOG = (
    "mdb_source_id,data_type,entity_type,location.country_code,"
    "location.subdivision_name,provider,name,urls.direct_download,urls.license,"
    "urls.authentication_type,static_reference\n"
    "100,gtfs,,US,California,Davis Community Transit,Davis Community Transit,"
    "https://ex.org/dct.zip,https://ex.org/dct/license,,\n"
    "101,gtfs-rt,vp,US,California,Davis Community Transit,DCT VP,"
    "https://ex.org/dct/vp.pb,,0,100\n"
    "102,gtfs-rt,tu,US,California,Davis Community Transit,DCT TU,"
    "https://ex.org/dct/tu.pb,,0,100\n"
    "200,gtfs,,US,California,Capitol Shuttle,Capitol Shuttle,"
    "https://ex.org/cap.zip,,,\n"
    "201,gtfs-rt,vp,US,California,Capitol Shuttle,Cap VP,"
    "https://ex.org/cap/vp.pb,,2,200\n"
    "300,gtfs,,US,Oregon,Portland Lines,Portland Lines,"
    "https://ex.org/pdx.zip,,,\n"
    "400,gbfs,,US,California,Bikeshare,Bikeshare,https://ex.org/gbfs.json,,,\n"
)


def test_parse_catalog_keeps_gtfs_rows_only() -> None:
    feeds = parse_catalog(CATALOG)
    types = {f.mdb_id: f.data_type for f in feeds}
    assert "400" not in types  # gbfs dropped
    assert types["100"] == "gtfs"
    assert types["101"] == "gtfs-rt"


def test_catalog_retains_status_and_official_provenance() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download,status,is_official\n"
        "active,gtfs,Active,Active,https://ex.org/a.zip,active,true\n"
        "old,gtfs,Old,Old,https://ex.org/o.zip,deprecated,false\n"
    )
    active, old = parse_catalog(catalog)
    assert active.status == "active" and active.is_official is True
    assert old.status == "deprecated" and old.is_official is False
    assert [proposal.mdb_id for proposal in propose_agencies([active, old])] == ["active"]


def test_proposals_dedupe_source_ids_and_http_variants() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download,status,is_official\n"
        "same,gtfs,First,First,http://ex.org/feed.zip,active,true\n"
        "same,gtfs,First Copy,First Copy,https://ex.org/feed.zip,active,true\n"
        "other,gtfs,URL Copy,URL Copy,https://ex.org/feed.zip,active,true\n"
    )
    proposals = propose_agencies(parse_catalog(catalog))
    assert len(proposals) == 1
    assert proposals[0].mdb_id == "same"
    assert proposals[0].feed_status == "active"
    assert proposals[0].is_official is True


def test_proposals_skip_catalog_rows_without_a_safe_normalized_url_key() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download,status,is_official\n"
        "bad-ipv6,gtfs,Bad IPv6,Bad IPv6,https://[::1/feed.zip,active,true\n"
        "bad-nfkc,gtfs,Bad NFKC,Bad NFKC,"
        "https://example.org\uff0f@evil.example/feed.zip,active,true\n"
        "valid,gtfs,Valid Transit,Valid Transit,https://ex.org/valid.zip,active,true\n"
    )

    proposals = propose_agencies(parse_catalog(catalog))

    assert [proposal.mdb_id for proposal in proposals] == ["valid"]


def test_state_filter_and_rt_pairing() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, country="US", subdivision="California")
    by_id = {p.id: p for p in proposals}

    assert "portland-lines" not in by_id  # Oregon filtered out
    dct = by_id["davis-community-transit"]
    assert dct.static_gtfs_url == "https://ex.org/dct.zip"
    # both open RT feeds attach, mapped to our kinds
    assert dct.rt_urls == {
        "vehicle_positions": "https://ex.org/dct/vp.pb",
        "trip_updates": "https://ex.org/dct/tu.pb",
    }
    assert "license" in dct.license_note


def test_key_gated_rt_becomes_note_not_url() -> None:
    feeds = parse_catalog(CATALOG)
    (cap,) = [p for p in propose_agencies(feeds, country="US") if p.id == "capitol-shuttle"]
    assert cap.rt_urls == {}
    assert "access key" in cap.rt_note


def test_existing_ids_are_skipped() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, country="US", existing_ids={"davis-community-transit"})
    assert "davis-community-transit" not in {p.id for p in proposals}


def test_provider_filter() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, providers=["Capitol Shuttle"])
    assert {p.id for p in proposals} == {"capitol-shuttle"}


def test_descriptor_feed_name_falls_back_to_provider() -> None:
    # When the catalog's name column is a feed descriptor ("Flex"), the provider
    # is the real agency name, so the proposal must use the provider.
    catalog = (
        "mdb_source_id,data_type,entity_type,location.country_code,"
        "location.subdivision_name,provider,name,urls.direct_download,urls.license,"
        "urls.authentication_type,static_reference\n"
        "900,gtfs,,US,California,Hopelink Transportation,Flex,"
        "https://ex.org/hope.zip,,,\n"
    )
    feeds = parse_catalog(catalog)
    (hope,) = propose_agencies(feeds, country="US")
    assert hope.name == "Hopelink Transportation"
    assert hope.id == "hopelink-transportation"


def test_slugify_falls_back_to_mdb_id() -> None:
    assert slugify("Davis Community Transit!", "100") == "davis-community-transit"
    assert slugify("", "100") == "mdb-100"


def test_rendered_yaml_parses_back_into_valid_agencies() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, country="US", subdivision="California")
    block = "agencies:\n" + render_yaml(proposals)
    agencies = parse_agencies(yaml.safe_load(block))
    ids = {a.id for a in agencies}
    assert {"davis-community-transit", "capitol-shuttle"} <= ids


def test_canadian_proposal_preserves_location_through_yaml_round_trip() -> None:
    catalog = (
        "mdb_source_id,data_type,location.country_code,location.subdivision_code,"
        "location.subdivision_name,provider,name,urls.direct_download\n"
        "ca-1,gtfs,CA,CA-ON,Ontario,Barrie Transit,Barrie Transit,"
        "https://example.ca/barrie.zip\n"
    )
    (proposal,) = propose_agencies(parse_catalog(catalog), country="CA")

    assert proposal.country == "CA"
    assert proposal.subdivision_code == "CA-ON"
    assert proposal.subdivision_name == "Ontario"

    block = "agencies:\n" + render_yaml([proposal])
    assert "    country: CA\n" in block
    assert "    subdivision_code: CA-ON\n" in block
    assert "    subdivision_name: Ontario\n" in block

    (agency,) = parse_agencies(yaml.safe_load(block))
    assert agency.country == "CA"
    assert agency.subdivision_code == "CA-ON"
    assert agency.subdivision_name == "Ontario"


def test_global_country_preserves_location_through_yaml_round_trip() -> None:
    catalog = (
        "mdb_source_id,data_type,location.country_code,location.subdivision_code,"
        "location.subdivision_name,provider,name,urls.direct_download\n"
        "gb-1,gtfs,GB,GB-ENG,England,Example Bus,Example Bus,"
        "https://example.org/england.zip\n"
    )
    (proposal,) = propose_agencies(parse_catalog(catalog), country="GB")

    assert proposal.country == "GB"
    assert proposal.subdivision_code == "GB-ENG"
    assert proposal.subdivision_name == "England"
    rendered = render_yaml([proposal])
    assert "    country: GB\n" in rendered
    (agency,) = parse_agencies(yaml.safe_load("agencies:\n" + rendered))
    assert (agency.country, agency.subdivision_code) == ("GB", "GB-ENG")


def test_unassigned_catalog_country_is_preserved_for_explicit_rejection() -> None:
    catalog = (
        "mdb_source_id,data_type,location.country_code,provider,name,urls.direct_download\n"
        "xk-1,gtfs,XK,Example Bus,Example Bus,https://example.org/example.zip\n"
    )
    (proposal,) = propose_agencies(parse_catalog(catalog), country="XK")

    assert proposal.country == "XK"
    rendered = render_yaml([proposal])
    with pytest.raises(AgencyConfigError, match="assigned ISO 3166-1"):
        parse_agencies(yaml.safe_load("agencies:\n" + rendered))


def test_us_proposal_resolves_subdivision_name_to_iso_code() -> None:
    proposals = propose_agencies(parse_catalog(CATALOG), providers=["Davis Community Transit"])
    (dct,) = proposals

    assert dct.country == "US"
    assert dct.subdivision_code == "US-CA"
    assert dct.subdivision_name == "California"
    rendered = render_yaml([dct])
    assert "    country:" not in rendered  # US remains the registry default.
    assert "    subdivision_code: US-CA\n" in rendered
    assert "    subdivision_name: California\n" in rendered


def test_unknown_subdivision_name_is_preserved_without_a_guessed_code() -> None:
    catalog = (
        "mdb_source_id,data_type,location.country_code,location.subdivision_name,"
        "provider,name,urls.direct_download\n"
        "unknown-1,gtfs,US,Some County,County Bus,County Bus,"
        "https://example.org/county.zip\n"
    )
    (proposal,) = propose_agencies(parse_catalog(catalog))

    assert proposal.country == "US"
    assert proposal.subdivision_code == ""
    assert proposal.subdivision_name == "Some County"
    rendered = render_yaml([proposal])
    assert "    subdivision_code:" not in rendered
    assert "    subdivision_name: Some County\n" in rendered


# A catalog where one tracked agency's URL is unchanged, one has moved to a new
# download URL, and one isn't present at all.
DISCOVERY_CATALOG = (
    "mdb_source_id,data_type,entity_type,location.country_code,"
    "location.subdivision_name,provider,name,urls.direct_download,urls.license,"
    "urls.authentication_type,static_reference\n"
    "500,gtfs,,US,California,Davis Community Transit,Davis Community Transit,"
    "https://feeds.example.org/davis/current.zip,https://ex.org/lic,,\n"
    "501,gtfs,,US,California,Alhambra Community Transit,Alhambra Community Transit,"
    "https://data.trilliumtransit.com/gtfs/alhambra-ca-us/alhambra-ca-us.zip,,,\n"
)


def test_find_replacements_classifies_each_agency() -> None:
    feeds = parse_catalog(DISCOVERY_CATALOG)
    registry = [
        # same URL as catalog 501 -> tracked
        (
            "alhambra-community-transit",
            "Alhambra Community Transit",
            "http://data.trilliumtransit.com/gtfs/alhambra-ca-us/alhambra-ca-us.zip",
        ),
        # name matches catalog 500 but our URL is different -> replaced
        (
            "davis-community-transit",
            "Davis Community Transit",
            "https://old.example.org/davis/legacy.zip",
        ),
        # nothing in the catalog looks like this -> missing
        ("phantom-shuttle", "Phantom Shuttle", "https://nowhere.example.org/x.zip"),
    ]
    by_id = {m.agency_id: m for m in find_replacements(feeds, registry)}

    # http vs https and a trailing path still resolve to the same feed.
    assert by_id["alhambra-community-transit"].status == "tracked"

    davis = by_id["davis-community-transit"]
    assert davis.status == "replaced"
    assert davis.candidates[0].direct_download == "https://feeds.example.org/davis/current.zip"

    assert by_id["phantom-shuttle"].status == "missing"
    assert by_id["phantom-shuttle"].candidates == []


def test_render_replacements_md_lists_only_actionable() -> None:
    feeds = parse_catalog(DISCOVERY_CATALOG)
    registry = [
        (
            "davis-community-transit",
            "Davis Community Transit",
            "https://old.example.org/davis/legacy.zip",
        ),
        ("phantom-shuttle", "Phantom Shuttle", "https://nowhere.example.org/x.zip"),
    ]
    md = render_replacements_md(find_replacements(feeds, registry), today="2026-06-19")
    assert "Likely replaced" in md
    assert "https://feeds.example.org/davis/current.zip" in md
    # the missing agency shows under its own heading, not as a replacement
    assert "No catalog match" in md
    assert "Phantom Shuttle" in md


def test_apply_replacements_rewrites_only_moved_feeds_and_keeps_comments() -> None:
    feeds = parse_catalog(DISCOVERY_CATALOG)
    registry = [
        # moved: name matches catalog 500 but our URL differs
        ("davis-community-transit", "Davis Community Transit", "https://old.example.org/davis.zip"),
        # unchanged: exact URL is in the catalog
        (
            "alhambra-community-transit",
            "Alhambra Community Transit",
            "http://data.trilliumtransit.com/gtfs/alhambra-ca-us/alhambra-ca-us.zip",
        ),
    ]
    matches = find_replacements(feeds, registry)

    yaml_text = (
        "# Agencies tracked by the scorecard.\n"
        "agencies:\n"
        "  - id: davis-community-transit\n"
        "    name: Davis Community Transit\n"
        "    static_gtfs_url: https://old.example.org/davis.zip\n"
        "    license_note: keep me\n"
        "  - id: alhambra-community-transit\n"
        "    name: Alhambra Community Transit\n"
        "    static_gtfs_url: http://data.trilliumtransit.com/gtfs/alhambra-ca-us/alhambra-ca-us.zip\n"
    )
    updated, changed = apply_replacements(yaml_text, matches)

    assert changed == ["davis-community-transit"]
    assert "static_gtfs_url: https://feeds.example.org/davis/current.zip" in updated
    # the unchanged agency and the human-written comment/fields are untouched
    assert "alhambra-ca-us/alhambra-ca-us.zip" in updated
    assert "# Agencies tracked by the scorecard." in updated
    assert "license_note: keep me" in updated
    # the result still parses as a valid registry
    parse_agencies(yaml.safe_load(updated))


def test_apply_replacements_noop_without_moves() -> None:
    yaml_text = "agencies:\n  - id: x\n    name: X\n    static_gtfs_url: https://x.org/x.zip\n"
    updated, changed = apply_replacements(yaml_text, [])
    assert changed == []
    assert updated == yaml_text


def test_replacement_url_only_for_replaced() -> None:
    feeds = parse_catalog(DISCOVERY_CATALOG)
    registry = [
        ("davis-community-transit", "Davis Community Transit", "https://old.example.org/davis.zip"),
        ("phantom-shuttle", "Phantom Shuttle", "https://nowhere.example.org/x.zip"),
    ]
    by_id = {m.agency_id: m for m in find_replacements(feeds, registry)}
    assert (
        replacement_url(by_id["davis-community-transit"])
        == "https://feeds.example.org/davis/current.zip"
    )
    assert replacement_url(by_id["phantom-shuttle"]) is None


# A catalog where the same agency now sits on a new URL but keeps its mdb id.
MDB_PIN_CATALOG = (
    "mdb_source_id,data_type,entity_type,location.country_code,"
    "location.subdivision_name,provider,name,urls.direct_download,urls.license,"
    "urls.authentication_type,static_reference\n"
    "777,gtfs,,US,California,Renamed Regional Transit,Renamed Regional Transit,"
    "https://feeds.example.org/new/regional.zip,,,\n"
)


def test_pinned_mdb_id_matches_exact_row_despite_rename() -> None:
    feeds = parse_catalog(MDB_PIN_CATALOG)
    # Our registry name no longer resembles the catalog provider name, and the
    # URL has changed; only the pinned mdb id ties them together.
    registry = [("old-county-bus", "Old County Bus", "https://old.example.org/legacy.zip")]
    matches = find_replacements(feeds, registry, mdb_ids={"old-county-bus": "777"})
    (m,) = matches
    assert m.status == "replaced"
    assert replacement_url(m) == "https://feeds.example.org/new/regional.zip"


def test_pinned_mdb_id_tracked_when_url_unchanged() -> None:
    feeds = parse_catalog(MDB_PIN_CATALOG)
    registry = [("x", "X", "https://feeds.example.org/new/regional.zip")]
    (m,) = find_replacements(feeds, registry, mdb_ids={"x": "777"})
    assert m.status == "tracked"


def test_sync_emits_mdb_id_and_it_round_trips() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, country="US", subdivision="California")
    block = "agencies:\n" + render_yaml(proposals)
    assert "mdb_id:" in block
    agencies = parse_agencies(yaml.safe_load(block))
    dct = next(a for a in agencies if a.id == "davis-community-transit")
    assert dct.mdb_id == "100"


# A catalog row carrying MobilityData's hosted GCS mirror in urls.latest.
MIRROR_CATALOG = (
    "mdb_source_id,data_type,entity_type,location.country_code,"
    "location.subdivision_name,provider,name,urls.direct_download,urls.license,"
    "urls.authentication_type,static_reference,urls.latest\n"
    "1295,gtfs,,US,California,Yolo County Transportation District,Yolobus,"
    "http://www.yolobus.com/GTFS/google_transit.zip,,,,"
    "https://storage.googleapis.com/storage/v1/b/mdb-latest/o/us-ca-yolo.zip?alt=media\n"
)


def test_parse_catalog_captures_hosted_mirror() -> None:
    (feed,) = parse_catalog(MIRROR_CATALOG)
    assert feed.hosted_url.endswith("us-ca-yolo.zip?alt=media")


def test_hosted_mirror_url_never_resolves_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline import mobilitydb as m

    feeds = parse_catalog(MIRROR_CATALOG)
    monkeypatch.setattr(m, "load_catalog", lambda **_: feeds)
    # Names are discovery hints, not a byte-level identity boundary. Even an
    # exact provider name cannot select a different catalog URL as a mirror.
    url = m.hosted_mirror_url(
        "yolobus",
        "Yolobus (Yolo County Transportation District)",
        "https://avl.yctd.org/RealTime/google_transit.zip",
    )
    assert url is None


def test_hosted_mirror_url_resolves_by_exact_pinned_mdb_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import mobilitydb as m

    feeds = parse_catalog(MIRROR_CATALOG)
    monkeypatch.setattr(m, "load_catalog", lambda **_: feeds)

    url = m.hosted_mirror_url(
        "renamed-agency",
        "A completely different public name",
        "https://unreachable.example.org/feed.zip",
        "1295",
    )

    assert url is not None and url.endswith("us-ca-yolo.zip?alt=media")


def test_hosted_mirror_url_resolves_by_exact_normalized_current_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import mobilitydb as m

    feeds = parse_catalog(MIRROR_CATALOG)
    monkeypatch.setattr(m, "load_catalog", lambda **_: feeds)

    url = m.hosted_mirror_url(
        "unrelated-slug",
        "Unrelated name",
        "https://www.yolobus.com/GTFS/google_transit.zip/",
    )

    assert url is not None and url.endswith("us-ca-yolo.zip?alt=media")
