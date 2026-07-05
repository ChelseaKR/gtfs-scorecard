"""Tests for artifact publishing: schema shape, idempotency, index history."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scorecard_pipeline import SCHEMA_VERSION
from scorecard_pipeline.config import Agency, artifacts_dir
from scorecard_pipeline.fetch import USER_AGENT, FetchResult
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import build_artifact, publish
from scorecard_pipeline.score import build_scorecard

AGENCY = Agency(
    id="unitrans",
    name="Unitrans",
    static_gtfs_url="https://example.org/gtfs.zip",
    license_note="test",
)
GENERATED_AT = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)


def make_fetch(date: dt.date, source: str = "unknown") -> FetchResult:
    return FetchResult(
        agency_id=AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=AGENCY.static_gtfs_url,
        fetched_date=date,
        sha256="abc123",
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
    assert artifact["agency"] == {"id": "unitrans", "name": "Unitrans"}
    assert artifact["snapshot_date"] == "2026-06-11"
    assert artifact["feed"]["sha256"] == "abc123"
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
    }


def test_fetch_provenance_block_carries_mirror_details() -> None:
    fetch = FetchResult(
        agency_id=AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=AGENCY.static_gtfs_url,
        fetched_date=dt.date(2026, 6, 11),
        sha256="abc123",
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
        "max_attempts": 1,
        "origin_error": "ConnectTimeout",
    }
    # feed.static_url still records the configured origin URL, unchanged.
    assert artifact["feed"]["static_url"] == AGENCY.static_gtfs_url


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
    # History carries per-category scores for trend rendering.
    assert "correctness" in entry["categories"]


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
        sha256="abc123",
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
        sha256="abc123",
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
        sha256="abc123",
        size_bytes=1024,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=80.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, GENERATED_AT)
    assert artifact["agency"]["country"] == "CA"
    # Omitted for US agencies so their artifacts stay byte-identical.
    assert "country" not in make_artifact(dt.date(2026, 6, 11))["agency"]


def test_operating_note_absent_keeps_agency_block_minimal() -> None:
    # The default AGENCY has no operating_note; the agency block stays two keys.
    artifact = make_artifact(dt.date(2026, 6, 11))
    assert "operating_note" not in artifact["agency"]
    publish(artifact)
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert "operating_note" not in index["agencies"]["unitrans"]


def test_reindex_skips_corrupt_dated_artifact_and_keeps_the_rest() -> None:
    # At national scale one corrupt dated file (e.g. a truncated or doubled
    # write surfacing as JSONDecodeError "Extra data") must not abort the whole
    # daily reindex. The good days for the same agency still index, and the
    # newest good day drives latest.json.
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
    assert dates == ["2026-06-17"]
    latest = json.loads((artifacts_dir() / "unitrans" / "latest.json").read_text())
    assert latest["snapshot_date"] == "2026-06-17"


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
