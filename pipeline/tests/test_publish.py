"""Tests for artifact publishing: schema shape, idempotency, index history."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

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
    assert any("agency's own URL" in n for n in conf["notes"])


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
