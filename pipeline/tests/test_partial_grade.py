"""A grade whose freshness was not measured is marked partial wherever it appears.

Rubric 1.5 holds an expired Mobility Database mirror copy's freshness out of
the grade (test_mirror_copy.py). The letter that the measured categories earn is
kept, but Chelsea's call (2026-11-05) is that it is never shown bare: every page,
badge, and export that prints it says "partial: freshness not measured", and the
unmeasured freshness itself is never rendered as a value (no 0, no "fresh").
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scorecard_pipeline import RUBRIC_VERSION, SCHEMA_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.badge import render_badge
from scorecard_pipeline.dataset import COLUMNS, build_quality_dataset, to_csv
from scorecard_pipeline.embed_badge import badge_sentence, badge_state, render_named_badge
from scorecard_pipeline.history_export import check_row
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import _history_entry, _write_badge
from scorecard_pipeline.render_site import (
    _agency_seo_metadata,
    _board_hero,
    _seo_grade_facts,
)
from scorecard_pipeline.report import build_report_data, render_report
from scorecard_pipeline.rescore_history import rescore_artifact
from scorecard_pipeline.score import (
    METHODOLOGY_CHANGELOG,
    PARTIAL_FRESHNESS_QUALIFIER,
    build_scorecard,
    build_scorecard_for_fetch,
    grade_qualifier,
    published_overall,
    qualified_grade,
    score_feed_content,
)

LABEL = "partial: freshness not measured"
TODAY = dt.date(2026, 11, 5)
URL = "https://iportal.example.org/GTFS/SRTD/google_transit.zip"
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "web" / "schemas"


def _expired_mirror_card(make_gtfs_zip: Callable[..., Path]) -> dict[str, Any]:
    path = make_gtfs_zip(
        {
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\n"
            "S1,Main St,38.5,-121.5,1\n",
            "trips.txt": "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\n"
            "R1,WK,T1,Downtown,1\n",
            "routes.txt": "route_id,route_short_name,route_type\nR1,1,3\n",
            "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,"
            "sunday,start_date,end_date\nWK,1,1,1,1,1,0,0,20240818,20250104\n",
        }
    )
    cats = [
        CategoryResult(name="correctness", score=90.0, summary="ok"),
        *score_feed_content(str(path), today=TODAY),
    ]
    return build_scorecard_for_fetch(
        cats, fetch_source="mirror", configured_url=URL, origin_error="SSLError"
    ).to_json()


def _artifact(card: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """A published artifact around ``card`` (a partial one by default)."""
    body = card or {
        "overall": {**published_overall(76.3), "grade_qualifier": LABEL},
        "categories": {
            "correctness": {"name": "correctness", "status": "measured", "score": 90.0},
            "freshness": {
                "name": "freshness",
                "status": "not_yet_measured",
                "reason": "mirror_copy_expired",
                "mirror_copy": {"service_start": "2024-08-18", "service_end": "2025-01-04"},
            },
        },
        "top_fixes": [],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {"id": SCORING_PROFILE_ID, "rubric_version": RUBRIC_VERSION},
        "validator_version": "8.0.1",
        "snapshot_date": "2026-11-05",
        "agency": {"id": "sampletown", "name": "Sampletown Transit"},
        "feed": {"static_url": URL, "sha256": "ab" * 32},
        "fetch": {"source": "mirror", "origin_error": "SSLError"},
        **body,
        **extra,
    }


def _full_artifact() -> dict[str, Any]:
    art = _artifact()
    art["overall"] = published_overall(84.0)
    art["categories"]["freshness"] = {
        "name": "freshness",
        "status": "measured",
        "score": 100.0,
        "details": {"days_until_expiry": 200},
    }
    art["fetch"] = {"source": "origin"}
    return art


# --- the scorecard and the artifact ---------------------------------------------------


def test_methodology_version_is_bumped_with_a_dated_note() -> None:
    assert RUBRIC_VERSION == "1.5"
    assert SCORING_PROFILE_ID == "gtfs-scorecard-1.5"
    newest = METHODOLOGY_CHANGELOG[0]
    assert newest["rubric_version"] == RUBRIC_VERSION
    assert newest["effective_date"] == "2026-11-05"
    assert LABEL in newest["summary"]


def test_a_held_freshness_keeps_the_letter_and_names_the_qualifier(
    make_gtfs_zip: Callable[..., Path],
) -> None:
    card = _expired_mirror_card(make_gtfs_zip)
    overall = card["overall"]
    assert overall["grade"] in {"A", "B", "C", "D", "F"}
    assert overall["grade_qualifier"] == PARTIAL_FRESHNESS_QUALIFIER == LABEL
    # The letter is still the one its own score earns.
    assert {k: v for k, v in overall.items() if k != "grade_qualifier"} == published_overall(
        overall["score"]
    )
    # Unmeasured freshness is no value at all, not a 0 and not a countdown.
    fresh = card["categories"]["freshness"]
    assert fresh["status"] == "not_yet_measured"
    assert "score" not in fresh and "details" not in fresh


def test_a_full_grade_carries_no_qualifier() -> None:
    card = build_scorecard(
        [
            CategoryResult(name="correctness", score=90.0, summary=""),
            CategoryResult(name="freshness", score=100.0, summary=""),
        ]
    ).to_json()
    assert "grade_qualifier" not in card["overall"]
    assert grade_qualifier(_full_artifact()) is None


def test_the_artifact_and_every_surface_use_one_qualifier_rule() -> None:
    # Review finding 2: a feed with stops and trips but no readable calendar
    # has no freshness category. Surfaces built through grade_qualifier() said
    # "partial", while the artifact's own overall carried a bare letter.
    card = build_scorecard(
        [
            CategoryResult(name="correctness", score=90.0, summary=""),
            CategoryResult(name="completeness", score=60.0, summary=""),
        ]
    ).to_json()
    assert card["categories"]["freshness"]["status"] == "not_yet_measured"
    assert card["overall"]["grade_qualifier"] == LABEL
    artifact = {"overall": card["overall"], "categories": card["categories"]}
    stripped = {**artifact, "overall": {**card["overall"]}}
    del stripped["overall"]["grade_qualifier"]
    # The stated qualifier and the derived one agree.
    assert grade_qualifier(artifact) == grade_qualifier(stripped) == LABEL


def test_the_qualifier_is_derived_for_an_artifact_that_does_not_state_it() -> None:
    legacy = _artifact()
    del legacy["overall"]["grade_qualifier"]
    assert grade_qualifier(legacy) == LABEL
    assert grade_qualifier({"categories": legacy["categories"]}) is None  # no grade, no mark
    assert grade_qualifier(None) is None
    assert qualified_grade("C", LABEL) == "C (partial: freshness not measured)"
    assert qualified_grade("C", None) == "C"


def test_the_published_schemas_accept_the_qualifier_and_nothing_else() -> None:
    schema = json.loads((SCHEMA_DIR / "artifact.schema.json").read_text())
    overall = Draft202012Validator(schema["properties"]["overall"])
    assert overall.is_valid({**published_overall(76.3), "grade_qualifier": LABEL})
    assert overall.is_valid(published_overall(76.3))
    assert not overall.is_valid({**published_overall(76.3), "grade_qualifier": "fresh"})
    for name in ("catalog.schema.json", "directory.schema.json", "rollup.schema.json"):
        text = (SCHEMA_DIR / name).read_text()
        assert '"grade_qualifier"' in text, name


# --- exports: index history, dataset, CSV, history tables -----------------------------


def test_index_history_and_the_flat_exports_carry_the_column() -> None:
    partial, full = _history_entry(_artifact()), _history_entry(_full_artifact())
    assert partial["grade_qualifier"] == LABEL
    assert full["grade_qualifier"] is None
    assert partial["days_until_expiry"] is None
    assert "freshness" not in partial["categories"]

    index = {
        "agencies": {
            "partial-feed": {"name": "Partial", "history": [partial]},
            "full-feed": {"name": "Full", "history": [full]},
        }
    }
    dataset = build_quality_dataset(index)
    assert dataset["schema_version"] == "1.7"
    assert COLUMNS.index("grade_qualifier") == COLUMNS.index("grade") + 1
    rows = {r["id"]: r for r in dataset["rows"]}
    assert rows["partial-feed"]["grade_qualifier"] == LABEL
    assert rows["partial-feed"]["freshness"] is None
    assert rows["full-feed"]["grade_qualifier"] is None

    parsed = {r["id"]: r for r in csv.DictReader(io.StringIO(to_csv(dataset)))}
    assert parsed["partial-feed"]["grade_qualifier"] == LABEL
    assert parsed["partial-feed"]["freshness"] == ""
    assert parsed["full-feed"]["grade_qualifier"] == ""


def test_the_history_tables_carry_the_column() -> None:
    row = check_row("sampletown", _artifact(), agency=None, finding_count=0)
    assert row["grade_qualifier"] == LABEL
    assert row["freshness"] is None
    assert check_row("x", _full_artifact(), agency=None, finding_count=0)["grade_qualifier"] is None


# --- badges ------------------------------------------------------------------------


def test_the_compact_badge_and_its_endpoint_say_partial(tmp_path: Path) -> None:
    svg = render_badge("C", 76.3, expiry_status="unknown", qualifier=LABEL)
    assert LABEL in svg
    assert "partial" not in render_badge("C", 76.3, expiry_status="unknown")

    _write_badge(tmp_path, _artifact())
    assert LABEL in (tmp_path / "badge.svg").read_text()
    message = json.loads((tmp_path / "badge.json").read_text())["message"]
    assert message == f"C 76.3 · {LABEL}"
    assert "expired" not in message


def test_the_named_badge_says_partial() -> None:
    state = badge_state("Sampletown Transit", _artifact(), TODAY)
    assert state.qualifier == LABEL
    assert f"grade C ({LABEL})" in badge_sentence(state)
    svg = render_named_badge(state)
    assert "Partial: freshness not measured" in svg
    assert "Score 76.3 of 100 · 2026-11-05" in svg

    full = badge_state("Sampletown Transit", _full_artifact(), TODAY)
    assert full.qualifier is None
    assert "artial" not in render_named_badge(full)


# --- pages and the paid report -----------------------------------------------------


def test_the_agency_hero_marks_the_grade_and_shows_no_freshness_value() -> None:
    html = _board_hero("Sampletown Transit", "sampletown", _artifact(), [])
    assert "Partial: freshness not measured." in html
    assert f'aria-label="Overall grade C ({LABEL})"' in html
    # No freshness chip of any kind: nothing was measured to put in one.
    for chip in ("Covers", "Feed expired", "Expires in", "Review service end date"):
        assert chip not in html

    full = _board_hero("Sampletown Transit", "sampletown", _full_artifact(), [])
    assert "artial" not in full


def test_the_search_snippet_carries_the_qualifier_within_budget() -> None:
    facts = _seo_grade_facts(_artifact())
    assert facts == (f"C ({LABEL})", "76.3", "2026-11-05")
    long_name = "Sacramento Regional Transit District Light Rail and Bus Services"
    meta = _agency_seo_metadata(long_name, location_label="California", grade_facts=facts)
    assert f"grade C ({LABEL}), 76.3 of 100" in meta.description
    assert len(meta.description) <= 155
    assert _seo_grade_facts(_full_artifact()) == ("B", "84.0", "2026-11-05")


def test_the_paid_report_marks_the_grade() -> None:
    now = dt.datetime(2026, 11, 5, 12, tzinfo=dt.UTC)
    html = render_report(build_report_data(_artifact(), [], generated_at=now))
    assert f"Grade C &middot; 76.3 out of 100 &middot; {LABEL}</p>" in html
    full = render_report(build_report_data(_full_artifact(), [], generated_at=now))
    assert "artial: freshness" not in full


# --- the rescored national history ------------------------------------------------


def test_rescoring_never_turns_an_expired_mirror_copy_back_into_a_grade() -> None:
    old = _artifact()
    old["rubric_version"] = "1.4"
    old["overall"] = published_overall(51.1)
    old["categories"]["freshness"] = {
        "name": "freshness",
        "status": "measured",
        "score": 0.0,
        "details": {"feed_end_date": "2025-01-04", "last_service_date": "2025-01-04"},
    }
    old["categories"]["correctness"] = {
        "name": "correctness",
        "status": "measured",
        "score": 100.0,
        "findings": [],
        "details": {"distinct_codes": 0, "instances_by_severity": {}},
    }
    old["categories"]["completeness"] = {
        "name": "completeness",
        "status": "measured",
        "score": 80.0,
        "findings": [],
        "details": {"stops": 1, "trips": 1, "mixed_case_stop_name_pct": 100.0},
    }
    result = rescore_artifact(old, {})
    assert result.row is None
    assert result.reason == "freshness_held_expired_mirror_copy"

    old["fetch"] = {"source": "origin"}
    assert rescore_artifact(old, {}).row is not None
