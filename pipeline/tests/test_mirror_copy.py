"""A grade scored from a Mobility Database mirror copy says so, with its dates.

When the configured feed URL fails, the daily run scores the catalog's hosted
copy instead, which can be years old. On 2026-11-05 that put an F and "re-export
your calendar" on SacRT, whose current feed runs into 2027, because the 2024
copy's service had ended. These tests pin the repair: an expired mirror copy's
freshness is held out of the grade (unknown, not zero), the failed download
leads the fixes, and every page and paid report that shows the grade names the
copy and its service dates.
"""

from __future__ import annotations

import datetime as dt
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from scorecard_pipeline.bundle import SOURCE_MIRROR, STATUS_INCLUDED, build_bundle, parse_request
from scorecard_pipeline.config import Agency
from scorecard_pipeline.feed_provenance import mirror_copy_caveat
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult, Finding
from scorecard_pipeline.publish import (
    CONFIDENCE_LEVELS,
    build_artifact,
    confidence_after_hold,
    publish,
    validate_artifact,
)
from scorecard_pipeline.report import build_report_data, render_report
from scorecard_pipeline.score import (
    FEED_DOWNLOAD_FAILED,
    build_scorecard,
    build_scorecard_for_fetch,
    score_feed_content,
)
from scorecard_pipeline.sweep import can_resweep, needs_sweep, resweep

TODAY = dt.date(2026, 11, 5)
URL = "https://iportal.example.org/GTFS/SRTD/google_transit.zip"
CALENDAR_HEADER = (
    "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
)


def _feed(make_gtfs_zip: Callable[..., Path], start: str, end: str) -> Path:
    return make_gtfs_zip(
        {
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\n"
            "S1,Main St,38.5,-121.5,1\n",
            "trips.txt": "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\n"
            "R1,WK,T1,Downtown,1\n",
            "routes.txt": "route_id,route_short_name,route_type\nR1,1,3\n",
            "calendar.txt": CALENDAR_HEADER + f"WK,1,1,1,1,1,0,0,{start},{end}\n",
            "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang,"
            "feed_start_date,feed_end_date\n"
            f"Sample,https://example.org,en,{start},{end}\n",
        }
    )


def _correctness() -> Any:

    return CategoryResult(name="correctness", score=90.0, summary="ok")


def _categories(path: Path) -> list[Any]:
    return [_correctness(), *score_feed_content(str(path), today=TODAY)]


def test_an_expired_mirror_copy_is_not_graded_as_the_agencys_lapse(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    cats = _categories(_feed(make_gtfs_zip, "20240818", "20250104"))
    origin = build_scorecard(cats)
    card = build_scorecard_for_fetch(
        cats, fetch_source="mirror", configured_url=URL, origin_error="SSLError"
    ).to_json()

    # Before: the copy's lapse costs the full freshness weight and leads the fixes.
    assert origin.to_json()["categories"]["freshness"]["score"] == 0.0
    assert origin.top_fixes[0].code == "scorecard_feed_expired"

    fresh = card["categories"]["freshness"]
    assert fresh["status"] == "not_yet_measured"
    assert "score" not in fresh
    # No expiry countdown, so the lapse is not counted as the agency's again.
    assert "details" not in fresh
    assert fresh["mirror_copy"] == {"service_start": "2024-08-18", "service_end": "2025-01-04"}
    assert card["overall"]["score"] > origin.to_json()["overall"]["score"]

    lead = card["top_fixes"][0]
    assert lead["code"] == FEED_DOWNLOAD_FAILED
    assert lead["rank"] == 1
    assert URL in lead["what"]
    assert "certificate" in lead["fix"]
    assert "2025-01-04" in lead["why"]
    assert len(card["top_fixes"]) <= 3
    assert not any("export" in f["fix"].lower() for f in card["top_fixes"])


def test_a_current_mirror_copy_and_any_origin_fetch_are_graded_as_before(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    current = _categories(_feed(make_gtfs_zip, "20260801", "20270102"))
    for source in ("mirror", "origin"):
        assert (
            build_scorecard_for_fetch(
                current, fetch_source=source, configured_url=URL, origin_error=None
            ).to_json()
            == build_scorecard(current).to_json()
        )

    expired = _categories(_feed(make_gtfs_zip, "20240818", "20250104"))
    assert (
        build_scorecard_for_fetch(
            expired, fetch_source="origin", configured_url=URL, origin_error=None
        ).to_json()
        == build_scorecard(expired).to_json()
    )


def _mirror_artifact(**freshness: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.5",
        "rubric_version": "1.4",
        "validator_version": "8.0.1",
        "snapshot_date": "2026-11-05",
        "agency": {"id": "sampletown", "name": "Sampletown Transit"},
        "feed": {"static_url": URL, "reachable": False},
        "fetch": {"source": "mirror", "origin_error": "SSLError"},
        "overall": {"grade": "C", "score": 74.0},
        "categories": {"freshness": {"name": "freshness", **freshness}},
        "top_fixes": [],
    }


def test_the_caveat_names_the_copy_and_its_dates() -> None:
    held = _mirror_artifact(
        status="not_yet_measured",
        mirror_copy={"service_start": "2024-08-18", "service_end": "2025-01-04"},
    )
    assert "2024-08-18 to 2025-01-04" in mirror_copy_caveat(held)
    assert "Mobility Database mirror copy" in mirror_copy_caveat(held)

    # An already-published artifact, graded before the hold, still gets dates.
    graded = _mirror_artifact(
        status="measured",
        details={"feed_start_date": None, "effective_expiry_date": "2026-08-29"},
    )
    assert "Service dates in that copy end 2026-08-29" in mirror_copy_caveat(graded)

    unknown = _mirror_artifact(status="not_yet_measured")
    assert "could not be read" in mirror_copy_caveat(unknown)

    origin = _mirror_artifact(status="measured")
    origin["fetch"] = {"source": "origin"}
    assert mirror_copy_caveat(origin) == ""


def test_the_paid_board_report_carries_the_caveat() -> None:
    artifact = _mirror_artifact(
        status="not_yet_measured",
        mirror_copy={"service_start": "2024-08-18", "service_end": "2025-01-04"},
    )
    now = dt.datetime(2026, 11, 5, 12, tzinfo=dt.UTC)
    html = render_report(build_report_data(artifact, [], generated_at=now))
    assert "mirror copy" in html
    assert "2024-08-18 to 2025-01-04" in html

    artifact["fetch"] = {"source": "origin"}
    assert "mirror" not in render_report(build_report_data(artifact, [], generated_at=now))


def test_the_bundle_manifest_flags_a_mirror_scored_report(
    isolated_repo_root: Path, tmp_path: Path
) -> None:
    art = isolated_repo_root / "data" / "artifacts"
    (art / "sampletown").mkdir(parents=True)
    artifact = _mirror_artifact(
        status="not_yet_measured",
        mirror_copy={"service_start": "2024-08-18", "service_end": "2025-01-04"},
    )
    (art / "sampletown" / "latest.json").write_text(json.dumps(artifact))
    (art / "index.json").write_text(json.dumps({"schema_version": "1", "agencies": {}}))
    request = parse_request(
        {
            "bundle_id": "0123456789abcdef0123456789abcdef",
            "program_name": "Sample Program",
            "agency_ids": "sampletown",
            "deliver_to": "program@example.org",
        }
    )
    out = tmp_path / "b.zip"
    manifest = build_bundle(request, out, now=dt.datetime(2026, 11, 5, tzinfo=dt.UTC))
    (row,) = manifest["agencies"]
    assert row["status"] == STATUS_INCLUDED
    assert row["source"] == SOURCE_MIRROR
    assert "2025-01-04" in row["detail"]
    with zipfile.ZipFile(out) as archive:
        assert "scored from a Mobility Database mirror copy" in archive.read("README.txt").decode()


def test_the_freshness_sweep_keeps_counting_down_a_mirror_copy() -> None:
    # A measured mirror copy is reswept like an origin fetch, so its countdown
    # never freezes (tests/test_sweep.py pins the hold once it goes negative).
    artifact = _mirror_artifact(status="measured", details={"last_service_date": "2026-12-01"})
    assert can_resweep(artifact)
    artifact["fetch"] = {"source": "origin"}
    assert can_resweep(artifact)
    # A copy whose freshness is already held is not measured: nothing to resweep.
    held = _mirror_artifact(status="not_yet_measured", reason="mirror_copy_expired")
    assert not can_resweep(held)


def test_a_lead_fix_never_pushes_the_list_past_three() -> None:

    findings = [
        Finding(
            code=f"c{i}",
            severity="WARNING",
            count=1,
            what="",
            why="",
            fix="",
            effort="",
            deduction=5.0,
        )
        for i in range(5)
    ]
    cat = CategoryResult(name="completeness", score=50.0, summary="", findings=findings)
    lead = Finding(
        code=FEED_DOWNLOAD_FAILED,
        severity="ERROR",
        count=1,
        what="",
        why="",
        fix="",
        effort="",
        deduction=0.0,
    )
    card = build_scorecard([cat], lead_fix=lead)
    assert [f.code for f in card.top_fixes] == [FEED_DOWNLOAD_FAILED, "c0", "c1"]


# --- the held record against the published schema ------------------------------
#
# hold_mirror_freshness shipped without its schema, and every test above reads
# the held category without validating it. publish() validates, so the first
# feed the sweep held stopped the Daily scorecard's collect job on 2026-11-07
# and 2026-11-08, and the site froze at 2026-11-06.

#: categories.freshness exactly as run 42484805472 printed it when it failed.
FAILING_FRESHNESS: dict[str, Any] = {
    "name": "freshness",
    "status": "not_yet_measured",
    "weight": 0.2,
    "reason": "mirror_copy_expired",
    "summary": (
        "Not graded. The feed URL on file could not be downloaded, "
        "and the Mobility Database mirror copy scored instead "
        "ended its service on 2023-03-22. That date describes the "
        "copy, not the feed the agency publishes today, so it does "
        "not count against the grade."
    ),
    "mirror_copy": {"service_start": None, "service_end": "2023-03-22"},
}
MIRROR_AGENCY = Agency(
    id="advance-transit-at",
    name="Advance Transit",
    static_gtfs_url=URL,
    license_note="test",
)


def _mirror_fetch(date: dt.date) -> FetchResult:
    return FetchResult(
        agency_id=MIRROR_AGENCY.id,
        path=Path("/tmp/gtfs.zip"),
        url=URL,
        fetched_date=date,
        sha256="a" * 64,
        size_bytes=1024,
        reused=False,
        source="mirror",
        origin_error="SSLError",
    )


def _freshness_category(last_service: str, days: int) -> CategoryResult:
    return CategoryResult(
        name="freshness",
        score=85.0 if days >= 0 else 0.0,
        summary="s",
        details={
            "has_feed_info": False,
            "service_type": "fixed",
            "last_service_date": last_service,
            "days_until_expiry": days,
        },
    )


def _measured_mirror_record(date: dt.date, last_service: str, days: int) -> dict[str, Any]:
    """A mirror copy still current on the day it was scored, as publish() stores it."""
    card = build_scorecard([_correctness(), _freshness_category(last_service, days)])
    return build_artifact(
        MIRROR_AGENCY, _mirror_fetch(date), card, dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    )


def _held_record() -> dict[str, Any]:
    record = _measured_mirror_record(dt.date(2023, 3, 1), "2023-03-22", 21)
    record["categories"]["freshness"] = dict(FAILING_FRESHNESS)
    return record


def test_the_exact_record_that_stopped_the_daily_run_is_valid() -> None:
    validate_artifact(_held_record())


def test_a_copy_the_sweep_holds_publishes_and_reads_back_held() -> None:
    # The path that failed: a measured copy lapses, the sweep holds it, publish validates.
    before = _measured_mirror_record(dt.date(2026, 6, 10), "2026-07-10", 30)
    swept, _summary = resweep(before, dt.date(2026, 7, 20))
    stored = json.loads(publish(swept).read_text())

    fresh = stored["categories"]["freshness"]
    assert fresh["status"] == "not_yet_measured"
    assert fresh["reason"] == "mirror_copy_expired"
    assert fresh["mirror_copy"] == {"service_start": None, "service_end": "2026-07-10"}
    assert "score" not in fresh and "details" not in fresh
    assert stored["overall"]["grade_qualifier"] == "partial: freshness not measured"
    assert stored["top_fixes"][0]["code"] == FEED_DOWNLOAD_FAILED
    # Held is not measured, so tomorrow's sweep passes over the stored record.
    assert not needs_sweep(stored, dt.date(2026, 7, 21))


def test_a_swept_hold_stops_claiming_freshness_was_measured() -> None:
    # The page prints the confidence block beside the partial grade. Carried
    # forward as it was, it read "Measured 4 of 4" on the same page.
    before = _measured_mirror_record(dt.date(2026, 6, 10), "2026-07-10", 30)
    measured_before = before["confidence"]["measured_categories"]
    level_before = before["confidence"]["level"]
    swept, _summary = resweep(before, dt.date(2026, 7, 20))

    assert swept["categories"]["freshness"]["status"] == "not_yet_measured"
    confidence = swept["confidence"]
    assert confidence["measured_categories"] == measured_before - 1
    assert "Freshness" in confidence["notes"][0]
    assert "not measured" in confidence["notes"][0]
    # What the sweep did not touch stays, and the level never rises.
    assert confidence["notes"][1:] == before["confidence"]["notes"][1:]
    assert confidence["fetch_source"] == "mirror"
    assert CONFIDENCE_LEVELS.index(confidence["level"]) <= CONFIDENCE_LEVELS.index(level_before)


def test_control_a_sweep_that_holds_nothing_leaves_confidence_alone() -> None:
    before = _measured_mirror_record(dt.date(2026, 6, 10), "2026-07-10", 30)
    swept, _summary = resweep(before, dt.date(2026, 6, 20))
    assert swept["categories"]["freshness"]["status"] == "measured"
    assert swept["confidence"] == before["confidence"]


@pytest.mark.parametrize(
    ("was_measured", "was_level", "now_measured", "now_level"),
    [
        (4, CONFIDENCE_LEVELS[2], 3, CONFIDENCE_LEVELS[1]),
        (4, CONFIDENCE_LEVELS[1], 3, CONFIDENCE_LEVELS[0]),
        (3, CONFIDENCE_LEVELS[1], 2, CONFIDENCE_LEVELS[1]),
        (2, CONFIDENCE_LEVELS[1], 1, CONFIDENCE_LEVELS[0]),
        (4, CONFIDENCE_LEVELS[0], 3, CONFIDENCE_LEVELS[0]),
    ],
)
def test_the_level_after_a_hold_moves_only_as_far_as_coverage_did(
    was_measured: int, was_level: str, now_measured: int, now_level: str
) -> None:
    names = ["correctness", "completeness", "realtime", "freshness"]
    categories = {
        name: {"status": "measured" if i < now_measured else "not_yet_measured"}
        for i, name in enumerate(names)
    }
    held = confidence_after_hold(
        {"level": was_level, "measured_categories": was_measured, "notes": ["old", "kept"]},
        categories,
    )
    assert (held["measured_categories"], held["level"]) == (now_measured, now_level)
    assert held["notes"][0] != "old" and held["notes"][1] == "kept"


def test_a_copy_the_full_run_holds_publishes_too() -> None:
    # The full run reaches the same record through build_scorecard_for_fetch.
    card = build_scorecard_for_fetch(
        [_correctness(), _freshness_category("2026-07-10", -10)],
        fetch_source="mirror",
        configured_url=URL,
        origin_error="SSLError",
    )
    artifact = build_artifact(
        MIRROR_AGENCY,
        _mirror_fetch(dt.date(2026, 7, 20)),
        card,
        dt.datetime(2026, 7, 20, tzinfo=dt.UTC),
    )
    stored = json.loads(publish(artifact).read_text())
    assert stored["categories"]["freshness"]["reason"] == "mirror_copy_expired"


def _set_in(path: tuple[str, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def apply(fresh: dict[str, Any]) -> None:
        target = fresh
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return apply


def _drop(key: str) -> Callable[[dict[str, Any]], None]:
    def apply(fresh: dict[str, Any]) -> None:
        del fresh[key]

    return apply


@pytest.mark.parametrize(
    "sabotage",
    [
        pytest.param(_set_in(("reason",), "feed_was_slow"), id="another-reason"),
        pytest.param(_set_in(("status",), "measured"), id="measured-with-a-reason"),
        pytest.param(_set_in(("name",), "correctness"), id="another-name"),
        pytest.param(_set_in(("score",), 0.0), id="a-score-standing-in-for-unknown"),
        pytest.param(_set_in(("details",), {}), id="details-beside-the-hold"),
        pytest.param(_set_in(("findings",), []), id="findings-beside-the-hold"),
        pytest.param(_set_in(("extra",), 1), id="an-unknown-key"),
        pytest.param(
            _set_in(("mirror_copy", "days_until_expiry"), -1325), id="a-countdown-on-the-copy"
        ),
        pytest.param(_set_in(("mirror_copy", "service_end"), 20230322), id="a-date-as-a-number"),
        pytest.param(_drop("mirror_copy"), id="no-mirror-copy"),
        pytest.param(_drop("reason"), id="no-reason"),
    ],
)
def test_control_the_schema_refuses_anything_else_on_a_held_freshness(
    sabotage: Callable[[dict[str, Any]], None],
) -> None:
    record = json.loads(json.dumps(_held_record()))
    untouched = json.loads(json.dumps(record["categories"]["freshness"]))
    sabotage(record["categories"]["freshness"])
    # A sabotage that silently failed to apply would read as a pass.
    assert record["categories"]["freshness"] != untouched
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact(record)


@pytest.mark.parametrize("category", ["correctness", "completeness", "realtime"])
def test_control_only_freshness_can_be_held(category: str) -> None:
    record = _held_record()
    record["categories"][category] = {**FAILING_FRESHNESS, "name": category}
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact(record)
