"""Tests for rebuilding index.json from artifacts on disk (sharded runs)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from scorecard_pipeline.artifact_lifecycle import (
    MUTABLE_PUBLIC_ARTIFACT_NAMES,
    retirement_manifest_path,
)
from scorecard_pipeline.config import Agency, artifacts_dir, register
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import build_artifact, publish, rebuild_index
from scorecard_pipeline.score import build_scorecard

GENERATED_AT = dt.datetime(2026, 6, 12, 12, 0, tzinfo=dt.UTC)


def _publish(agency_id: str, date: dt.date, score: float) -> None:
    agency = Agency(
        id=agency_id, name=f"{agency_id} Transit", static_gtfs_url="https://ex.org/g.zip"
    )
    fetch = FetchResult(
        agency_id=agency_id,
        path=Path("/tmp/g.zip"),
        url=agency.static_gtfs_url,
        fetched_date=date,
        sha256="a" * 64,
        size_bytes=1,
        reused=False,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=score, summary="s")])
    publish(build_artifact(agency, fetch, card, GENERATED_AT))


def test_reindex_assembles_history_from_disk() -> None:
    _publish("a", dt.date(2026, 6, 11), 80.0)
    _publish("a", dt.date(2026, 6, 12), 84.0)
    _publish("b", dt.date(2026, 6, 12), 70.0)

    # corrupt the incrementally-built index to prove reindex rebuilds from scratch
    (artifacts_dir() / "index.json").write_text('{"schema_version": "1.1", "agencies": {}}')

    rebuild_index()
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert set(index["agencies"]) == {"a", "b"}
    a_dates = [h["date"] for h in index["agencies"]["a"]["history"]]
    assert a_dates == ["2026-06-11", "2026-06-12"]


def test_reindex_ignores_rollups_dir() -> None:
    _publish("a", dt.date(2026, 6, 12), 80.0)
    (artifacts_dir() / "rollups").mkdir(parents=True, exist_ok=True)
    (artifacts_dir() / "rollups" / "all.json").write_text("{}")
    rebuild_index()
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert "rollups" not in index["agencies"]


def test_reindex_skips_directories_absent_from_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The S3 artifacts store is additive and outlives registry edits, so a
    # hydrated tree can hold directories no agencies.yaml version lists (the
    # 2026-07 directory-count jump). With a populated registry, reindex must
    # list only registered agencies.
    from scorecard_pipeline.config import AGENCIES

    _publish("a", dt.date(2026, 6, 12), 80.0)
    _publish("ghost", dt.date(2026, 6, 12), 70.0)

    monkeypatch.setitem(
        AGENCIES, "a", Agency(id="a", name="a Transit", static_gtfs_url="https://ex.org/g.zip")
    )
    rebuild_index()
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert set(index["agencies"]) == {"a"}
    ghost_dir = artifacts_dir() / "ghost"
    assert (ghost_dir / "2026-06-12.json").exists()
    assert not (ghost_dir / "latest.json").exists()
    manifest = json.loads(retirement_manifest_path(artifacts_dir()).read_text())
    assert manifest["agency_ids"] == ["ghost"]


def test_retired_f_alias_is_not_current_alongside_live_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retirement changes publication identity without erasing evidence."""
    from scorecard_pipeline.config import AGENCIES

    retired_id = "annapolis-transit"
    successor_id = "annapolis-transit-2285"

    # Reproduce the pre-fix state: both endpoints have public score histories,
    # and the stale predecessor's F appears beside its live successor's A.
    _publish(retired_id, dt.date(2026, 6, 12), 31.2)
    _publish(successor_id, dt.date(2026, 6, 12), 91.1)
    stale = json.loads((artifacts_dir() / "index.json").read_text())
    assert stale["agencies"][retired_id]["history"][-1]["grade"] == "F"
    assert stale["agencies"][successor_id]["history"][-1]["grade"] == "A"

    monkeypatch.setitem(
        AGENCIES,
        retired_id,
        Agency(
            id=retired_id,
            name="Annapolis Transit",
            static_gtfs_url="https://archive.example/annapolis.zip",
            alias_of=successor_id,
            feed_status="deprecated",
        ),
    )
    monkeypatch.setitem(
        AGENCIES,
        successor_id,
        Agency(
            id=successor_id,
            name="Annapolis Transit",
            static_gtfs_url="https://annapolis.example/gtfs.zip",
        ),
    )

    retired_dir = artifacts_dir() / retired_id
    for name in MUTABLE_PUBLIC_ARTIFACT_NAMES:
        (retired_dir / name).write_text(f"stale {name}")

    rebuild_index()

    current = json.loads((artifacts_dir() / "index.json").read_text())
    assert set(current["agencies"]) == {successor_id}
    # Dated evidence remains available, while every mutable current-looking
    # API/asset pointer is removed locally and named in the S3 cleanup plan.
    assert (retired_dir / "2026-06-12.json").exists()
    assert all(not (retired_dir / name).exists() for name in MUTABLE_PUBLIC_ARTIFACT_NAMES)
    manifest = json.loads(retirement_manifest_path(artifacts_dir()).read_text())
    assert manifest == {"agency_ids": [retired_id], "schema_version": 1}

    # A deliberate single-feed reproduction can add dated evidence, but cannot
    # resurrect any mutable pointer or its index membership.
    _publish(retired_id, dt.date(2026, 6, 13), 31.2)
    after_reproduction = json.loads((artifacts_dir() / "index.json").read_text())
    assert set(after_reproduction["agencies"]) == {successor_id}
    assert (retired_dir / "2026-06-13.json").exists()
    assert all(not (retired_dir / name).exists() for name in MUTABLE_PUBLIC_ARTIFACT_NAMES)


def test_reindex_indexes_everything_when_no_registry_is_loaded() -> None:
    # Library callers (and most unit tests) run with an empty registry; the
    # bound only applies once agencies.yaml has been loaded.
    _publish("a", dt.date(2026, 6, 12), 80.0)
    _publish("b", dt.date(2026, 6, 12), 70.0)

    rebuild_index()
    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert set(index["agencies"]) == {"a", "b"}


def test_publish_and_reindex_use_curated_name_but_keep_dated_artifact_immutable() -> None:
    register(
        Agency(
            id="a",
            name="Curated A Transit",
            static_gtfs_url="https://ex.org/g.zip",
        )
    )
    _publish("a", dt.date(2026, 6, 12), 80.0)

    index_path = artifacts_dir() / "index.json"
    assert json.loads(index_path.read_text())["agencies"]["a"]["name"] == "Curated A Transit"
    dated_path = artifacts_dir() / "a" / "2026-06-12.json"
    assert json.loads(dated_path.read_text())["agency"]["name"] == "a Transit"

    rebuild_index()
    assert json.loads(index_path.read_text())["agencies"]["a"]["name"] == "Curated A Transit"
    assert json.loads(dated_path.read_text())["agency"]["name"] == "a Transit"
