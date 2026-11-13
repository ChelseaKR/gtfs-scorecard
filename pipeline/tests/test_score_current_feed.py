"""Records that moved off a mirror copy, and the guards that keep them honest."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.agencies import read_agencies
from scorecard_pipeline.comparisons import same_producer_contract, scored_from_mirror
from scorecard_pipeline.config import Agency
from scorecard_pipeline.feed_provenance import mirror_copy_caveat
from scorecard_pipeline.fixlog import diff_receipts
from scorecard_pipeline.mobilitydb import (
    CatalogFeed,
    FeedMatch,
    hold_pinned_hosts,
    is_frozen_archive,
    replacement_url,
)
from scorecard_pipeline.publish import _history_entry

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every URL below answered with a GTFS zip on 2026-11-08 whose agency name, stop
# count, and location were compared with the record's published copy.
MOVED_HOSTS = {
    "bell-gardens-trolley": "ips-systems.com",
    "broward-county-transit": "arcgis.com",
    "casco-bay-lines": "gtfs.remix.com",
    "cherriots": "cherriots.rideralerts.com",
    "corpus-christi-regional-transportation-authority": "gtfs.ccrta.cadavl.com",
    "elk-grove-transit": "apps.sacrt.com",
    "cascades-east-transit-cet": "passio3.com",
    "essex-bus-network": "data.essex.gov.uk/download/2ydj8/hr6/",
    "exo-trains": "exo.quebec",
    "fr-pan-83389": "data.grandpoitiers.fr",
    "fr-tul": "files.orchestra.ratpdev.com",
    "mvv-munchen": "/developer/opendata/mvv_gtfs.zip",
    "suntran-2354": "suntran.com/wp-content/uploads/SunTranGTFS.zip",
    "gold-coast-transit-south-coast-area-transit": "gctd.org",
    "lane-transit-district-ltd": "feed.ltd.org",
    "memphis-area-transit-authority-2352": "gtfs.mata.cadavl.com",
    "rio-de-janeiro-transportes": "dados.mobilidade.rio",
    "roseville-transit": "apps.sacrt.com",
    "wave-transit": "wave.connexionz.net",
}
RETIRED_INTO = {
    "advance-transit-at": "advance-transit",
    "beach-cities-transit": "beach-cities-transit-1999",
    "bellflower-bus": "bellflower-bus-3095",
    "glendora-transportation-division": "glendora-transportation-division-3097",
    "huntington-park-express": "huntington-park-express-2648",
    "rosemead-explorer": "rosemead-explorer-3098",
}


@pytest.fixture()
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Agency]:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    return {agency.id: agency for agency in read_agencies()}


def _artifact(source: str, **overrides: Any) -> dict[str, Any]:
    finding = {"code": "scorecard_feed_expired", "what": "The feed expired."}
    artifact: dict[str, Any] = {
        "agency": {"id": "a", "name": "A"},
        "snapshot_date": "2026-11-08",
        "rubric_version": "1.5",
        "validator_version": "8.0.1",
        "scoring_profile": {"id": "gtfs-scorecard-1.5", "rubric_version": "1.5"},
        "overall": {"score": 80.0, "grade": "B"},
        "feed": {"sha256": "0" * 64},
        "fetch": {"source": source, "reader_archive_profile": "raw-v1"},
        "categories": {
            "correctness": {"status": "measured", "score": 90.0, "findings": []},
            "freshness": {
                "status": "measured",
                "score": 70.0,
                "findings": [finding],
                "details": {"feed_start_date": "2024-08-17", "feed_end_date": "2025-01-05"},
            },
            "completeness": {"status": "measured", "score": 80.0, "findings": []},
        },
    }
    artifact.update(overrides)
    return artifact


def test_mirror_caveat_says_when_the_copy_was_downloaded() -> None:
    caveat = mirror_copy_caveat(_artifact("mirror", snapshot_date="2026-10-19"))
    assert "mirror copy downloaded on 2026-10-19, because" in caveat
    assert "2024-08-17 to 2025-01-05" in caveat
    assert caveat.endswith("It may not match the feed the agency publishes today.")


def test_mirror_caveat_reads_the_download_date_off_a_swept_artifact() -> None:
    swept = _artifact(
        "mirror",
        snapshot_date="2026-11-06",
        recompute={"kind": "freshness", "as_of": "2026-11-06", "feed_fetched_date": "2026-09-12"},
    )
    assert "downloaded on 2026-09-12," in mirror_copy_caveat(swept)
    assert "2026-11-06" not in mirror_copy_caveat(swept)


@pytest.mark.parametrize(
    "overrides",
    [
        {"snapshot_date": None},
        {"snapshot_date": "not a date"},
        {"recompute": {"kind": "freshness"}},
    ],
)
def test_mirror_caveat_leaves_an_unknown_download_date_out(overrides: dict[str, Any]) -> None:
    caveat = mirror_copy_caveat(_artifact("mirror", **overrides))
    assert "downloaded on" not in caveat
    assert caveat.startswith("Scored from a Mobility Database mirror copy, because")


def test_mirror_caveat_stays_empty_for_the_agencys_own_url() -> None:
    assert mirror_copy_caveat(_artifact("origin")) == ""


def test_a_move_from_a_mirror_copy_is_not_a_comparable_transition() -> None:
    mirror, origin = _artifact("mirror"), _artifact("origin")
    assert not same_producer_contract(mirror, origin)
    assert not same_producer_contract(origin, mirror)
    # Controls: the guard only separates the two kinds of source.
    assert same_producer_contract(origin, _artifact("origin"))
    assert same_producer_contract(mirror, _artifact("mirror"))


def test_a_move_from_a_mirror_copy_clears_no_findings() -> None:
    before = _artifact("mirror")
    after = copy.deepcopy(_artifact("origin"))
    after["categories"]["freshness"]["findings"] = []
    assert diff_receipts(before, after) == []

    # Control: the same change between two reads of the agency's URL is a receipt.
    control = diff_receipts(_artifact("origin"), after)
    assert [receipt["code"] for receipt in control] == ["scorecard_feed_expired"]


def test_history_points_carry_the_mark_only_for_a_mirror_copy() -> None:
    mirror_point = _history_entry(_artifact("mirror"))
    origin_point = _history_entry(_artifact("origin"))
    assert mirror_point["fetch_source"] == "mirror"
    assert "fetch_source" not in origin_point
    assert scored_from_mirror(mirror_point)
    assert not scored_from_mirror(origin_point)
    assert not same_producer_contract(mirror_point, origin_point)


def _feed(url: str) -> CatalogFeed:
    return CatalogFeed(
        mdb_id="mdb-1",
        data_type="gtfs",
        entity_type="",
        country="US",
        subdivision_code="",
        subdivision="",
        municipality="",
        provider="Example",
        name="",
        direct_download=url,
        license_url="",
        authentication_type="",
        static_reference="",
    )


@pytest.mark.parametrize(
    "archive",
    [
        "https://openmobilitydata-data.s3.us-west-1.amazonaws.com/public/feeds/ride-sitka/713/20180520/gtfs.zip",
        "https://transitfeeds.com/p/ride-sitka/713/latest/download",
        "https://github.com/transitland/gtfs-archives-not-hosted-elsewhere/raw/master/x.zip",
    ],
)
def test_discovery_never_moves_a_record_onto_a_frozen_archive(archive: str) -> None:
    assert is_frozen_archive(archive)
    match = FeedMatch("a", "A", "https://old.example.org/gtfs.zip", "replaced", [_feed(archive)])
    assert replacement_url(match) is None

    # Control: a live candidate listed after the archive is still followed.
    live = _feed("https://new.example.org/gtfs.zip")
    match = FeedMatch(
        "a", "A", "https://old.example.org/gtfs.zip", "replaced", [_feed(archive), live]
    )
    assert replacement_url(match) == "https://new.example.org/gtfs.zip"


def test_a_lookalike_host_is_not_a_frozen_archive() -> None:
    assert not is_frozen_archive("https://nottransitfeeds.com/p/x/1/latest/download")
    assert not is_frozen_archive("https://github.com/transitland/other-repo/raw/main/x.zip")


@pytest.mark.parametrize(("agency_id", "host"), sorted(MOVED_HOSTS.items()))
def test_moved_records_track_the_verified_host(
    registry: dict[str, Agency], agency_id: str, host: str
) -> None:
    agency = registry[agency_id]
    assert host in agency.static_gtfs_url
    assert agency.feed_status == "active"
    assert not is_frozen_archive(agency.static_gtfs_url)
    assert "Checked 2026-11-08" in agency.operating_note


@pytest.mark.parametrize(
    "agency_id",
    [
        "fr-agglo-en-bus",
        "fr-cmonbus",
        "fr-pan-76779",
        "fr-pan-81252",
        "fr-pan-82619",
        "fr-pan-83389",
        "fr-pan-83990",
        "fr-pan-84096",
        "fr-tul",
    ],
)
def test_french_moves_leave_the_disallowed_host_and_carry_no_key(
    registry: dict[str, Agency], agency_id: str
) -> None:
    url = registry[agency_id].static_gtfs_url
    assert "data.gouv.fr" not in url
    assert "key=" not in url.lower()
    assert registry[agency_id].reuse_evidence is not None


@pytest.mark.parametrize("path", ["NOTICE", "web/fetcher/index.html"])
def test_transitland_atlas_is_credited_with_its_license_as_published(path: str) -> None:
    text = " ".join((REPO_ROOT / path).read_text().split())
    assert "github.com/transitland/transitland-atlas" in text
    assert (
        "Unless otherwise indicated, data files and scripts in this repository are "
        "made available under the Creative Commons Attribution 4.0 International Public "
        "License."
    ) in text


@pytest.mark.parametrize("agency_id", sorted(MOVED_HOSTS))
def test_weekly_discovery_holds_a_moved_record_instead_of_moving_it_back(
    registry: dict[str, Agency], agency_id: str
) -> None:
    agency = registry[agency_id]
    proposal = FeedMatch(
        agency_id,
        agency.name,
        agency.static_gtfs_url,
        "replaced",
        [_feed("https://old.example.org/stale.zip")],
    )
    ready, held = hold_pinned_hosts([proposal], registry)
    assert (ready, held) == ([], [proposal])


@pytest.mark.parametrize(("agency_id", "successor"), sorted(RETIRED_INTO.items()))
def test_records_with_a_published_successor_retire_into_it(
    registry: dict[str, Agency], agency_id: str, successor: str
) -> None:
    agency = registry[agency_id]
    assert agency.alias_of == successor
    assert agency.feed_status == "deprecated"
    assert registry[successor].feed_status == "active"
    # The one cross-state pair is a rename too, and has a review entry.
    assert registry[successor].name in agency.name
