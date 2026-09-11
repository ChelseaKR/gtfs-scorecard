"""Workspace mode (#362): a private history for untracked feeds, read back as a trend."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from scorecard_pipeline import RUBRIC_VERSION, SCORING_PROFILE_ID, cli
from scorecard_pipeline.alerts import AlertItem, build_digest
from scorecard_pipeline.config import artifacts_dir
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.publish import _history_entry
from scorecard_pipeline.validate import VALIDATOR_VERSION, NoticeGroup, ValidationReport
from scorecard_pipeline.workspace import (
    BOUNDARY,
    CHANGED,
    FIRST,
    HISTORY_FILENAME,
    RECORD_TYPE,
    RENDERERS,
    SAME_BYTES,
    UNCHANGED,
    WorkspaceError,
    append_run,
    build_record,
    build_trend,
    compare_step,
    describe_source,
    read_ledger,
    slug_for,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "web" / "schemas" / "workspace-history.schema.json").read_text())
FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"
SOURCE = "https://transit.example/gtfs.zip"
NAME = "Parity Transit"
SLUG = "parity-transit"
FINDING_TEXT = "Three trips have no destination sign."
CONTACT = "ops@transit.example"


def _artifact(
    date: str,
    score: float,
    *,
    days: int | None = 300,
    sha: str = "a" * 64,
    validator: str = VALIDATOR_VERSION,
    profile: str = SCORING_PROFILE_ID,
    name: str = NAME,
) -> dict[str, Any]:
    return {
        "agency": {"id": "_adhoc", "name": name},
        "snapshot_date": date,
        "overall": {"score": score, "grade": "C"},
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {"id": profile, "rubric_version": RUBRIC_VERSION},
        "validator_version": validator,
        "feed": {"static_url": SOURCE, "sha256": sha},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": score,
                "findings": [
                    {
                        "code": "missing_trip_headsign",
                        "count": 3,
                        "what": FINDING_TEXT,
                        "why": "Riders cannot tell which way the bus goes.",
                        "fix": "Export a headsign.",
                        "effort": "One setting.",
                    }
                ],
            },
            "freshness": {
                "status": "measured",
                "score": 80.0,
                "details": {
                    "days_until_expiry": days,
                    "service_type": "fixed",
                    "feed_contact_email": CONTACT,
                },
                "findings": [],
            },
            "completeness": {"status": "measured", "score": 70.0, "findings": []},
            "realtime": {"status": "not_yet_measured", "findings": []},
        },
        "top_fixes": [{"rank": 1, "code": "missing_trip_headsign", "count": 3}],
    }


def _ledger_lines(history: Path, slug: str = SLUG) -> list[str]:
    return (history / slug / HISTORY_FILENAME).read_text().splitlines()


# --- the record -------------------------------------------------------------------------


def test_a_record_holds_counts_and_codes_only() -> None:
    record = build_record(
        _artifact("2026-06-11", 84.0), source=describe_source("/home/someone/exports/feed.zip")
    )

    Draft202012Validator(SCHEMA).validate(record)
    dumped = json.dumps(record)
    assert FINDING_TEXT not in dumped
    assert CONTACT not in dumped
    assert "/home/someone" not in dumped
    assert record["source"] == "local file feed.zip"
    assert record["findings"] == {"missing_trip_headsign": 3}
    assert set(record["categories"]) == {"correctness", "freshness", "completeness"}
    assert record["freshness"] == {
        "days_until_expiry": 300,
        "service_type": "fixed",
        "finding_codes": [],
    }
    assert record["record_type"] == RECORD_TYPE


def test_the_record_carries_the_index_trend_point_unchanged() -> None:
    artifact = _artifact("2026-06-11", 84.0)
    record = build_record(artifact, source=SOURCE)
    assert {key: record[key] for key in _history_entry(artifact)} == _history_entry(artifact)


def test_the_schema_refuses_a_field_that_could_carry_text() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    record = build_record(_artifact("2026-06-11", 84.0), source=SOURCE)
    record["what"] = FINDING_TEXT
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(record)


def test_slugs_and_sources() -> None:
    assert slug_for("Parity Transit") == "parity-transit"
    assert slug_for("南信州広域連合") == "南信州広域連合"
    assert slug_for("...") == "feed"
    assert describe_source(SOURCE) == SOURCE


# --- comparing runs -----------------------------------------------------------------------


def test_two_runs_on_identical_bytes_are_unchanged_and_raise_no_regression(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history"
    _path, first = append_run(history, _artifact("2026-06-11", 84.0), source=SOURCE)
    path, second = append_run(history, _artifact("2026-06-11", 84.0), source=SOURCE)

    assert (first.kind, second.kind) == (FIRST, UNCHANGED)
    assert path == history / SLUG / HISTORY_FILENAME
    assert len(_ledger_lines(history)) == 2
    trend = build_trend(history)
    assert [row.step.kind for row in trend.feeds[0].rows] == [FIRST, UNCHANGED]
    assert [item.kind for item in trend.feeds[0].alerts] == []


def test_same_bytes_with_a_moved_score_is_not_called_unchanged() -> None:
    before = build_record(_artifact("2026-06-11", 84.0), source=SOURCE)
    after = build_record(_artifact("2026-06-20", 81.0), source=SOURCE)
    step = compare_step(before, after)
    assert step.kind == SAME_BYTES
    assert "score 84.0 to 81.0" in step.sentence


def test_a_new_export_is_compared_and_a_grade_drop_is_a_regression(tmp_path: Path) -> None:
    history = tmp_path / "history"
    append_run(history, _artifact("2026-06-11", 90.0), source=SOURCE)
    _path, step = append_run(history, _artifact("2026-06-12", 80.0, sha="b" * 64), source=SOURCE)

    assert step.kind == CHANGED
    assert "grade A to B" in step.sentence
    assert [item.kind for item in build_trend(history).feeds[0].alerts] == ["regression"]


@pytest.mark.parametrize(
    ("validator", "profile", "label"),
    [
        ("7.0.0", SCORING_PROFILE_ID, "validator 7.0.0 to"),
        (VALIDATOR_VERSION, "experimental", "scoring profile experimental to"),
    ],
)
def test_a_record_measured_differently_is_shown_and_never_compared(
    tmp_path: Path, validator: str, profile: str, label: str
) -> None:
    history = tmp_path / "history"
    first = _artifact("2026-06-11", 95.0, validator=validator, profile=profile)
    append_run(history, first, source=SOURCE)
    _path, step = append_run(history, _artifact("2026-06-12", 60.0, sha="b" * 64), source=SOURCE)

    assert step.kind == BOUNDARY
    assert label in step.sentence
    feed = build_trend(history).feeds[0]
    assert [row.step.kind for row in feed.rows] == [FIRST, BOUNDARY]
    # A 35-point fall across the boundary is neither a regression nor a cliff.
    assert [item.kind for item in feed.alerts] == []


def test_records_that_do_not_say_how_they_were_measured_are_not_compared() -> None:
    before = build_record(_artifact("2026-06-11", 84.0), source=SOURCE)
    after = build_record(_artifact("2026-06-12", 84.0), source=SOURCE)
    before["validator_version"] = after["validator_version"] = None
    step = compare_step(before, after)
    assert step.kind == BOUNDARY
    assert "do not say fully how they were measured" in step.sentence


# --- the alert set equals `scorecard alerts` ----------------------------------------------


def _history_scenario(name: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Artifacts for one feed, and the alert kinds they must raise."""
    if name == "expiry and a sustained cliff":
        return [
            _artifact("2026-06-01", 90.0, days=200),
            _artifact("2026-06-02", 90.0, days=199),
            _artifact("2026-06-03", 60.0, days=19, sha="b" * 64),
            _artifact("2026-06-04", 60.0, days=18, sha="b" * 64),
        ], ["expiry", "anomaly", "anomaly"]
    if name == "regression":
        return [
            _artifact("2026-06-01", 90.0),
            _artifact("2026-06-02", 80.0, sha="b" * 64),
        ], ["regression"]
    if name == "boundary":
        return [
            _artifact("2026-06-01", 95.0, validator="7.0.0"),
            _artifact("2026-06-02", 60.0, sha="b" * 64),
        ], []
    return [_artifact("2026-06-01", 84.0), _artifact("2026-06-01", 84.0)], []


def _comparable(items: list[AlertItem]) -> list[tuple[Any, ...]]:
    # Links are left out on purpose: a private feed has no public page to link to.
    return [
        (
            i.kind,
            i.agency_name,
            i.headline,
            i.detail,
            i.fix,
            i.days_until_expiry,
            i.planned_boundary,
        )
        for i in items
    ]


@pytest.mark.parametrize(
    "scenario", ["expiry and a sustained cliff", "regression", "boundary", "unchanged"]
)
def test_the_alert_set_equals_scorecard_alerts_for_the_same_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    artifacts, expected_kinds = _history_scenario(scenario)
    # The registered-feed side: the same history in index.json, the newest
    # artifact as latest.json, read by `scorecard alerts`' own digest.
    monkeypatch.setattr("scorecard_pipeline.alerts.current_agency_ids", lambda ids: list(ids))
    feed_dir = artifacts_dir() / SLUG
    feed_dir.mkdir(parents=True)
    (feed_dir / "latest.json").write_text(json.dumps(artifacts[-1]))
    index = {"agencies": {SLUG: {"name": NAME, "history": [_history_entry(a) for a in artifacts]}}}
    (artifacts_dir() / "index.json").write_text(json.dumps(index))
    registered = _comparable(build_digest(today=dt.date(2026, 6, 4), expiry_days=60).items)

    history = tmp_path / "history"
    for artifact in artifacts:
        append_run(history, artifact, source=SOURCE)
    workspace = _comparable(build_trend(history, expiry_days=60).feeds[0].alerts)

    assert workspace == registered
    assert [item[0] for item in workspace] == expected_kinds


# --- an unreadable line is named, never dropped silently ------------------------------------


def _corrupt_ledger(history: Path) -> Path:
    append_run(history, _artifact("2026-06-11", 84.0), source=SOURCE)
    path = history / SLUG / HISTORY_FILENAME
    good = json.loads(path.read_text())
    foreign = dict(good, schema_version="2.0")
    undated = {key: value for key, value in good.items() if key != "date"}
    with path.open("ab") as handle:
        handle.write(b"{not json\n")
        handle.write(json.dumps(foreign).encode() + b"\n")
        handle.write(b'["a list"]\n')
        handle.write(b"\xff\xfe\n")
        handle.write(json.dumps(undated).encode() + b"\n")
        handle.write(b"\n")
        handle.write(json.dumps(dict(good, record_type="other")).encode() + b"\n")
        handle.write(json.dumps(dict(good, date="yesterday")).encode() + b"\n")
    return path


def test_a_corrupt_line_is_skipped_and_named(tmp_path: Path) -> None:
    history = tmp_path / "history"
    ledger = read_ledger(_corrupt_ledger(history), slug=SLUG)

    assert len(ledger.records) == 1
    assert [(line.line, line.reason) for line in ledger.skipped] == [
        (2, "not valid JSON (Expecting property name enclosed in double quotes)"),
        (3, "schema version '2.0' is not one this build reads (1.x)"),
        (4, "not a JSON object"),
        (5, "not valid UTF-8"),
        (6, "field 'date' is missing or malformed"),
        (8, "not a workspace history record"),
        (9, "field 'date' is not a date"),
    ]
    trend = build_trend(history)
    for render in RENDERERS.values():
        assert "parity-transit/history.jsonl line 2: not valid JSON" in render(trend)


def test_the_command_logs_every_skipped_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    history = tmp_path / "history"
    _corrupt_ledger(history)
    _no_registry(monkeypatch)
    with caplog.at_level(logging.WARNING):
        assert cli.main(["trend", "--history", str(history)]) == 0
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 7
    assert any("line 5: not valid UTF-8; skipped" in message for message in warned)


def test_a_ledger_with_nothing_readable_still_reports_its_lines(tmp_path: Path) -> None:
    path = tmp_path / "history" / "broken" / HISTORY_FILENAME
    path.parent.mkdir(parents=True)
    path.write_text("{not json\n")
    feed = build_trend(tmp_path / "history").feeds[0]
    assert (feed.name, feed.rows, feed.alerts) == ("broken", [], [])
    for render in RENDERERS.values():
        out = render(build_trend(tmp_path / "history"))
        assert "No readable records." in out
        assert "broken/history.jsonl line 1" in out


# --- refusals --------------------------------------------------------------------------------


def test_a_second_feed_is_refused_rather_than_joined(tmp_path: Path) -> None:
    history = tmp_path / "history"
    append_run(history, _artifact("2026-06-11", 84.0), source=SOURCE)
    with pytest.raises(WorkspaceError, match="already records a different feed"):
        append_run(history, _artifact("2026-06-12", 84.0), source="https://other.example/gtfs.zip")
    assert len(_ledger_lines(history)) == 1


def test_a_record_the_reader_would_skip_is_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "scorecard_pipeline.workspace._history_entry",
        lambda artifact: {"date": "yesterday", "score": 1.0, "grade": "F"},
    )
    with pytest.raises(WorkspaceError, match="would not be readable"):
        append_run(tmp_path / "history", _artifact("2026-06-11", 84.0), source=SOURCE)
    assert not (tmp_path / "history").exists()


def test_trend_refuses_when_there_is_nothing_to_read(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError, match=r"no history\.jsonl under"):
        build_trend(tmp_path)
    append_run(tmp_path, _artifact("2026-06-11", 84.0), source=SOURCE)
    with pytest.raises(WorkspaceError, match="no history for elsewhere"):
        build_trend(tmp_path, feeds=["elsewhere"])
    assert [feed.slug for feed in build_trend(tmp_path, feeds=[SLUG]).feeds] == [SLUG]


# --- rendering ---------------------------------------------------------------------------------


def test_html_is_self_contained_and_escaped(tmp_path: Path) -> None:
    history = tmp_path / "history"
    append_run(history, _artifact("2026-06-11", 90.0, name="<b>Bold</b> Transit"), source=SOURCE)
    append_run(
        history,
        _artifact("2026-06-12", 80.0, sha="b" * 64, days=10, name="<b>Bold</b> Transit"),
        source=SOURCE,
    )
    out = RENDERERS["html"](build_trend(history))
    assert "<script" not in out
    assert 'src="http' not in out
    assert 'href="http' not in out
    assert "&lt;b&gt;Bold&lt;/b&gt; Transit" in out
    assert "<b>Bold</b>" not in out
    assert "<li>Expiry:" in out


def test_markdown_escapes_table_pipes(tmp_path: Path) -> None:
    history = tmp_path / "history"
    append_run(history, _artifact("2026-06-11", 84.0, name="A | B"), source=SOURCE)
    out = RENDERERS["markdown"](build_trend(history))
    assert "## A \\| B (`a-b`)" in out
    assert "| 2026-06-11 | B | 84.0 | 300 |" in out


# --- the commands --------------------------------------------------------------------------------


def _stub_scoring(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched = FetchResult(
        agency_id="_adhoc",
        path=FIXTURE,
        url=SOURCE,
        fetched_date=dt.date(2026, 6, 11),
        sha256="ab" * 32,
        size_bytes=FIXTURE.stat().st_size,
        reused=False,
    )
    report = ValidationReport(
        validator_version="9.9.9",
        notices=[NoticeGroup(code="route_short_name_too_long", severity="WARNING", total=2)],
    )
    monkeypatch.setattr(cli, "fetch_static", lambda *a, **k: fetched)
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: Path("unused.json"))
    monkeypatch.setattr(cli, "parse_report", lambda *a, **k: report)


def _no_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "load_agencies", lambda *a, **k: pytest.fail("trend must not load the registry")
    )


def test_try_history_then_trend_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_scoring(monkeypatch)
    history = tmp_path / "history"
    argv = ["try", SOURCE, "--name", "Stub Transit", "--date", "2026-06-11"]
    assert cli.main([*argv, "--history", str(history)]) == 0
    assert cli.main([*argv, "--history", str(history)]) == 0
    assert "Unchanged: the same feed bytes, scored the same." in capsys.readouterr().out
    assert len(_ledger_lines(history, "stub-transit")) == 2

    _no_registry(monkeypatch)
    out = tmp_path / "trend.md"
    code = cli.main(["trend", "--history", str(history), "--format", "markdown", "--out", str(out)])
    assert code == 0
    text = out.read_text()
    assert "## Stub Transit (`stub-transit`)" in text
    assert "Regression:" not in text

    assert cli.main(["trend", "--history", str(history)]) == 0
    assert "== Stub Transit (stub-transit) ==" in capsys.readouterr().out


def test_try_history_refuses_a_different_feed_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_scoring(monkeypatch)
    history = tmp_path / "history"
    base = ["--name", "Stub Transit", "--date", "2026-06-11", "--history", str(history)]
    assert cli.main(["try", SOURCE, *base]) == 0
    assert cli.main(["try", "https://other.example/gtfs.zip", *base]) == 2
    assert len(_ledger_lines(history, "stub-transit")) == 1


def test_trend_with_nothing_to_read_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_registry(monkeypatch)
    assert cli.main(["trend", "--history", str(tmp_path)]) == 2


# --- the Action and its documentation ---


def test_the_action_passes_history_path_only_when_set() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert action["inputs"]["history-path"]["default"] == ""
    step = action["runs"]["steps"][-1]
    assert step["env"]["HISTORY_PATH"] == "${{ inputs.history-path }}"
    run = step["run"]
    line = 'if [[ -n "$HISTORY_PATH" ]]; then args+=(--history "$HISTORY_PATH"); fi'
    assert line in run
    assert run.index(line) < run.index("gate_rc=$?")


def test_the_docs_never_present_history_path_as_released() -> None:
    docs = (ROOT / "docs" / "ci-action.md").read_text()
    gap = docs[docs.index("**What `v1.4.0` does not yet include.**") :]
    gap = gap[: gap.index("\n## ")]
    assert "`history-path`" in gap
    row = next(line for line in docs.splitlines() if line.startswith("| `history-path` |"))
    assert "Not in `v1.4.0`" in row
