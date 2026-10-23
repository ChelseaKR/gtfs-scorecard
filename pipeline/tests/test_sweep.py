"""Tests for the freshness sweep (pure recompute, plus the command that applies it)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.sweep import can_resweep, needs_sweep, resweep


def _artifact(*, last_service: str | None, fresh_score: float, days: int | None) -> dict[str, Any]:
    """A minimal scored artifact with one finding per measured category, shaped
    like a real published latest.json."""
    return {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "snapshot_date": "2026-06-10",
        "overall": {"score": 80.0, "grade": "B"},
        "top_fixes": [],
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "summary": "",
                "weight": 0.35,
                "findings": [
                    {
                        "code": "missing_recommended_field",
                        "severity": "WARNING",
                        "count": 2,
                        "what": "x",
                        "why": "y",
                        "fix": "z",
                        "effort": "",
                        "points": 4.0,
                    }
                ],
                "details": {},
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": fresh_score,
                "summary": "",
                "weight": 0.20,
                "findings": [],
                "details": {
                    "has_feed_info": False,
                    "feed_version": None,
                    "service_type": "fixed",
                    "feed_start_date": None,
                    "feed_end_date": None,
                    "last_service_date": last_service,
                    "days_until_expiry": days,
                },
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 60.0,
                "summary": "",
                "weight": 0.25,
                "findings": [],
                "details": {},
            },
            "realtime": {
                "name": "realtime",
                "status": "not_yet_measured",
                "weight": 0.20,
                "summary": "This agency does not publish realtime.",
            },
        },
    }


def test_can_resweep_requires_dated_measured_freshness() -> None:
    assert can_resweep(_artifact(last_service="2026-09-01", fresh_score=85.0, days=83))
    # No expiry date stored: nothing to recompute against.
    assert not can_resweep(_artifact(last_service=None, fresh_score=0.0, days=None))


def test_needs_sweep_skips_feeds_already_scored_on_the_sweep_date() -> None:
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)  # snapshot 2026-06-10
    # Stale: last full score predates the sweep date, so refresh it.
    assert needs_sweep(art, dt.date(2026, 6, 20)) is True
    # Already current: scored on (or after) the sweep date, so skip — never
    # restamp a same-day full score as a freshness recompute.
    assert needs_sweep(art, dt.date(2026, 6, 10)) is False
    assert needs_sweep(art, dt.date(2026, 6, 5)) is False
    # No dates to recompute against: nothing to sweep.
    assert (
        needs_sweep(_artifact(last_service=None, fresh_score=0.0, days=None), dt.date(2026, 6, 20))
        is False
    )


def test_resweep_drops_grade_when_feed_has_since_expired() -> None:
    # Scored 2026-06-10 with service through 2026-09-01 (current); sweeping months
    # later, after service has ended, must recompute freshness to 0 and re-grade.
    art = _artifact(last_service="2026-02-01", fresh_score=85.0, days=83)
    new, summary = resweep(art, dt.date(2026, 6, 20))

    assert new["categories"]["freshness"]["score"] == 0.0
    assert new["categories"]["freshness"]["details"]["days_until_expiry"] == -139
    assert summary["grade_changed"] is True
    assert summary["new_grade"] != "B"
    # The expired feed becomes the leading fix, ahead of the correctness warning.
    assert new["top_fixes"][0]["code"] == "scorecard_feed_expired"


def test_resweep_overall_is_weighted_average_of_measured_categories() -> None:
    # correctness 90 (0.35), freshness 0 (0.20), completeness 60 (0.25); realtime
    # is not measured, so weights renormalize over 0.80.
    art = _artifact(last_service="2026-02-01", fresh_score=85.0, days=83)
    new, _ = resweep(art, dt.date(2026, 6, 20))
    expected = (90 * 0.35 + 0 * 0.20 + 60 * 0.25) / (0.35 + 0.20 + 0.25)
    assert new["overall"]["score"] == round(expected, 1)


def test_resweep_marks_partial_and_keeps_feed_fetched_date() -> None:
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)
    new, _ = resweep(art, dt.date(2026, 6, 20))
    assert new["snapshot_date"] == "2026-06-20"
    assert new["recompute"] == {
        "kind": "freshness",
        "as_of": "2026-06-20",
        "feed_fetched_date": "2026-06-10",
    }
    # Not-yet-measured realtime is preserved untouched, not regenerated.
    assert new["categories"]["realtime"]["status"] == "not_yet_measured"
    assert "does not publish realtime" in new["categories"]["realtime"]["summary"]


def test_resweep_keeps_current_feed_current() -> None:
    # Still 70+ days of service left as of the sweep date: the date component is
    # full (100), less the standing 15-point penalty for absent feed_info dates.
    art = _artifact(last_service="2026-09-01", fresh_score=85.0, days=83)
    new, summary = resweep(art, dt.date(2026, 6, 20))
    assert new["categories"]["freshness"]["score"] == 85.0
    assert summary["new_days"] == (dt.date(2026, 9, 1) - dt.date(2026, 6, 20)).days


def test_a_chain_of_sweeps_keeps_naming_the_day_the_feed_was_fetched() -> None:
    """The defect: each sweep took the previous sweep's stamp as a fetch date.

    Sweeps run every cycle, so the published claim became "fetched yesterday"
    for feeds nobody had downloaded in weeks. On 2026-09-13, 468 of the 472
    published recomputes claimed a fetch on 2026-09-12 while carrying the same
    feed_sha256 they had held since 2026-08-10.
    """
    art = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    art["snapshot_date"] = "2026-08-10"  # the day the feed was really downloaded

    first, _ = resweep(art, dt.date(2026, 9, 12))
    assert first["recompute"]["feed_fetched_date"] == "2026-08-10"

    # Sweeping the swept artifact, as the next cycle does.
    second, _ = resweep(first, dt.date(2026, 9, 13))
    assert second["snapshot_date"] == "2026-09-13"
    assert second["recompute"]["as_of"] == "2026-09-13"
    assert second["recompute"]["feed_fetched_date"] == "2026-08-10"

    # And a thirtieth sweep still says the same thing.
    latest = second
    for day in range(14, 30):
        latest, _ = resweep(latest, dt.date(2026, 9, day))
    assert latest["recompute"]["feed_fetched_date"] == "2026-08-10"


def test_a_full_score_after_a_sweep_resets_the_fetch_date() -> None:
    """The rule must not freeze the date: a real fetch is a real fetch.

    A full re-score writes an artifact with no recompute block, so the next
    sweep reads its snapshot_date, which is the day it was downloaded.
    """
    from scorecard_pipeline.sweep import last_fetched_date

    swept = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    swept["snapshot_date"] = "2026-08-10"
    swept, _ = resweep(swept, dt.date(2026, 9, 12))
    assert last_fetched_date(swept) == "2026-08-10"

    rescored = _artifact(last_service="2027-09-02", fresh_score=85.0, days=365)
    rescored["snapshot_date"] = "2026-09-13"
    assert last_fetched_date(rescored) == "2026-09-13"
    swept_again, _ = resweep(rescored, dt.date(2026, 9, 14))
    assert swept_again["recompute"]["feed_fetched_date"] == "2026-09-13"


def _sacrt_like_artifact() -> dict[str, Any]:
    """A US full score shaped like SacRT's: service through 2026-08-15, scored
    2026-07-25 with 21 days left, carrying the two verdicts that quote it."""
    from scorecard_pipeline.conformance import assess as assess_conformance
    from scorecard_pipeline.ntd import assess as assess_ntd

    art = _artifact(last_service="2026-08-15", fresh_score=75.0, days=21)
    art["agency"] = {
        "id": "sacramento-regional-transit-sacrt",
        "name": "Sacramento Regional Transit (SacRT)",
        "country": "US",
    }
    art["snapshot_date"] = "2026-07-25"
    art["feed"] = {"static_url": "https://iportal.sacrt.com/GTFS/SRTD/google_transit.zip"}
    details = art["categories"]["freshness"]["details"]
    details.update(
        {
            "has_feed_info": True,
            "feed_version": "June_2026",
            "feed_start_date": "2026-06-14",
            "feed_end_date": "2026-08-15",
            "effective_expiry_date": "2026-08-15",
        }
    )
    art["conformance"] = assess_conformance(art).to_dict()
    art["ntd_readiness"] = assess_ntd(art).to_dict()
    assert "21 days" in art["conformance"]["summary"]
    assert "21 days" in art["ntd_readiness"]["summary"]
    return art


def test_a_sweep_rebuilds_every_verdict_that_quotes_the_expiry_count() -> None:
    """The defect: the sweep rebuilt the top fix but copied conformance and NTD
    readiness forward. SacRT's 2026-08-07 record led with "runs out in 8
    day(s)" while both blocks still said 21 days."""
    new, summary = resweep(_sacrt_like_artifact(), dt.date(2026, 8, 7))

    assert summary["new_days"] == 8
    assert new["top_fixes"][0]["code"] == "scorecard_feed_expiring_soon"
    assert "8 day" in new["top_fixes"][0]["what"]
    current = next(c for c in new["conformance"]["criteria"] if c["key"] == "current")
    assert current["detail"] == "Service data runs out in 8 days; renew to qualify."
    pillar = next(p for p in new["ntd_readiness"]["pillars"] if p["key"] == "current")
    assert pillar["detail"] == "Service data runs out in 8 days; renew before you certify."
    for block in (new["conformance"], new["ntd_readiness"]):
        assert "21 days" not in json.dumps(block)


def test_a_sweep_does_not_invent_ntd_readiness_for_a_feed_without_it() -> None:
    # NTD readiness is US-only (ADR 0026); a record scored without it stays without it.
    art = _sacrt_like_artifact()
    del art["ntd_readiness"]
    new, _ = resweep(art, dt.date(2026, 8, 7))
    assert "ntd_readiness" not in new
    assert "8 days" in new["conformance"]["summary"]


def _artifact_over_an_empty_archive() -> dict[str, Any]:
    """A published scorecard shaped like `boxcar`'s on 2026-09-13.

    Its rider-experience category is `measured` over an archive holding 0 stops
    and 0 trips, because it was scored before `score_feed_content` learned to
    refuse such an archive (#331). Freshness carries real dates, so the sweep
    can recompute it and would otherwise re-stamp the whole record.
    """
    art = _artifact(last_service="2027-09-02", fresh_score=100.0, days=365)
    art["agency"] = {"id": "boxcar", "name": "Boxcar Commuter Bus"}
    art["overall"] = {"score": 83.9, "grade": "B"}
    art["categories"]["freshness"]["details"]["feed_end_date"] = "2027-09-02"
    art["categories"]["completeness"]["details"] = {
        "stops": 0,
        "trips": 0,
        "components": {"contact": 15.0, "fares": 0.0},
        "unmeasured_components": ["headsigns", "stop_names"],
    }
    return art


def test_a_grade_over_an_empty_archive_is_not_swept_to_a_new_date() -> None:
    # The defect: the sweep carries correctness, rider experience and realtime
    # forward untouched, so a letter the scorer now refuses to produce was
    # re-published with today's date every cycle. boxcar published B 83.9 this
    # way on 2026-09-13, over an archive its own artifact records as 0 stops
    # and 0 trips.
    art = _artifact_over_an_empty_archive()
    assert can_resweep(art), "freshness is recomputable, so only the new rule can hold it back"
    assert needs_sweep(art, dt.date(2026, 9, 13)) is False


def test_a_real_measurement_is_still_swept() -> None:
    # The rule is narrow: an archive that was actually read still sweeps.
    art = _artifact_over_an_empty_archive()
    art["categories"]["completeness"]["details"] = {"stops": 296, "trips": 1794}
    assert needs_sweep(art, dt.date(2026, 9, 13)) is True


def test_the_sweep_command_names_what_it_held_back_and_leaves_it_undated(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole command, not the predicate: the held-back record keeps its own
    date, a real one beside it is still swept, and the holding back is said out
    loud. A skip nobody is told about is how this ran for days."""
    import argparse

    from scorecard_pipeline import cli, config

    root = tmp_path / "data" / "artifacts"
    empty_dir = root / "boxcar"
    real_dir = root / "unitrans"
    for directory in (empty_dir, real_dir):
        directory.mkdir(parents=True)
    empty = _artifact_over_an_empty_archive()
    real = _artifact_over_an_empty_archive()
    real["agency"] = {"id": "unitrans", "name": "Unitrans"}
    real["categories"]["completeness"]["details"] = {"stops": 296, "trips": 1794}
    (empty_dir / "latest.json").write_text(json.dumps(empty))
    (real_dir / "latest.json").write_text(json.dumps(real))
    monkeypatch.setattr(config, "artifacts_dir", lambda: root)

    changed = tmp_path / "changed.txt"
    args = argparse.Namespace(
        date=dt.date(2026, 9, 13), apply=False, changed_out=str(changed), budget_seconds=None
    )
    with caplog.at_level(logging.WARNING):
        assert cli._cmd_freshness_sweep(args, argparse.ArgumentParser()) == 0

    # The record over an empty archive is not among those the sweep would refresh;
    # the feed that was actually read still is.
    assert changed.read_text().split() == ["unitrans"]
    # And the reader of the log is told which record was held back, and why.
    assert "no stops and no trips" in caplog.text
    assert "boxcar" in caplog.text
    assert "corrections.yaml" in caplog.text


# ------------------------------------------------------------- the time budget
#
# The sweep step had no bound of its own. From 2026-10-14 the first sweep of
# each UTC day ran 134 to 167 minutes and was cancelled at the job's 175-minute
# bound (runs 39703075009, 39557688508, 39524867695 among others), publishing
# nothing, so the next cycle did it all again. The sweep now stops taking on
# agencies once its budget is spent, publishes what it swept, names the rest
# and exits 0. A deferred agency's record is not touched.

SWEEP_DAY = dt.date(2026, 6, 20)


def _published_artifact(agency_id: str, *, last_service: dt.date | None) -> dict[str, Any]:
    """A full, schema-valid artifact as the daily run publishes one, scored on
    2026-06-10 so it is due for a sweep on ``SWEEP_DAY``. With no service end
    date its freshness has nothing to recompute against and its countdown is
    absent (null), which is how the record must stay."""
    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.fetch import FetchResult
    from scorecard_pipeline.gtfs import FeedDates
    from scorecard_pipeline.metrics import CategoryResult, freshness
    from scorecard_pipeline.publish import build_artifact
    from scorecard_pipeline.score import build_scorecard

    scored_on = dt.date(2026, 6, 10)
    agency = Agency(
        id=agency_id,
        name=agency_id.title(),
        static_gtfs_url=f"https://example.org/{agency_id}.zip",
        license_note="test",
    )
    fetch = FetchResult(
        agency_id=agency_id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=scored_on,
        sha256="a" * 64,
        size_bytes=1024,
        reused=False,
        source="unknown",
    )
    categories = [CategoryResult(name="correctness", score=88.0, summary="s")]
    dates = FeedDates(
        has_feed_info=False,
        feed_publisher_name=None,
        feed_version=None,
        feed_start_date=None,
        feed_end_date=None,
        last_service_date=last_service,
    )
    fresh = freshness(dates, scored_on, "fixed")
    if fresh is not None:
        categories.append(fresh)
    card = build_scorecard(categories)
    return build_artifact(agency, fetch, card, dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC))


def _sweep_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Three stale feeds in sweep order, plus one with no expiry date at all."""
    from scorecard_pipeline import config

    root = tmp_path / "repo"
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    artifacts = root / "data" / "artifacts"
    for agency_id in ("alpha", "beta", "gamma"):
        (artifacts / agency_id).mkdir(parents=True)
        artifact = _published_artifact(agency_id, last_service=dt.date(2026, 7, 1))
        (artifacts / agency_id / "latest.json").write_text(json.dumps(artifact, indent=2))
    (artifacts / "nodate").mkdir(parents=True)
    nodate = _published_artifact("nodate", last_service=None)
    (artifacts / "nodate" / "latest.json").write_text(json.dumps(nodate, indent=2))
    assert config.artifacts_dir() == artifacts
    return artifacts


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _days(directory: Path) -> int | None:
    latest = json.loads((directory / "latest.json").read_text())
    days = latest["categories"]["freshness"].get("details", {}).get("days_until_expiry")
    assert days is None or isinstance(days, int)
    return days


def _ticking_clock(monkeypatch: pytest.MonkeyPatch, step: float) -> list[float]:
    """Replace the sweep's clock with one that advances ``step`` seconds per
    read, and return the reads so a test can see the clock was consulted.

    The sweep reads ``time.monotonic`` through the module, so the module
    attribute is what is replaced; monkeypatch puts it back."""
    import time

    reads: list[float] = []

    def monotonic() -> float:
        reads.append(len(reads) * step)
        return reads[-1]

    monkeypatch.setattr(time, "monotonic", monotonic)
    return reads


def _run_sweep(tmp_path: Path, budget_seconds: int | None, *, changed: Path | None = None) -> int:
    import argparse

    from scorecard_pipeline import cli

    args = argparse.Namespace(
        date=SWEEP_DAY,
        apply=True,
        changed_out=str(changed) if changed else None,
        budget_seconds=budget_seconds,
    )
    return cli._cmd_freshness_sweep(args, argparse.ArgumentParser())


def test_the_sweep_stops_at_its_budget_and_leaves_deferred_records_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The clock reads 0 when the budget is set, 100 before alpha, 200 before
    beta and 300 before gamma; with a 150 s budget alpha is swept and the other
    two are deferred. Their directories are the same bytes afterward, their
    countdowns are what they were (21 days, not 0 and not null), the feed with
    no expiry date still has none, and the reader is told exactly which were
    deferred, in the log and in a workflow annotation. Exit 0: a short cycle
    publishes what it did rather than nothing."""
    artifacts = _sweep_fixture(tmp_path, monkeypatch)
    before = {name: _snapshot(artifacts / name) for name in ("beta", "gamma", "nodate")}
    assert _days(artifacts / "beta") == 21
    assert _days(artifacts / "nodate") is None
    reads = _ticking_clock(monkeypatch, step=100.0)
    changed = tmp_path / "swept.txt"

    with caplog.at_level(logging.INFO):
        assert _run_sweep(tmp_path, 150, changed=changed) == 0

    assert len(reads) == 4, "the deadline is read once at the start and once per candidate"
    assert changed.read_text().split() == ["alpha"]
    swept = json.loads((artifacts / "alpha" / "latest.json").read_text())
    assert swept["snapshot_date"] == SWEEP_DAY.isoformat()
    assert swept["recompute"]["as_of"] == SWEEP_DAY.isoformat()
    assert (artifacts / "alpha" / f"{SWEEP_DAY.isoformat()}.json").exists()

    # Deferred and skipped records: nothing written, nothing rewritten.
    for name in ("beta", "gamma", "nodate"):
        assert _snapshot(artifacts / name) == before[name], name
    assert _days(artifacts / "beta") == 21
    assert _days(artifacts / "gamma") == 21
    assert _days(artifacts / "nodate") is None
    assert json.loads((artifacts / "beta" / "latest.json").read_text())["snapshot_date"] == (
        "2026-06-10"
    )
    # The index carries the one swept feed and nothing for the deferred two.
    index = json.loads((artifacts / "index.json").read_text())
    assert list(index["agencies"]) == ["alpha"]

    assert (
        "Freshness sweep stopped at its 150s budget: 1 agencies reswept, 2 deferred." in caplog.text
    )
    assert "Deferred: beta, gamma" in caplog.text
    assert "nodate" not in caplog.text.split("Deferred:")[1]
    assert "1 agencies reswept, 0 held back, 2 deferred" in caplog.text
    annotation = capsys.readouterr().err
    assert (
        "::warning title=freshness sweep deferred::2 agencies not re-dated within 150s"
        in annotation
    )


def test_control_without_a_budget_every_stale_feed_is_swept_and_rewritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same fixture and the same running clock with no budget: all three
    are swept, the two the budget held back are rewritten to the sweep date,
    the clock is never consulted, and no deferral is reported. This is what
    the test above would see if the budget check did nothing."""
    artifacts = _sweep_fixture(tmp_path, monkeypatch)
    before = {name: _snapshot(artifacts / name) for name in ("beta", "gamma")}
    reads = _ticking_clock(monkeypatch, step=100.0)
    changed = tmp_path / "swept.txt"

    with caplog.at_level(logging.INFO):
        assert _run_sweep(tmp_path, None, changed=changed) == 0

    assert reads == []
    assert changed.read_text().split() == ["alpha", "beta", "gamma"]
    for name in ("beta", "gamma"):
        assert _snapshot(artifacts / name) != before[name], name
        latest = json.loads((artifacts / name / "latest.json").read_text())
        assert latest["snapshot_date"] == SWEEP_DAY.isoformat()
        assert _days(artifacts / name) == 11
    assert _days(artifacts / "nodate") is None
    assert sorted(json.loads((artifacts / "index.json").read_text())["agencies"]) == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert "deferred." not in caplog.text
    assert "3 agencies reswept, 0 held back, 0 deferred" in caplog.text
    assert "::warning" not in capsys.readouterr().err


def test_control_a_budget_the_clock_never_reaches_defers_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A budget is not a quota: with the clock standing still the same 150 s
    budget sweeps all three. It is the deadline passing that defers."""
    artifacts = _sweep_fixture(tmp_path, monkeypatch)
    reads = _ticking_clock(monkeypatch, step=0.0)

    with caplog.at_level(logging.INFO):
        assert _run_sweep(tmp_path, 150) == 0

    assert len(reads) == 4
    assert "3 agencies reswept, 0 held back, 0 deferred" in caplog.text
    assert sorted(json.loads((artifacts / "index.json").read_text())["agencies"]) == [
        "alpha",
        "beta",
        "gamma",
    ]
