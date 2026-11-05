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

from scorecard_pipeline.bundle import SOURCE_MIRROR, STATUS_INCLUDED, build_bundle, parse_request
from scorecard_pipeline.feed_provenance import mirror_copy_caveat
from scorecard_pipeline.metrics import Finding
from scorecard_pipeline.report import build_report_data, render_report
from scorecard_pipeline.score import (
    FEED_DOWNLOAD_FAILED,
    build_scorecard,
    build_scorecard_for_fetch,
    score_feed_content,
)
from scorecard_pipeline.sweep import can_resweep

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
    from scorecard_pipeline.metrics import CategoryResult

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


def test_the_freshness_sweep_does_not_count_down_a_mirror_copy() -> None:
    artifact = _mirror_artifact(status="measured", details={"last_service_date": "2026-12-01"})
    assert not can_resweep(artifact)
    artifact["fetch"] = {"source": "origin"}
    assert can_resweep(artifact)


def test_a_lead_fix_never_pushes_the_list_past_three() -> None:
    from scorecard_pipeline.metrics import CategoryResult

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
