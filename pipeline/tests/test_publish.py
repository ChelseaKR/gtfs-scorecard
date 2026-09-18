"""Tests for artifact publishing: schema shape, idempotency, index history."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import (
    RUBRIC_VERSION,
    SCHEMA_VERSION,
    SCORING_PROFILE_ID,
    SCORING_PROFILE_PROVENANCE,
)
from scorecard_pipeline.config import Agency, artifacts_dir
from scorecard_pipeline.dataset import build_quality_dataset
from scorecard_pipeline.fetch import (
    FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE,
    RAW_READER_ARCHIVE_PROFILE,
    USER_AGENT,
    FetchResult,
)
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import (
    _history_entry,
    build_artifact,
    enrich_index_history_provenance,
    publish,
)
from scorecard_pipeline.score import build_scorecard

AGENCY = Agency(
    id="unitrans",
    name="Unitrans",
    static_gtfs_url="https://example.org/gtfs.zip",
    license_note="test",
)
GENERATED_AT = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)
FEED_SHA = "a" * 64


def make_fetch(date: dt.date, source: str = "unknown") -> FetchResult:
    return FetchResult(
        agency_id=AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=AGENCY.static_gtfs_url,
        fetched_date=date,
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
        source=source,
    )


def make_artifact(date: dt.date, score: float = 88.0) -> dict:  # type: ignore[type-arg]
    card = build_scorecard([CategoryResult(name="correctness", score=score, summary="s")])
    return build_artifact(AGENCY, make_fetch(date), card, GENERATED_AT)


ALL_CATEGORIES = ("correctness", "freshness", "completeness", "realtime")


def test_artifact_schema_essentials() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["scoring_profile"] == {
        "id": SCORING_PROFILE_ID,
        "rubric_version": RUBRIC_VERSION,
        "provenance": SCORING_PROFILE_PROVENANCE,
    }
    assert artifact["agency"] == {"id": "unitrans", "name": "Unitrans"}
    assert artifact["snapshot_date"] == "2026-06-11"
    assert artifact["feed"]["sha256"] == FEED_SHA
    assert artifact["overall"]["grade"] == "B"
    assert artifact["categories"]["realtime"]["status"] == "not_yet_measured"
    assert len(artifact["top_fixes"]) <= 3
    # Fetch provenance rides on every artifact (FIX-01). A FetchResult without
    # recorded provenance states source "unknown" and falls back to the
    # configured feed URL; optional fields are omitted.
    assert artifact["fetch"] == {
        "source": "unknown",
        "final_url": AGENCY.static_gtfs_url,
        "user_agent": USER_AGENT,
        "reader_archive_profile": RAW_READER_ARCHIVE_PROFILE,
    }


def test_history_entry_derives_legacy_horizon_status_for_public_api() -> None:
    artifact = make_artifact(dt.date(2026, 7, 13))
    artifact["categories"]["freshness"] = {
        "name": "freshness",
        "status": "measured",
        "score": 100.0,
        "summary": "Review the distant end date.",
        "findings": [],
        "details": {"days_until_expiry": 26_834},
    }
    entry = _history_entry(artifact)
    assert entry["days_until_expiry"] == 26_834
    assert entry["service_horizon_status"] == "unusually_distant"


def test_history_entry_keeps_genuinely_unknown_legacy_horizon_unknown() -> None:
    artifact = make_artifact(dt.date(2026, 7, 13))
    artifact["categories"]["freshness"] = {
        "name": "freshness",
        "status": "measured",
        "score": 0.0,
        "summary": "No service end date could be found.",
        "findings": [],
        "details": {"days_until_expiry": None},
    }
    assert _history_entry(artifact)["service_horizon_status"] == "unknown"


def test_fetch_provenance_block_carries_mirror_details() -> None:
    fetch = FetchResult(
        agency_id=AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=AGENCY.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
        source="mirror",
        final_url="https://storage.googleapis.com/mdb-latest/x.zip",
        max_attempts=1,
        origin_error="ConnectTimeout",
    )
    card = build_scorecard([CategoryResult(name="correctness", score=88.0, summary="s")])
    artifact = build_artifact(AGENCY, fetch, card, GENERATED_AT)
    assert artifact["fetch"] == {
        "source": "mirror",
        "final_url": "https://storage.googleapis.com/mdb-latest/x.zip",
        "user_agent": USER_AGENT,
        "reader_archive_profile": RAW_READER_ARCHIVE_PROFILE,
        "max_attempts": 1,
        "origin_error": "ConnectTimeout",
    }
    # feed.static_url still records the configured origin URL, unchanged.
    assert artifact["feed"]["static_url"] == AGENCY.static_gtfs_url


def test_fetch_provenance_discloses_reader_archive_normalization() -> None:
    raw_path = Path("/tmp/gtfs.zip")
    fetch = FetchResult(
        agency_id=AGENCY.id,
        path=raw_path,
        url=AGENCY.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
        reader_path=Path("/tmp/gtfs.reader.zip"),
        reader_archive_normalized=True,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=88.0, summary="s")])

    artifact = build_artifact(AGENCY, fetch, card, GENERATED_AT)

    assert artifact["feed"]["sha256"] == FEED_SHA
    assert artifact["fetch"]["reader_archive_normalized"] is True
    assert artifact["fetch"]["reader_archive_profile"] == FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE
    assert _history_entry(artifact)["reader_archive_profile"] == (
        FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE
    )


def test_unknown_reader_profile_fails_closed_through_history_and_dataset() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["fetch"]["reader_archive_profile"] = ""

    history = _history_entry(artifact)
    dataset = build_quality_dataset(
        {"agencies": {AGENCY.id: {"name": AGENCY.name, "history": [history]}}}
    )
    row = dataset["rows"][0]

    assert history["reader_archive_profile"] == ""
    assert row["reader_archive_profile"] == ""
    assert row["comparison_eligible"] is False
    assert dataset["comparison"]["exclusion_counts"]["reader_archive_profile_mismatch"] == 1


def test_confidence_high_when_all_measured_from_origin() -> None:
    card = build_scorecard(
        [
            CategoryResult(
                name=name,
                score=90.0,
                summary="s",
                details={"samples": 5} if name == "realtime" else {},
            )
            for name in ALL_CATEGORIES
        ]
    )
    fetch = make_fetch(dt.date(2026, 6, 11), source="origin")
    artifact = build_artifact(AGENCY, fetch, card, GENERATED_AT)
    conf = artifact["confidence"]
    assert conf["level"] == "high"
    assert conf["measured_categories"] == 4
    assert conf["total_categories"] == 4
    assert conf["fetch_source"] == "origin"
    assert conf["rt_windows"] == 1
    assert conf["feed_age_days"] == 0
    assert any("5 snapshots" in n for n in conf["notes"])
    assert artifact["feed"]["source_provenance"] == "unverified"
    assert any("Publisher ownership of that URL is not verified" in n for n in conf["notes"])
    assert all("agency's own" not in n for n in conf["notes"])


@pytest.mark.parametrize(
    ("static_url", "is_official", "fetch_source", "expected_class", "expected_note"),
    [
        (
            "https://agency.example/gtfs.zip",
            True,
            "origin",
            "official",
            "The feed was downloaded from the official feed URL on file.",
        ),
        (
            "https://transitfeeds.com/p/example/1/latest/download",
            None,
            "mirror",
            "archive",
            "The archived feed URL on file was unreachable, so the Mobility Database's "
            "hosted mirror copy was scored instead.",
        ),
        (
            "https://third-party.example/gtfs.zip",
            False,
            "origin",
            "third_party",
            "The feed was downloaded from a third-party feed URL on file.",
        ),
        (
            "https://github.com/mobilityequity/example/raw/main/gtfs.zip",
            None,
            "origin",
            "unverified",
            "The feed was downloaded from the configured feed URL. Publisher ownership of that "
            "URL is not verified.",
        ),
    ],
)
def test_feed_source_provenance_is_explicit_and_never_inferred_from_fetch_success(
    static_url: str,
    is_official: bool | None,
    fetch_source: str,
    expected_class: str,
    expected_note: str,
) -> None:
    agency = Agency(
        id="provenance-demo",
        name="Provenance Demo",
        static_gtfs_url=static_url,
        is_official=is_official,
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
        source=fetch_source,
    )
    card = build_scorecard(
        [CategoryResult(name=name, score=90.0, summary="s") for name in ALL_CATEGORIES]
    )

    artifact = build_artifact(agency, fetch, card, GENERATED_AT)

    assert artifact["feed"]["source_provenance"] == expected_class
    assert expected_note in artifact["confidence"]["notes"]
    assert all("agency's own" not in note for note in artifact["confidence"]["notes"])


def test_confidence_provisional_when_realtime_missing_and_mirror_fetched() -> None:
    card = build_scorecard(
        [
            CategoryResult(name=name, score=80.0, summary="s")
            for name in ("correctness", "freshness", "completeness")
        ]
    )
    fetch = make_fetch(dt.date(2026, 6, 11), source="mirror")
    artifact = build_artifact(AGENCY, fetch, card, GENERATED_AT)
    conf = artifact["confidence"]
    assert conf["level"] == "provisional"
    assert conf["measured_categories"] == 3
    assert conf["fetch_source"] == "mirror"
    assert conf["rt_windows"] == 0
    assert artifact["fetch"]["source"] == "mirror"
    assert any("mirror" in n for n in conf["notes"])
    assert any("Realtime quality was not measured" in n for n in conf["notes"])
    # The level is a word, never a letter grade or a number out of 100.
    assert conf["level"] not in "ABCDF"


def test_confidence_unknown_fetch_source_is_flagged_and_floors_at_provisional() -> None:
    # One measured category is already provisional; an unrecorded fetch source
    # cannot push it any lower than the floor.
    card = build_scorecard([CategoryResult(name="correctness", score=88.0, summary="s")])
    fetch = make_fetch(dt.date(2026, 6, 11), source="unknown")
    conf = build_artifact(AGENCY, fetch, card, GENERATED_AT)["confidence"]
    assert conf["level"] == "provisional"
    assert any("not known" in n for n in conf["notes"])
    # Three unmeasured categories are named, and framed as not counting.
    assert any("do not count against the grade" in n for n in conf["notes"])


def test_confidence_stale_snapshot_drops_a_full_measurement_to_medium() -> None:
    card = build_scorecard(
        [CategoryResult(name=name, score=90.0, summary="s") for name in ALL_CATEGORIES]
    )
    # Scored 10 days after the snapshot was fetched: stale evidence.
    fetch = make_fetch(dt.date(2026, 6, 1), source="origin")
    conf = build_artifact(AGENCY, fetch, card, GENERATED_AT)["confidence"]
    assert conf["level"] == "medium"
    assert conf["feed_age_days"] == 10
    assert any("10 days old" in n for n in conf["notes"])
    # Realtime measured but without a recorded sample count still gets a note.
    assert any("one bounded window" in n for n in conf["notes"])


def test_publish_writes_dated_latest_and_index() -> None:
    path = publish(make_artifact(dt.date(2026, 6, 11)))
    assert path == artifacts_dir() / "unitrans" / "2026-06-11.json"
    assert path.exists()
    latest = json.loads((artifacts_dir() / "unitrans" / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-11"
    index = json.loads((artifacts_dir() / "index.json").read_text())
    entry = index["agencies"]["unitrans"]["history"][0]
    assert entry["date"] == "2026-06-11"
    assert entry["score"] == 88.0
    assert entry["grade"] == "B"
    assert entry["rubric_version"] == RUBRIC_VERSION
    assert entry["feed_sha256"] == FEED_SHA
    # History carries per-category scores for trend rendering.
    assert "correctness" in entry["categories"]


def test_publish_rederives_embedded_legacy_conformance_copy() -> None:
    from scorecard_pipeline.conformance import CONFORMANCE_VERSION

    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["conformance"] = {
        "version": CONFORMANCE_VERSION - 1,
        "awarded": False,
        "status": "not_yet",
        "summary": "This feed is close to the conformance mark.",
        "criteria": [],
    }

    dated = publish(artifact)

    latest = json.loads((dated.parent / "latest.json").read_text())
    credential = json.loads((dated.parent / "conformance.json").read_text())
    persisted = json.loads(dated.read_text())
    for payload in (persisted["conformance"], latest["conformance"], credential):
        assert payload["version"] == CONFORMANCE_VERSION
        assert "close to" not in payload["summary"].lower()


def test_enrich_index_history_provenance_backfills_local_dated_artifact() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    agency_dir = artifacts_dir() / "unitrans"
    agency_dir.mkdir(parents=True)
    (agency_dir / "2026-06-11.json").write_text(json.dumps(artifact))
    point = _history_entry(artifact)
    del point["rubric_version"]
    del point["feed_sha256"]
    index = {"agencies": {"unitrans": {"history": [point]}}}

    changed = enrich_index_history_provenance(index)

    assert changed == 2
    assert point["rubric_version"] == RUBRIC_VERSION
    assert point["feed_sha256"] == FEED_SHA


def test_publish_writes_shields_badge_json() -> None:
    publish(make_artifact(dt.date(2026, 6, 11), score=88.0))  # grade B
    badge = json.loads((artifacts_dir() / "unitrans" / "badge.json").read_text())
    assert badge["schemaVersion"] == 1
    assert badge["label"] == "GTFS quality"
    assert badge["message"].startswith("B 88")
    assert badge["color"] == "green"


def test_republish_same_day_is_idempotent() -> None:
    publish(make_artifact(dt.date(2026, 6, 11)))
    first = (artifacts_dir() / "unitrans" / "2026-06-11.json").read_bytes()
    publish(make_artifact(dt.date(2026, 6, 11)))
    second = (artifacts_dir() / "unitrans" / "2026-06-11.json").read_bytes()
    assert first == second
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert len(index["agencies"]["unitrans"]["history"]) == 1


def test_index_accumulates_history_in_date_order() -> None:
    publish(make_artifact(dt.date(2026, 6, 12), score=91.0))
    publish(make_artifact(dt.date(2026, 6, 11), score=88.0))
    index = json.loads((artifacts_dir() / "index.json").read_text())
    history = index["agencies"]["unitrans"]["history"]
    assert [h["date"] for h in history] == ["2026-06-11", "2026-06-12"]
    assert [h["grade"] for h in history] == ["B", "A"]


def test_operating_note_rides_on_artifact_and_index_when_set() -> None:
    agency = Agency(
        id="lapsed-co",
        name="Lapsed County Transit",
        static_gtfs_url="https://example.org/g.zip",
        operating_note="Confirmed still operating as of 2026-06; vendor stopped refreshing.",
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=80.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, GENERATED_AT)
    assert artifact["agency"]["operating_note"].startswith("Confirmed still operating")

    publish(artifact)
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert index["agencies"]["lapsed-co"]["operating_note"].startswith("Confirmed")


def test_state_is_persisted_in_the_artifact_when_set() -> None:
    agency = Agency(
        id="ca-co",
        name="CA County Transit",
        static_gtfs_url="https://example.org/g.zip",
        state="CA",
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=80.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, GENERATED_AT)
    assert artifact["agency"]["state"] == "CA"
    # Absent when unset (the default AGENCY has no state).
    assert "state" not in make_artifact(dt.date(2026, 6, 11))["agency"]


def test_country_is_persisted_only_when_not_us() -> None:
    agency = Agency(
        id="ca-yt",
        name="Whitehorse Transit",
        static_gtfs_url="https://example.org/g.zip",
        country="CA",
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=80.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, GENERATED_AT)
    assert artifact["agency"]["country"] == "CA"
    # Omitted for US agencies so their artifacts stay byte-identical.
    assert "country" not in make_artifact(dt.date(2026, 6, 11))["agency"]


def test_iso_subdivision_is_persisted_without_changing_legacy_state() -> None:
    agency = Agency(
        id="barrie",
        name="Barrie Transit",
        static_gtfs_url="https://example.org/g.zip",
        country="CA",
        subdivision_code="CA-ON",
        subdivision_name="Ontario",
    )
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256=FEED_SHA,
        size_bytes=1024,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=88.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, GENERATED_AT)
    assert artifact["agency"]["subdivision_code"] == "CA-ON"
    assert artifact["agency"]["subdivision_name"] == "Ontario"
    assert "state" not in artifact["agency"]


def test_operating_note_absent_keeps_agency_block_minimal() -> None:
    # The default AGENCY has no operating_note; the agency block stays two keys.
    artifact = make_artifact(dt.date(2026, 6, 11))
    assert "operating_note" not in artifact["agency"]
    publish(artifact)
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert "operating_note" not in index["agencies"]["unitrans"]


def test_reindex_recovers_corrupt_current_dated_from_authoritative_latest() -> None:
    # The S3 latest/index pair is the durable current record. If the matching
    # dated copy is corrupt, reindex keeps the verified current summary while
    # warning about (and not rewriting) the immutable dated object.
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 17), score=72.0))
    publish(make_artifact(dt.date(2026, 6, 18), score=84.0))
    # Corrupt the middle day: a complete object followed by trailing data.
    bad = artifacts_dir() / "unitrans" / "2026-06-18.json"
    good_text = bad.read_text()
    bad.write_text(good_text + good_text)

    # Must not raise even though one file is unparseable.
    rebuild_index()

    index = json.loads((artifacts_dir() / "index.json").read_text())
    dates = [h["date"] for h in index["agencies"]["unitrans"]["history"]]
    assert dates == ["2026-06-17", "2026-06-18"]
    latest = json.loads((artifacts_dir() / "unitrans" / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-18"
    assert latest["overall"]["score"] == 84.0


def test_reindex_drops_corrupt_historical_dated_artifact() -> None:
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 17), score=72.0))
    publish(make_artifact(dt.date(2026, 6, 18), score=84.0))
    publish(make_artifact(dt.date(2026, 6, 19), score=90.0))
    bad = artifacts_dir() / "unitrans" / "2026-06-18.json"
    bad.write_text(bad.read_text() + bad.read_text())

    rebuild_index()

    index = json.loads((artifacts_dir() / "index.json").read_text())
    dates = [h["date"] for h in index["agencies"]["unitrans"]["history"]]
    assert dates == ["2026-06-17", "2026-06-19"]
    latest = json.loads((artifacts_dir() / "unitrans" / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-19"


def test_reindex_drops_dated_artifact_with_mismatched_identity_or_date() -> None:
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 17), score=72.0))
    agency_dir = artifacts_dir() / "unitrans"

    wrong_id = make_artifact(dt.date(2026, 6, 18), score=99.0)
    wrong_id["agency"]["id"] = "wrong-id"
    (agency_dir / "2026-06-18.json").write_text(json.dumps(wrong_id))

    wrong_date = make_artifact(dt.date(2026, 6, 19), score=99.0)
    wrong_date["snapshot_date"] = "2099-01-01"
    (agency_dir / "2026-06-19.json").write_text(json.dumps(wrong_date))

    invalid_date = make_artifact(dt.date(2026, 6, 20), score=99.0)
    invalid_date["snapshot_date"] = "2026-99-99"
    (agency_dir / "2026-99-99.json").write_text(json.dumps(invalid_date))

    rebuild_index()

    index = json.loads((artifacts_dir() / "index.json").read_text())
    history = index["agencies"]["unitrans"]["history"]
    assert [item["date"] for item in history] == ["2026-06-17"]
    latest = json.loads((agency_dir / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-17"
    assert latest["overall"]["score"] == 72.0


def test_reindex_repairs_clobbered_latest_and_badge_from_newest_dated() -> None:
    # The sharded daily run can leave latest.json overwritten by a stale copy
    # while the newest dated file is intact; reindex must heal it.
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 16), score=70.0))
    publish(make_artifact(dt.date(2026, 6, 19), score=90.0))
    latest_path = artifacts_dir() / "unitrans" / "latest.json"
    # Simulate a clobber: latest.json knocked back to the older snapshot.
    latest_path.write_text(json.dumps(make_artifact(dt.date(2026, 6, 16), score=70.0)))
    assert json.loads(latest_path.read_text())["snapshot_date"] == "2026-06-16"

    rebuild_index()

    repaired = json.loads(latest_path.read_text())
    assert repaired["snapshot_date"] == "2026-06-19"
    assert repaired["overall"]["score"] == 90.0
    assert (artifacts_dir() / "unitrans" / "badge.svg").exists()
    # index history still has both days, newest last
    index = json.loads((artifacts_dir() / "index.json").read_text())
    dates = [h["date"] for h in index["agencies"]["unitrans"]["history"]]
    assert dates == ["2026-06-16", "2026-06-19"]


def test_reindex_migrates_current_conformance_without_rewriting_dated_history() -> None:
    from scorecard_pipeline.conformance import CONFORMANCE_VERSION
    from scorecard_pipeline.publish import rebuild_index

    dated = publish(make_artifact(dt.date(2026, 6, 19), score=90.0))
    legacy = json.loads(dated.read_text())
    legacy["conformance"] = {
        "version": CONFORMANCE_VERSION - 1,
        "awarded": False,
        "status": "not_yet",
        "summary": "This feed is close to the conformance mark.",
        "criteria": [],
    }
    legacy_text = json.dumps(legacy, indent=2, sort_keys=True) + "\n"
    dated.write_text(legacy_text)
    (dated.parent / "latest.json").write_text(legacy_text)

    rebuild_index()

    # Dated evidence is immutable; only mutable current views are re-derived.
    assert dated.read_text() == legacy_text
    latest = json.loads((dated.parent / "latest.json").read_text())
    credential = json.loads((dated.parent / "conformance.json").read_text())
    for payload in (latest["conformance"], credential):
        assert payload["version"] == CONFORMANCE_VERSION
        assert "close to" not in payload["summary"].lower()


def test_reindex_preserves_s3_history_not_present_in_clean_checkout() -> None:
    """The compact index remains complete after dated files move to S3."""
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 16), score=70.0))
    publish(make_artifact(dt.date(2026, 6, 17), score=80.0))
    missing_locally = artifacts_dir() / "unitrans" / "2026-06-16.json"
    missing_locally.unlink()

    rebuild_index()

    index = json.loads((artifacts_dir() / "index.json").read_text())
    dates = [item["date"] for item in index["agencies"]["unitrans"]["history"]]
    assert dates == ["2026-06-16", "2026-06-17"]


def test_reindex_preserves_authoritative_latest_when_current_dated_is_absent() -> None:
    """A skipped feed cannot roll back to the checkout's older cutover file."""
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 6, 16), score=70.0))
    publish(make_artifact(dt.date(2026, 6, 19), score=90.0))
    current_dated = artifacts_dir() / "unitrans" / "2026-06-19.json"
    current_dated.unlink()

    rebuild_index()

    latest = json.loads((artifacts_dir() / "unitrans" / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-19"
    assert latest["overall"]["score"] == 90.0
    index = json.loads((artifacts_dir() / "index.json").read_text())
    history = index["agencies"]["unitrans"]["history"]
    assert [item["date"] for item in history] == ["2026-06-16", "2026-06-19"]
    assert history[-1]["score"] == 90.0
    # Reindex uses latest in memory; it does not recreate a lifecycle-expired
    # dated object that the broad S3 sync would upload without expiry tags.
    assert not current_dated.exists()


def test_reindex_ignores_ahead_latest_when_indexed_dated_is_present() -> None:
    """A partial refresh cannot advance the index before its commit pointer."""
    from scorecard_pipeline.publish import rebuild_index

    indexed_date = dt.date(2026, 6, 19)
    publish(make_artifact(indexed_date, score=90.0))
    agency_dir = artifacts_dir() / "unitrans"

    # Simulate Intraday uploading latest.json before its final index write, then
    # losing AWS credentials. Daily hydrates the indexed dated object alongside
    # this ahead-of-index latest and must retain the indexed snapshot.
    ahead = make_artifact(dt.date(2026, 6, 20), score=95.0)
    (agency_dir / "latest.json").write_text(json.dumps(ahead))

    rebuild_index()

    latest = json.loads((agency_dir / "latest.json").read_text())
    assert latest["snapshot_date"] == indexed_date.isoformat()
    assert latest["overall"]["score"] == 90.0
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert index["agencies"]["unitrans"]["history"][-1]["date"] == indexed_date.isoformat()


def test_reindex_accepts_verified_same_day_shard_replacement() -> None:
    """A methodology re-score may replace today's artifact without changing its date."""
    from scorecard_pipeline.publish import rebuild_index

    date = dt.date(2026, 7, 14)
    publish(make_artifact(date, score=70.0))
    replacement = make_artifact(date, score=90.0)
    agency_dir = artifacts_dir() / "unitrans"
    replacement_text = json.dumps(replacement, indent=2, sort_keys=True) + "\n"
    # The shard overlays both files, but collect retains the older S3 index
    # until rebuild. Matching payloads prove this is a publish() pair rather
    # than a clobbered checkout latest.
    (agency_dir / "2026-07-14.json").write_text(replacement_text)
    (agency_dir / "latest.json").write_text(replacement_text)

    rebuild_index()

    latest = json.loads((agency_dir / "latest.json").read_text())
    assert latest["overall"]["score"] == 90.0
    index = json.loads((artifacts_dir() / "index.json").read_text())
    history = index["agencies"]["unitrans"]["history"]
    assert len(history) == 1
    assert history[0]["date"] == "2026-07-14"
    assert history[0]["score"] == 90.0


def test_reindex_purges_unverifiable_legacy_fixlog() -> None:
    """A stale legacy receipt is removed, not left public after reconciliation."""
    from scorecard_pipeline.publish import rebuild_index

    publish(make_artifact(dt.date(2026, 7, 14)))
    agency_dir = artifacts_dir() / "unitrans"
    fixlog = agency_dir / "fixlog.json"
    fixlog.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "code": "legacy",
                        "what": "No supporting artifacts remain.",
                        "last_seen": "2025-01-01",
                        "cleared": "2025-01-02",
                    }
                ]
            }
        )
    )

    rebuild_index()

    assert not fixlog.exists()


# --- The published letter must be the letter the published score earns. -------
#
# Nine live artifacts read "Grade C * 80.0 / 100" against named transit
# agencies, because build_scorecard graded the unrounded weighted score while
# to_json published round(overall, 1). score.published_overall is now the one
# derivation; these cover the two ways a wrong letter could still reach a
# reader after that fix -- written fresh by publish(), or copied forward out of
# a dated snapshot that was written before it.


def _contradicting(artifact: dict) -> dict:  # type: ignore[type-arg]
    """A copy whose overall block says C where its own 80.0 earns a B."""
    contradicted: dict = json.loads(json.dumps(artifact))  # type: ignore[type-arg]
    contradicted["overall"] = {
        "score": 80.0,
        "grade": "C",
        "margin_to_next_band": 0.0,
        "margin_to_lower_band": 10.0,
    }
    return contradicted


def test_validate_artifact_rejects_a_letter_that_contradicts_its_own_score() -> None:
    """The schema can say the grade is one of A-F, not that it is the right one.

    docs/rubric.md and the published scoring.json both say 80 is a B, so an
    artifact that prints 80.0 and calls it a C is unpublishable, whatever
    produced it.
    """
    from jsonschema import ValidationError

    from scorecard_pipeline.publish import validate_artifact

    artifact = make_artifact(dt.date(2026, 6, 11))
    validate_artifact(artifact)  # the honest one is fine

    with pytest.raises(ValidationError, match=r"contradicts its own score 80.0"):
        validate_artifact(_contradicting(artifact))


def test_validate_artifact_rejects_margins_measured_from_a_different_number() -> None:
    """All nine also reported an F as 0.0 points from a D."""
    from jsonschema import ValidationError

    from scorecard_pipeline.publish import validate_artifact

    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["overall"] = {
        "score": 60.0,
        "grade": "D",
        "margin_to_next_band": 0.0,  # 60.0 is 10.0 points from a C, not 0.0
        "margin_to_lower_band": 0.0,
    }
    with pytest.raises(ValidationError, match="margin_to_next_band"):
        validate_artifact(artifact)


def test_reindex_rederives_the_published_letter_without_rewriting_dated_history() -> None:
    """A current surface rebuilt from a pre-fix snapshot shows the right letter.

    docs/api.md: dated artifacts are immutable once written, while latest.json
    is rewritten when a scoring run completes. So the fix cannot reach the nine
    published letters by editing the evidence -- the letter has to be re-derived
    on the way out, the same way the conformance credential already is.
    """
    from scorecard_pipeline.publish import rebuild_index

    dated = publish(make_artifact(dt.date(2026, 6, 19), score=90.0))
    stale_text = json.dumps(_contradicting(json.loads(dated.read_text())), indent=2) + "\n"
    dated.write_text(stale_text)
    (dated.parent / "latest.json").write_text(stale_text)

    rebuild_index()

    assert dated.read_text() == stale_text, "immutable dated evidence was rewritten"

    latest = json.loads((dated.parent / "latest.json").read_text())
    assert latest["overall"]["score"] == 80.0, "the score itself must not move"
    assert latest["overall"]["grade"] == "B"
    assert latest["overall"]["margin_to_next_band"] == 10.0
    assert latest["overall"]["margin_to_lower_band"] == 0.0

    badge = json.loads((dated.parent / "badge.json").read_text())
    assert badge["message"] == "B 80.0"
    assert badge["color"] == "green"
    assert "B 80" in (dated.parent / "badge.svg").read_text()

    # index.json is what the app draws trends from. A point carrying the old
    # letter would make the corrected one look like the agency's grade changing.
    index = json.loads((artifacts_dir() / "index.json").read_text())
    point = index["agencies"]["unitrans"]["history"][-1]
    assert (point["score"], point["grade"]) == (80.0, "B")


def test_history_entry_letter_comes_from_its_own_score() -> None:
    artifact = make_artifact(dt.date(2026, 6, 19))
    point = _history_entry(_contradicting(artifact))
    assert (point["score"], point["grade"]) == (80.0, "B")


# --- the consequence block on every finding (issue #367) ---------------------


def _artifact_with_findings(
    agency: Agency = AGENCY, *, ntd_id: str | None = "90142"
) -> dict[str, Any]:
    from scorecard_pipeline.metrics import Finding

    def make(code: str, count: int, deduction: float) -> Finding:
        return Finding(
            code=code,
            severity="WARNING",
            count=count,
            what="w",
            why="y",
            fix="f",
            effort="e",
            deduction=deduction,
        )

    card = build_scorecard(
        [
            CategoryResult(
                name="completeness",
                score=70.0,
                summary="s",
                findings=[
                    make("scorecard_wheelchair_boarding_unknown", 120, 10.0),
                    make("scorecard_orphan_stops", 4, 2.0),
                    make("scorecard_no_fare_data", 1, 5.0),
                ],
            )
        ]
    )
    artifact = build_artifact(agency, make_fetch(dt.date(2026, 6, 11)), card, GENERATED_AT)
    artifact["geo"] = {"stop_count": 296}
    artifact["routability"] = {"boardable_stops": 274, "trips_total": 1794}
    if ntd_id is not None:
        artifact["ntd_id_alignment"] = {"ntd_id": ntd_id}
    return artifact


def _every_block(published: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = [
        f["consequence"]
        for cat in published["categories"].values()
        for f in cat.get("findings", [])
    ]
    blocks.extend(f["consequence"] for f in published["top_fixes"])
    return blocks


def test_publish_attaches_a_consequence_block_to_every_finding() -> None:
    dated = publish(_artifact_with_findings())
    published = json.loads(dated.read_text())
    blocks = _every_block(published)
    assert len(blocks) == 3 + len(published["top_fixes"])
    assert published["top_fixes"], "the fixture must produce top fixes to check"
    by_code = {b["code"]: b for b in blocks}
    assert by_code["scorecard_wheelchair_boarding_unknown"]["reach"]["total"] == 296
    assert by_code["scorecard_orphan_stops"]["reach"]["total_source"] == (
        "routability.boardable_stops"
    )
    assert by_code["scorecard_no_fare_data"]["reach"]["reason"] == "feed_level"
    # latest.json is the same record as the dated evidence.
    latest = json.loads((dated.parent / "latest.json").read_text())
    assert _every_block(latest) == blocks


def test_published_absences_are_never_written_as_values() -> None:
    """A US record's writer joins neither input, and says so rather than zero."""
    published = json.loads(publish(_artifact_with_findings()).read_text())
    for block in _every_block(published):
        assert block["ridership"]["annual_rider_trips"] is None
        assert block["ridership"]["reason"] == "not_joined_here"
        assert block["served_area_need"]["tier"] is None
        assert block["served_area_need"]["reason"] == "not_joined_here"
        assert "annual rider-trips" not in block["line"]
        assert not any("was supplied" in note for note in block["absences"])


def test_a_canadian_record_publishes_the_ntd_scope_absence() -> None:
    canadian = Agency(
        id="grt",
        name="Grand River Transit",
        static_gtfs_url="https://example.org/grt.zip",
        country="CA",
    )
    published = json.loads(publish(_artifact_with_findings(canadian, ntd_id=None)).read_text())
    for block in _every_block(published):
        assert block["ridership"] == {
            "annual_rider_trips": None,
            "ntd_id": None,
            "reason": "outside_ridership_scope",
        }
        assert block["served_area_need"]["scale"] == "ca_cimd"
        assert any("United States National Transit Database" in n for n in block["absences"])


def test_two_records_sharing_an_ntd_reporter_both_publish_an_absence() -> None:
    from scorecard_pipeline.config import AGENCIES

    first = Agency(id="a1", name="A one", static_gtfs_url="https://e.org/1.zip", ntd_id="90142")
    second = Agency(id="a2", name="A two", static_gtfs_url="https://e.org/2.zip", ntd_id="0090142")
    alone = Agency(id="a3", name="A three", static_gtfs_url="https://e.org/3.zip", ntd_id="90001")
    for agency in (first, second, alone):
        AGENCIES[agency.id] = agency

    for agency in (first, second):
        published = json.loads(publish(_artifact_with_findings(agency)).read_text())
        for block in _every_block(published):
            assert block["ridership"]["annual_rider_trips"] is None
            assert block["ridership"]["reason"] == "duplicate_ntd_reporter"

    published = json.loads(publish(_artifact_with_findings(alone, ntd_id="90001")).read_text())
    assert {b["ridership"]["reason"] for b in _every_block(published)} == {"not_joined_here"}


def test_a_retired_alias_does_not_quarantine_its_successors_reporter() -> None:
    from scorecard_pipeline.config import AGENCIES

    live = Agency(id="live", name="Live", static_gtfs_url="https://e.org/l.zip", ntd_id="90142")
    retired = Agency(
        id="old",
        name="Old",
        static_gtfs_url="https://e.org/o.zip",
        ntd_id="90142",
        alias_of="live",
    )
    AGENCIES.update({"live": live, "old": retired})
    published = json.loads(publish(_artifact_with_findings(live)).read_text())
    assert {b["ridership"]["reason"] for b in _every_block(published)} == {"not_joined_here"}


def test_publish_rebuilds_the_block_a_sweep_carried_forward() -> None:
    artifact = _artifact_with_findings()
    first = json.loads(publish(artifact).read_text())
    carried = json.loads(json.dumps(first))
    # The sweep copies category findings forward and rebuilds top_fixes from
    # their fields, so the block arrives stale on one list and absent on the other.
    for cat in carried["categories"].values():
        for f in cat.get("findings", []):
            f["consequence"]["reach"]["affected"] = 999_999
    for fix in carried["top_fixes"]:
        del fix["consequence"]
    again = json.loads(publish(carried).read_text())
    assert _every_block(again) == _every_block(first)


def test_the_schema_refuses_an_absence_written_as_a_value() -> None:
    """Negative controls: each sabotage must land, and each must be refused.

    The schema's only job here is the portfolio's most common defect: a missing
    number published as zero. A sabotage that silently failed to apply would
    read as a pass, so every mutation is asserted before it is validated.
    """
    import copy

    import jsonschema

    from scorecard_pipeline.publish import validate_artifact

    published = json.loads(publish(_artifact_with_findings()).read_text())
    validate_artifact(published)  # the untouched record is valid

    def sabotaged(path: tuple[str, str], value: object) -> dict[str, Any]:
        bad: dict[str, Any] = copy.deepcopy(published)
        block = bad["top_fixes"][0]["consequence"]
        block[path[0]][path[1]] = value
        assert bad["top_fixes"][0]["consequence"][path[0]][path[1]] == value
        assert bad != published
        return bad

    for path, value in (
        (("ridership", "annual_rider_trips"), 0),
        (("served_area_need", "tier"), "lower"),
        (("reach", "reason"), "feed_level"),
        (("ridership", "reason"), ""),
        # An absent identifier written as an empty string reads as a value too.
        (("ridership", "ntd_id"), ""),
        (("served_area_need", "scale"), ""),
    ):
        bad = sabotaged(path, value)
        with pytest.raises(jsonschema.ValidationError):
            validate_artifact(bad)


def test_the_schema_refuses_a_share_for_a_finding_with_no_basis() -> None:
    """A feed-level finding has no share, even one that looks plausible."""
    import copy

    import jsonschema

    from scorecard_pipeline.publish import validate_artifact

    published = json.loads(publish(_artifact_with_findings()).read_text())
    findings = published["categories"]["completeness"]["findings"]
    index = next(i for i, f in enumerate(findings) if f["consequence"]["reach"]["basis"] == "none")
    bad = copy.deepcopy(published)
    reach = bad["categories"]["completeness"]["findings"][index]["consequence"]["reach"]
    reach.update({"share": 1.0, "affected": 1, "total": 1, "reason": ""})
    assert (
        bad["categories"]["completeness"]["findings"][index]["consequence"]["reach"]["share"] == 1.0
    )
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact(bad)


def test_the_schema_still_accepts_a_joined_value() -> None:
    """The controls above are not vacuous: a real value with no reason passes."""
    import copy

    from scorecard_pipeline.publish import validate_artifact

    published = json.loads(publish(_artifact_with_findings()).read_text())
    good = copy.deepcopy(published)
    block = good["top_fixes"][0]["consequence"]
    block["ridership"] = {"annual_rider_trips": 0, "ntd_id": "90142", "reason": ""}
    block["served_area_need"] = {"tier": "high", "scale": "us_acs", "reason": ""}
    validate_artifact(good)
