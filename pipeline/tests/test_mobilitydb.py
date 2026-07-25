"""Tests for the Mobility Database sync: parsing, proposing, rendering."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.mobilitydb import (
    DEFAULT_CATALOG_URL,
    DEFAULT_PROPOSAL_CATALOG_URL,
    LEGACY_MOBILITY_DATABASE_CATALOG_URL,
    MOBILITY_DATABASE_FEEDS_V2_URL,
    apply_replacements,
    apply_state_backfill,
    canonical_state,
    catalog_source_counts,
    fetch_catalog,
    fetch_catalog_bytes,
    find_replacements,
    parse_catalog,
    parse_catalog_records,
    proposal_catalog_schema,
    propose_agencies,
    propose_agencies_with_dispositions,
    render_replacements_md,
    render_yaml,
    replacement_url,
    resolve_states,
    slugify,
)

V2_FIXTURE = Path(__file__).parent / "fixtures" / "mobilitydb_feeds_v2_trimmed.csv"
V2_HEADER = (
    "id",
    "data_type",
    "entity_type",
    "location.country_code",
    "location.subdivision_name",
    "location.municipality",
    "provider",
    "is_official",
    "name",
    "note",
    "feed_contact_email",
    "static_reference",
    "urls.direct_download",
    "urls.authentication_type",
    "urls.authentication_info",
    "urls.api_key_parameter_name",
    "urls.latest",
    "urls.license",
    "location.bounding_box.minimum_latitude",
    "location.bounding_box.maximum_latitude",
    "location.bounding_box.minimum_longitude",
    "location.bounding_box.maximum_longitude",
    "location.bounding_box.extracted_on",
    "status",
    "features",
    "redirect.id",
    "redirect.comment",
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


def test_v2_source_is_separate_from_legacy_operational_default() -> None:
    assert DEFAULT_PROPOSAL_CATALOG_URL == MOBILITY_DATABASE_FEEDS_V2_URL
    assert DEFAULT_CATALOG_URL == LEGACY_MOBILITY_DATABASE_CATALOG_URL
    assert DEFAULT_PROPOSAL_CATALOG_URL != DEFAULT_CATALOG_URL


def test_v2_fixture_has_exact_schema_and_maps_supported_fields() -> None:
    text = V2_FIXTURE.read_text()
    reader = csv.DictReader(text.splitlines(keepends=True))
    rows = list(reader)

    assert tuple(reader.fieldnames or ()) == V2_HEADER
    assert all(None not in row and None not in row.values() for row in rows)

    by_id = {feed.mdb_id: feed for feed in parse_catalog(text)}
    assert "gbfs-demo" not in by_id

    schedule = by_id["mdb-100"]
    assert schedule.data_type == "gtfs"
    assert schedule.country == "US"
    assert schedule.subdivision == "California"
    assert schedule.municipality == "Davis"
    assert schedule.provider == "Davis Community Transit"
    assert schedule.name == "DCT Local,\nRegional schedule"
    assert schedule.direct_download == "http://example.org/dct.zip"
    assert schedule.authentication_type == "0"
    assert schedule.hosted_url.endswith("/mdb-100/latest.zip")
    assert schedule.license_url == "https://example.org/license"
    assert schedule.status == "active"
    assert schedule.is_official is True

    realtime = by_id["mdb-rt-1"]
    assert realtime.data_type == "gtfs-rt"
    assert realtime.entity_type == "tu|vp"
    assert realtime.static_reference == "101|mdb-200"


def test_proposal_catalog_schema_accepts_v2_and_compatible_legacy() -> None:
    assert proposal_catalog_schema(V2_FIXTURE.read_text()) == "mobilitydatabase-feeds-v2"
    assert proposal_catalog_schema(CATALOG) == "mobilitydatabase-legacy"


@pytest.mark.parametrize(
    "body, message",
    [
        ("<html><body>upstream error</body></html>", "unrecognized proposal catalog header"),
        (
            "id,data_type,provider,urls.direct_download\n",
            "Mobility Database V2 catalog is missing required column",
        ),
    ],
)
def test_proposal_catalog_schema_rejects_non_csv_and_unsafe_v2_headers(
    body: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        proposal_catalog_schema(body)


def test_v2_source_counts_preserve_the_pre_filter_denominator() -> None:
    assert catalog_source_counts(V2_FIXTURE.read_text()) == {
        "total_records": 9,
        "schedule_records": 7,
        "realtime_records": 1,
        "active_schedule_records": 6,
        "active_keyless_schedule_records": 5,
        "proposal_eligible_schedule_records": 3,
    }


def test_candidate_ledger_accounts_for_every_v2_schedule_source_record() -> None:
    records = parse_catalog_records(V2_FIXTURE.read_text())
    proposals, dispositions = propose_agencies_with_dispositions(records, country="US")

    assert len(dispositions) == 7
    assert len(proposals) == 2
    assert [record.source_record_number for record in dispositions] == [1, 2, 3, 5, 6, 7, 8]
    by_id = {record.source_id: record for record in dispositions}
    assert by_id["mdb-100"].decision == "proposed_for_review"
    assert by_id["mdb-100"].proposal_id == "davis-community-transit"
    assert by_id["mdb-101"].decision == "collapsed_duplicate"
    assert by_id["mdb-101"].selected_source_id == "mdb-100"
    assert by_id["mdb-300"].reason_codes == ("non_active_status",)
    assert by_id["mdb-400"].reason_codes == ("schedule_authentication_required",)
    assert by_id["mdb-500"].reason_codes == ("explicitly_unofficial",)
    assert by_id["mdb-600"].reason_codes == ("invalid_direct_download",)
    assert by_id["mdb-200"].review_flags == (
        "license_not_stated",
        "official_status_unspecified",
    )
    assert sum(record.proposal_eligible for record in dispositions) == 3


def test_candidate_ledger_preserves_missing_urls_and_multiple_exclusion_reasons() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "missing,gtfs,,Missing Transit,false,,1,inactive,\n"
        "rt,gtfs_rt,tu,Missing Transit,true,,0,active,missing\n"
    )

    assert parse_catalog(catalog) == []
    records = parse_catalog_records(catalog)
    proposals, dispositions = propose_agencies_with_dispositions(records)

    assert proposals == []
    assert len(dispositions) == 1
    assert dispositions[0].reason_codes == (
        "non_active_status",
        "explicitly_unofficial",
        "schedule_authentication_required",
        "missing_direct_download",
    )


def test_candidate_ledger_blocks_one_catalog_id_mapped_to_multiple_endpoints() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "same,gtfs,,First Transit,true,https://example.org/first.zip,0,active,\n"
        "same,gtfs,,Second Transit,true,https://example.org/second.zip,0,active,\n"
    )

    proposals, dispositions = propose_agencies_with_dispositions(parse_catalog_records(catalog))

    assert proposals == []
    assert [record.decision for record in dispositions] == [
        "blocked_conflict",
        "blocked_conflict",
    ]
    assert {reason for record in dispositions for reason in record.reason_codes} == {
        "catalog_id_maps_to_multiple_endpoints"
    }


def test_ambiguous_catalog_id_precedes_registry_suppression() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "same,gtfs,,First Transit,true,https://example.org/first.zip,0,active,\n"
        "same,gtfs,,Second Transit,true,https://example.org/second.zip,0,active,\n"
    )

    proposals, dispositions = propose_agencies_with_dispositions(
        parse_catalog_records(catalog),
        existing_mdb_id_matches={"same": {"tracked"}},
    )

    assert proposals == []
    assert [record.decision for record in dispositions] == [
        "blocked_conflict",
        "blocked_conflict",
    ]
    assert all(
        record.reason_codes == ("catalog_id_maps_to_multiple_endpoints",) for record in dispositions
    )
    assert all(record.matched_registry_ids == () for record in dispositions)


def test_candidate_ledger_surfaces_a_second_generated_id_collision() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "mdb-1,gtfs,,Same,true,https://example.org/feed.zip,0,active,\n"
    )

    proposals, dispositions = propose_agencies_with_dispositions(
        parse_catalog_records(catalog),
        existing_ids={"same", "same-mdb-1"},
    )

    assert proposals == []
    assert dispositions[0].decision == "blocked_conflict"
    assert dispositions[0].reason_codes == ("proposal_id_collision",)


def test_proposal_ids_are_independent_of_distinct_source_row_order() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "mdb-2,gtfs,,Same,true,https://example.org/b.zip,0,active,\n"
        "mdb-1,gtfs,,Same,true,https://example.org/a.zip,0,active,\n"
    )
    records = parse_catalog_records(catalog)

    forward, _forward_dispositions = propose_agencies_with_dispositions(records)
    reverse, _reverse_dispositions = propose_agencies_with_dispositions(list(reversed(records)))

    assert forward == reverse
    assert [proposal.id for proposal in forward] == ["same", "same-mdb-2"]


def test_candidate_ledger_names_registry_records_that_suppress_a_candidate() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "mdb-00100,gtfs,,Tracked Transit,true,https://example.org/feed.zip,0,active,\n"
    )

    proposals, dispositions = propose_agencies_with_dispositions(
        parse_catalog_records(catalog),
        existing_mdb_id_matches={"100": {"tracked-by-id"}},
        existing_feed_url_matches={"http://example.org/feed.zip/": {"tracked-by-url"}},
    )

    assert proposals == []
    assert dispositions[0].decision == "already_tracked"
    assert dispositions[0].reason_codes == (
        "catalog_id_already_tracked",
        "endpoint_already_tracked",
    )
    assert dispositions[0].matched_registry_ids == (
        "tracked-by-id",
        "tracked-by-url",
    )


def test_candidate_ledger_omits_raw_endpoint_credentials_and_query_values() -> None:
    catalog = (
        "id,data_type,entity_type,provider,is_official,urls.direct_download,"
        "urls.authentication_type,status,static_reference\n"
        "unsafe,gtfs,,Unsafe Transit,true,"
        "https://alice:secret@example.org/feed.zip?token=private,0,active,\n"
    )

    _proposals, dispositions = propose_agencies_with_dispositions(parse_catalog_records(catalog))
    rendered = str([record.as_record() for record in dispositions])

    assert "alice" not in rendered
    assert "secret" not in rendered
    assert "private" not in rendered


def test_v2_hosted_latest_url_is_not_treated_as_a_canonical_source() -> None:
    catalog = (
        "id,data_type,entity_type,static_reference,urls.direct_download,"
        "urls.latest,status,is_official\n"
        "mdb-700,gtfs,,,,"
        "https://files.mobilitydatabase.org/mdb-700/latest.zip,active,true\n"
        "mdb-rt-700,gtfs_rt,tu,mdb-700,,"
        "https://files.mobilitydatabase.org/mdb-rt-700/latest.pb,active,true\n"
    )

    assert parse_catalog(catalog) == []
    counts = catalog_source_counts(catalog)
    assert counts["schedule_records"] == 1
    assert counts["realtime_records"] == 1
    assert counts["proposal_eligible_schedule_records"] == 0


def test_v2_proposals_filter_rows_and_prefer_richer_duplicate_metadata() -> None:
    proposals = propose_agencies(parse_catalog(V2_FIXTURE.read_text()), country="US")
    by_mdb = {proposal.mdb_id: proposal for proposal in proposals}

    # Inactive, key-gated, explicitly unofficial, and malformed schedule rows
    # do not enter the review queue. The two DCT rows share one normalized URL;
    # the official row with license/location/mirror metadata wins.
    assert set(by_mdb) == {"mdb-100", "mdb-200"}
    dct = by_mdb["mdb-100"]
    assert dct.mdb_id == "mdb-100"  # Preserve the selected V2 source id verbatim.
    assert dct.static_gtfs_url == "https://example.org/dct.zip"
    assert dct.country == "US"
    assert dct.subdivision_name == "California"
    assert dct.license_note == "License: https://example.org/license"
    assert dct.is_official is True


def test_v2_duplicate_selection_is_independent_of_source_order() -> None:
    duplicates = [
        feed
        for feed in parse_catalog(V2_FIXTURE.read_text())
        if feed.mdb_id in {"mdb-100", "mdb-101"}
    ]

    first = propose_agencies(duplicates)
    reversed_order = propose_agencies(list(reversed(duplicates)))

    assert [proposal.mdb_id for proposal in first] == ["mdb-100"]
    assert [proposal.mdb_id for proposal in reversed_order] == ["mdb-100"]


def test_v2_numeric_registry_id_suppresses_prefixed_catalog_id() -> None:
    proposals = propose_agencies(
        parse_catalog(V2_FIXTURE.read_text()),
        existing_mdb_ids={"100"},
    )

    assert {proposal.mdb_id for proposal in proposals} == {"mdb-200"}


def test_v2_pipe_delimited_realtime_kinds_attach_to_each_static_reference() -> None:
    proposals = propose_agencies(parse_catalog(V2_FIXTURE.read_text()))
    by_mdb = {proposal.mdb_id: proposal for proposal in proposals}
    expected = {
        "trip_updates": "https://example.org/regional.pb",
        "vehicle_positions": "https://example.org/regional.pb",
    }

    # The realtime row references the lean duplicate of the first schedule with
    # its legacy numeric id and the second with its V2 id. Canonical equality
    # joins both, and endpoint grouping carries the first link to the rich row.
    assert by_mdb["mdb-100"].rt_urls == expected
    assert by_mdb["mdb-200"].rt_urls == expected


def test_catalog_fetch_exposes_exact_bytes_for_one_fetch_parse_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import mobilitydb as m

    calls: list[tuple[str, int, int]] = []

    def fake_safe_get(url: str, *, timeout: int, max_bytes: int) -> bytes:
        calls.append((url, timeout, max_bytes))
        return b"id,data_type\nsource,gtfs\n"

    monkeypatch.setattr(m, "safe_get", fake_safe_get)

    assert fetch_catalog_bytes("https://example.org/catalog.csv").startswith(b"id,")
    assert fetch_catalog("https://example.org/catalog.csv").endswith("gtfs\n")
    assert calls == [
        ("https://example.org/catalog.csv", 60, 128 * 1024 * 1024),
        ("https://example.org/catalog.csv", 60, 128 * 1024 * 1024),
    ]


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


_AMBIGUOUS_RT_CATALOG = (
    "mdb_source_id,data_type,entity_type,provider,name,urls.direct_download,"
    "urls.authentication_type,static_reference,status,is_official\n"
    "schedule,gtfs,,Demo Transit,Demo Transit,https://example.org/schedule.zip,"
    "0,,active,true\n"
    "tu-a,gtfs-rt,tu,Demo Transit,Trip Updates A,https://example.org/tu-a.pb,"
    "0,schedule,active,true\n"
    "tu-b,gtfs-rt,tu,Demo Transit,Trip Updates B,https://example.org/tu-b.pb,"
    "0,schedule,active,true\n"
    "vp,gtfs-rt,vp,Demo Transit,Vehicle Positions,https://example.org/vp.pb,"
    "0,schedule,active,true\n"
)


def test_multiple_same_kind_realtime_urls_are_not_chosen_arbitrarily() -> None:
    (proposal,) = propose_agencies(parse_catalog(_AMBIGUOUS_RT_CATALOG))

    assert proposal.rt_urls == {
        "vehicle_positions": "https://example.org/vp.pb",
    }
    assert "multiple keyless Trip Updates endpoints" in proposal.rt_note
    assert "canonical URL is ambiguous" in proposal.rt_note


def test_ambiguous_realtime_selection_is_independent_of_row_order() -> None:
    feeds = parse_catalog(_AMBIGUOUS_RT_CATALOG)

    forward = propose_agencies(feeds)
    reverse = propose_agencies(list(reversed(feeds)))

    assert reverse == forward


def test_duplicate_identical_realtime_urls_remain_unambiguous() -> None:
    catalog = (
        "mdb_source_id,data_type,entity_type,provider,name,urls.direct_download,"
        "urls.authentication_type,static_reference,status,is_official\n"
        "schedule,gtfs,,Demo Transit,Demo Transit,https://example.org/schedule.zip,"
        "0,,active,true\n"
        "tu-a,gtfs-rt,tu,Demo Transit,Trip Updates A,https://example.org/tu.pb,"
        "0,schedule,active,true\n"
        "tu-b,gtfs-rt,tu,Demo Transit,Trip Updates B,https://example.org/tu.pb,"
        "none,schedule,active,true\n"
    )

    (proposal,) = propose_agencies(parse_catalog(catalog))

    assert proposal.rt_urls == {"trip_updates": "https://example.org/tu.pb"}
    assert proposal.rt_note == ""


def test_mixed_open_and_authenticated_realtime_references_fail_closed() -> None:
    catalog = (
        "mdb_source_id,data_type,entity_type,provider,name,urls.direct_download,"
        "urls.authentication_type,static_reference,status,is_official\n"
        "schedule,gtfs,,Demo Transit,Demo Transit,https://example.org/schedule.zip,"
        "0,,active,true\n"
        "tu-open,gtfs-rt,tu,Demo Transit,Open TU,https://example.org/open-tu.pb,"
        "0,schedule,active,true\n"
        "tu-gated,gtfs-rt,tu,Demo Transit,Gated TU,https://example.org/gated-tu.pb,"
        "1,schedule,active,true\n"
        "vp-open,gtfs-rt,vp,Demo Transit,Open VP,https://example.org/vp.pb,"
        "0,schedule,active,true\n"
        "sa-gated,gtfs-rt,sa,Demo Transit,Gated SA,https://example.org/sa.pb,"
        "2,schedule,active,true\n"
    )

    (proposal,) = propose_agencies(parse_catalog(catalog))

    assert proposal.rt_urls == {"vehicle_positions": "https://example.org/vp.pb"}
    assert "both keyless and access-key Trip Updates references" in proposal.rt_note
    assert "No Trip Updates endpoint was attached" in proposal.rt_note
    assert "Service Alerts" in proposal.rt_note
    assert "need an access key" in proposal.rt_note
    assert proposal.rt_note.endswith("Nothing here counts against the grade.")


def test_candidate_ledger_keeps_realtime_review_flags_per_kind() -> None:
    catalog = (
        "mdb_source_id,data_type,entity_type,provider,name,urls.direct_download,"
        "urls.authentication_type,static_reference,status,is_official\n"
        "schedule,gtfs,,Demo Transit,Demo Transit,https://example.org/schedule.zip,"
        "0,,active,true\n"
        "tu-open,gtfs-rt,tu,Demo Transit,Open TU,https://example.org/open-tu.pb,"
        "0,schedule,active,true\n"
        "tu-gated,gtfs-rt,tu,Demo Transit,Gated TU,https://example.org/gated-tu.pb,"
        "1,schedule,active,true\n"
        "vp-a,gtfs-rt,vp,Demo Transit,VP A,https://example.org/vp-a.pb,"
        "0,schedule,active,true\n"
        "vp-b,gtfs-rt,vp,Demo Transit,VP B,https://example.org/vp-b.pb,"
        "0,schedule,active,true\n"
        "sa-gated,gtfs-rt,sa,Demo Transit,Gated SA,https://example.org/sa.pb,"
        "2,schedule,active,true\n"
    )

    _proposals, dispositions = propose_agencies_with_dispositions(parse_catalog_records(catalog))

    assert dispositions[0].review_flags == (
        "license_not_stated",
        "realtime_service_alerts_authentication_required",
        "realtime_trip_updates_access_conflict",
        "realtime_vehicle_positions_ambiguous",
    )


def test_explicitly_unofficial_realtime_does_not_create_access_conflict() -> None:
    catalog = (
        "mdb_source_id,data_type,entity_type,provider,name,urls.direct_download,"
        "urls.authentication_type,static_reference,status,is_official\n"
        "schedule,gtfs,,Demo Transit,Demo Transit,https://example.org/schedule.zip,"
        "0,,active,true\n"
        "tu-official,gtfs-rt,tu,Demo Transit,Official TU,https://example.org/tu.pb,"
        "0,schedule,active,true\n"
        "tu-unofficial,gtfs-rt,tu,Demo Transit,Unofficial TU,"
        "https://example.org/unofficial-tu.pb,1,schedule,active,false\n"
    )

    (proposal,) = propose_agencies(parse_catalog(catalog))

    assert proposal.rt_urls == {"trip_updates": "https://example.org/tu.pb"}
    assert proposal.rt_note == ""


def test_key_gated_schedule_feed_is_not_registry_ready() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download,"
        "urls.authentication_type\n"
        "open,gtfs,Open Transit,Open Transit,https://ex.org/open.zip,0\n"
        "gated,gtfs,Gated Transit,Gated Transit,https://ex.org/gated.zip,1\n"
    )

    proposals = propose_agencies(parse_catalog(catalog))

    assert [proposal.mdb_id for proposal in proposals] == ["open"]


def test_existing_ids_are_skipped() -> None:
    feeds = parse_catalog(CATALOG)
    proposals = propose_agencies(feeds, country="US", existing_ids={"davis-community-transit"})
    assert "davis-community-transit" not in {p.id for p in proposals}


def test_existing_catalog_ids_and_normalized_urls_are_skipped() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download\n"
        "tracked-id,gtfs,Renamed Transit,Renamed Transit,https://ex.org/renamed.zip\n"
        "url-copy,gtfs,URL Copy,URL Copy,https://tracked.example/feed.zip/\n"
        "fresh,gtfs,Fresh Transit,Fresh Transit,https://ex.org/fresh.zip\n"
    )

    proposals = propose_agencies(
        parse_catalog(catalog),
        existing_mdb_ids={"tracked-id"},
        existing_feed_urls={"http://tracked.example/feed.zip"},
    )

    assert [proposal.mdb_id for proposal in proposals] == ["fresh"]


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
    assert slugify("大新東", "mdb-jbda-daishinto-Radiant-City") == "mdb-jbda-daishinto-radiant-city"
    opaque = slugify("大新東", "完全")
    assert opaque.startswith("mdb-catalog-")
    assert opaque == opaque.lower()
    assert opaque.isascii()


def test_collision_suffix_sanitizes_mixed_case_catalog_ids() -> None:
    catalog = (
        "mdb_source_id,data_type,provider,name,urls.direct_download\n"
        "mdb-Upper.A,gtfs,Shared Transit,First,https://example.org/first.zip\n"
        "Other-ID,gtfs,Shared Transit,Second,https://example.org/second.zip\n"
    )
    proposals = propose_agencies(parse_catalog(catalog), existing_ids={"shared-transit"})

    assert {proposal.id for proposal in proposals} == {
        "shared-transit-mdb-upper-a",
        "shared-transit-other-id",
    }
    parse_agencies(yaml.safe_load("agencies:\n" + render_yaml(proposals)))


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


@pytest.mark.parametrize(
    "current_url",
    [
        "javascript://www.yolobus.com/GTFS/google_transit.zip",
        "ftp://www.yolobus.com/GTFS/google_transit.zip",
        "//www.yolobus.com/GTFS/google_transit.zip",
        "https:///GTFS/google_transit.zip",
        "https://user@www.yolobus.com/GTFS/google_transit.zip",
        "http://www.yolobus.com:443/GTFS/google_transit.zip",
        "https://www.yolobus.com:80/GTFS/google_transit.zip",
    ],
)
def test_hosted_mirror_url_rejects_unsafe_or_port_ambiguous_current_urls(
    monkeypatch: pytest.MonkeyPatch, current_url: str
) -> None:
    from scorecard_pipeline import mobilitydb as m

    feeds = parse_catalog(MIRROR_CATALOG)
    monkeypatch.setattr(m, "load_catalog", lambda **_: feeds)

    assert m.hosted_mirror_url("yolobus", "Yolobus", current_url) is None
