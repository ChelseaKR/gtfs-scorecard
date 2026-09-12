"""`scorecard try --batch`: a CSV of untracked feeds into a private cohort rollup (#363)."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import requests
from jsonschema import Draft202012Validator

from scorecard_pipeline import cli
from scorecard_pipeline.batch import (
    MAX_WORKERS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    BatchInputError,
    BatchResult,
    BatchRow,
    build_cohort_rollup,
    prepare_output_dir,
    read_batch_csv,
    render_rollup_html,
    render_rollup_markdown,
    rollup_members_csv,
    score_batch,
    scrub_local_paths,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.rollups import count_shared_fixes
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"
SCHEMA = Path(__file__).resolve().parents[2] / "web" / "schemas" / "batch-feeds.schema.json"
DATE = dt.date(2026, 6, 11)
LIVE = "https://live.example.test/gtfs.zip"
DEAD = "https://dead.example.test/gtfs.zip"


def _csv(path: Path, rows: list[list[str]], header: tuple[str, ...] = REQUIRED_COLUMNS) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.write_text(buffer.getvalue())
    return path


def _stub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fetched: list[str] | None = None
) -> None:
    """Offline scoring: every live link serves the trimmed fixture; DEAD refuses."""
    report = ValidationReport(
        validator_version="9.9.9",
        notices=[NoticeGroup(code="route_short_name_too_long", severity="WARNING", total=2)],
    )

    def fetch(agency: Agency, date: dt.date, **_kwargs: Any) -> FetchResult:
        url = agency.static_gtfs_url
        if fetched is not None:
            fetched.append(url)
        if url == DEAD:
            raise requests.ConnectionError("connection refused")
        return FetchResult(
            agency_id=agency.id,
            path=FIXTURE,
            url=url,
            fetched_date=date,
            sha256="ab" * 32,
            size_bytes=FIXTURE.stat().st_size,
            reused=False,
        )

    monkeypatch.setattr(cli, "raw_dir", lambda: tmp_path / "raw")
    monkeypatch.setattr(cli, "fetch_static", fetch)
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: Path("unused.json"))
    monkeypatch.setattr(cli, "parse_report", lambda *a, **k: report)


def _no_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "fetch_static", lambda *a, **k: pytest.fail("fetched a feed"))
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: pytest.fail("ran the validator"))


def _batch(csv_path: Path, out: Path, *extra: str) -> int:
    return cli.main(
        ["try", "--batch", str(csv_path), "--out", str(out), "--date", DATE.isoformat(), *extra]
    )


def _cohort(tmp_path: Path) -> Path:
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "local.zip").write_bytes(FIXTURE.read_bytes())
    return _csv(
        tmp_path / "cohort.csv",
        [
            ["Live Transit", LIVE, "US"],
            ["Dead Link Transit", DEAD, "US"],
            ["Local Shuttle", "exports/local.zip", "us"],
        ],
    )


# --- reading the CSV -----------------------------------------------------------------------


def test_a_valid_csv_reads_every_column(tmp_path: Path) -> None:
    path = tmp_path / "feeds.csv"
    path.write_text(
        "﻿name,url,country,ntd_id,large_feed\n"
        "Same Name,https://a.example/gtfs.zip,us,00007,Yes\n"
        "\n"
        "Same Name,exports/b.zip,CA,,\n"
        "Société de Transport,/abs/c.zip,US,12.0,false\n"
    )
    rows = read_batch_csv(path)

    assert [row.number for row in rows] == [2, 4, 5]
    assert [row.slug for row in rows] == ["same-name", "same-name-2", "societe-de-transport"]
    first, second, third = rows
    assert (first.country, first.ntd_id, first.large_feed) == ("US", "7", True)
    assert first.display_source == first.source == "https://a.example/gtfs.zip"
    assert second.source == str(tmp_path / "exports" / "b.zip")
    assert second.display_source == "b.zip"
    assert (second.ntd_id, second.large_feed) == ("", False)
    assert (third.source, third.display_source, third.ntd_id) == ("/abs/c.zip", "c.zip", "12")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "the CSV is empty"),
        ("name,url\nA,https://a.example/g.zip\n", "missing required column\\(s\\) country"),
        ("name,url,country,notes\n", "unknown column\\(s\\) notes"),
        ("name,url,country,country\n", "listed more than once: country"),
        ("name,url,country\n\n", "lists no feeds"),
        ("name,url,country\nA,https://a.example/g.zip\n", "expected 3 cells, found 2"),
        ("name,url,country\n,https://a.example/g.zip,US\n", "row 2: name is empty"),
        ("name,url,country\nA,,US\n", "row 2 \\(A\\): url is empty"),
        ("name,url,country\nA,ftp://a.example/g.zip,US\n", "only http and https"),
        ("name,url,country\nA,https://a.example/g.zip,ZZ\n", "assigned ISO 3166-1"),
        ("name,url,country,ntd_id\nA,https://a.example/g.zip,US,N/A\n", "is not a number"),
        ("name,url,country,large_feed\nA,https://a.example/g.zip,US,maybe\n", "true or false"),
        (
            "name,url,country\nA,https://a.example/g.zip,US\nB,https://a.example/g.zip,us\n",
            "already listed on row 2",
        ),
    ],
)
def test_a_csv_that_cannot_run_is_refused(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "feeds.csv"
    path.write_text(text)
    with pytest.raises(BatchInputError, match=message):
        read_batch_csv(path)


def test_an_unreadable_csv_is_refused(tmp_path: Path) -> None:
    with pytest.raises(BatchInputError, match="could not read the CSV"):
        read_batch_csv(tmp_path / "missing.csv")


def test_only_a_new_or_empty_output_folder_is_accepted(tmp_path: Path) -> None:
    prepare_output_dir(tmp_path / "new")
    (tmp_path / "empty").mkdir()
    prepare_output_dir(tmp_path / "empty")
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "rollup.md").write_text("old")
    with pytest.raises(BatchInputError, match="new or empty"):
        prepare_output_dir(tmp_path / "used")
    (tmp_path / "a-file").write_text("x")
    with pytest.raises(BatchInputError, match="new or empty"):
        prepare_output_dir(tmp_path / "a-file")


def test_the_published_schema_and_the_reader_agree(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    assert set(schema["properties"]) == set(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
    assert schema["required"] == list(REQUIRED_COLUMNS)
    assert schema["additionalProperties"] is False
    validator = Draft202012Validator(schema)

    def reader_accepts(row: dict[str, str]) -> bool:
        path = _csv(tmp_path / "one.csv", [list(row.values())], header=tuple(row))
        try:
            read_batch_csv(path)
        except BatchInputError:
            return False
        return True

    base = {"name": "A", "url": "https://a.example/g.zip", "country": "US"}
    cases = [
        (base, True),
        ({**base, "url": "HTTPS://A.example/g.zip"}, True),
        ({**base, "url": "exports/a.zip"}, True),
        ({**base, "ntd_id": "00007", "large_feed": "TRUE"}, True),
        ({**base, "ntd_id": "", "large_feed": ""}, True),
        ({"name": "A", "url": "https://a.example/g.zip"}, False),
        ({**base, "notes": "x"}, False),
        ({**base, "name": ""}, False),
        ({**base, "url": "ftp://a.example/g.zip"}, False),
        ({**base, "country": "U1"}, False),
        ({**base, "ntd_id": "N/A"}, False),
        ({**base, "large_feed": "maybe"}, False),
    ]
    for row, expected in cases:
        assert validator.is_valid(row) is expected, row
        assert reader_accepts(row) is expected, row
    # The one documented difference: two letters that are not an assigned code.
    assert validator.is_valid({**base, "country": "ZZ"})
    assert not reader_accepts({**base, "country": "ZZ"})


# --- the command ---------------------------------------------------------------------------


def test_a_missing_column_is_refused_before_any_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_fetch(monkeypatch)
    path = _csv(tmp_path / "feeds.csv", [["A", LIVE]], header=("name", "url"))

    assert _batch(path, tmp_path / "out") == 2
    assert not (tmp_path / "out").exists()


def test_a_used_output_folder_is_refused_before_any_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_fetch(monkeypatch)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "keep.txt").write_text("mine")

    assert _batch(_csv(tmp_path / "feeds.csv", [["A", LIVE, "US"]]), tmp_path / "out") == 2
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["keep.txt"]


def test_a_dead_link_is_a_row_with_a_reason_never_a_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fetched: list[str] = []
    _stub(monkeypatch, tmp_path, fetched=fetched)
    monkeypatch.setattr(cli, "load_agencies", lambda *a, **k: pytest.fail("loaded the registry"))
    out = tmp_path / "out"

    assert _batch(_cohort(tmp_path), out) == 0

    assert sorted(fetched) == [DEAD, LIVE]
    rollup = json.loads((out / "rollup.json").read_text())
    assert (rollup["feeds_listed"], rollup["feeds_scored"], rollup["feeds_not_scored"]) == (3, 2, 1)
    assert [m["name"] for m in rollup["members"]] == [
        "Live Transit",
        "Dead Link Transit",
        "Local Shuttle",
    ]
    dead = rollup["members"][1]
    assert dead["status"] == "not_scored"
    assert (dead["grade"], dead["score"], dead["scorecard_json"]) == (None, None, None)
    assert dead["reason"] == "could not fetch the feed: connection refused"
    assert sorted(p.name for p in (out / "feeds").iterdir()) == [
        "live-transit.html",
        "live-transit.json",
        "local-shuttle.html",
        "local-shuttle.json",
    ]
    for campaign in rollup["campaigns"]:
        assert campaign["baseline"]["agencies_checked"] == 2

    table = list(csv.DictReader(io.StringIO((out / "rollup.csv").read_text())))
    dead_row = next(row for row in table if row["feed_name"] == "Dead Link Transit")
    assert (dead_row["status"], dead_row["grade"], dead_row["score"]) == ("not_scored", "", "")
    assert "Not scored: could not fetch the feed" in (out / "rollup.md").read_text()
    assert "Not scored: could not fetch the feed" in (out / "rollup.html").read_text()
    assert "not scored  Dead Link Transit" in capsys.readouterr().out


def test_strict_exits_1_when_a_feed_could_not_be_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, tmp_path)
    cohort = _cohort(tmp_path)

    assert _batch(cohort, tmp_path / "strict", "--strict") == 1
    assert (tmp_path / "strict" / "rollup.json").exists()
    clean = _csv(tmp_path / "clean.csv", [["Live Transit", LIVE, "US"]])
    assert _batch(clean, tmp_path / "clean", "--strict") == 0


def test_identical_inputs_give_byte_identical_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, tmp_path)
    cohort = _cohort(tmp_path)

    assert _batch(cohort, tmp_path / "first", "--batch-workers", "3") == 0
    assert _batch(cohort, tmp_path / "second", "--batch-workers", "1") == 0

    def tree(root: Path) -> dict[str, bytes]:
        return {
            str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
        }

    first, second = tree(tmp_path / "first"), tree(tmp_path / "second")
    assert len(first) == 8
    assert first == second


def test_a_local_feed_is_recorded_by_name_and_never_by_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, tmp_path)
    out = tmp_path / "out"
    assert _batch(_cohort(tmp_path), out) == 0

    local = json.loads((out / "feeds" / "local-shuttle.json").read_text())
    assert local["feed"]["static_url"] == "local.zip"
    resolved = tmp_path.resolve()
    leaks = {str(resolved), resolved.as_uri(), str(tmp_path)}
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert not any(leak in text for leak in leaks), path.name


def test_a_missing_or_unreadable_local_file_is_a_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, tmp_path)
    (tmp_path / "broken.zip").write_bytes(b"this is not a zip archive")
    path = _csv(
        tmp_path / "local.csv",
        [["Gone", "missing.zip", "US"], ["Broken", "broken.zip", "US"], ["Live", LIVE, "US"]],
    )
    out = tmp_path / "out"

    assert _batch(path, out) == 0

    members = {m["name"]: m for m in json.loads((out / "rollup.json").read_text())["members"]}
    assert members["Gone"]["reason"].startswith("could not find the local file: ")
    assert "missing.zip" in members["Gone"]["reason"]
    assert str(tmp_path) not in members["Gone"]["reason"]
    assert members["Broken"]["status"] == "not_scored"
    assert members["Broken"]["reason"].startswith("could not read or score the feed: ")
    assert members["Live"]["status"] == "scored"


def test_single_feed_options_are_refused_with_batch(tmp_path: Path) -> None:
    path = tmp_path / "feeds.csv"
    for extra in (
        ["--html", "x.html"],
        ["--name", "X"],
        ["--min-days-to-expiry", "30"],
        ["--country", "CA"],
        ["--large-feed"],
        # `try --history` is written by the single-feed path only. Without this
        # the batch takes the flag and records nothing, which is the silent
        # ignore the refusal list exists to prevent.
        ["--history", "hist"],
    ):
        with pytest.raises(SystemExit) as exc:
            _batch(path, tmp_path / "out", *extra)
        assert exc.value.code == 2, extra
    for argv in (
        ["try", "--batch", str(path)],
        ["try", LIVE, "--batch", str(path), "--out", "d"],
        ["try"],
        ["try", LIVE, "--out", "d"],
        ["try", LIVE, "--strict"],
        ["try", "--batch", str(path), "--out", "d", "--batch-workers", str(MAX_WORKERS + 1)],
    ):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2, argv


# --- the rollup ----------------------------------------------------------------------------


def _row(name: str, number: int = 2) -> BatchRow:
    slug = name.casefold().replace(" ", "-")
    return BatchRow(
        number=number,
        name=name,
        source=f"https://{slug}.example/gtfs.zip",
        display_source=f"https://{slug}.example/gtfs.zip",
        country="US",
        ntd_id="",
        large_feed=False,
        slug=slug,
    )


def _fix(code: str) -> dict[str, Any]:
    return {"code": code, "fix": f"Fix {code}.", "count": 3, "effort": "One setting."}


def _scored(name: str, fixes: list[str], days: int | None = 90) -> BatchResult:
    details = {} if days is None else {"days_until_expiry": days}
    artifact = {
        "agency": {"id": "_adhoc", "name": name},
        "snapshot_date": DATE.isoformat(),
        "overall": {"grade": "B", "score": 84.0},
        "categories": {"freshness": {"status": "measured", "details": details, "findings": []}},
        "top_fixes": [_fix(code) for code in fixes],
    }
    return BatchResult(row=_row(name), artifact=artifact, reason=None)


def _failed(name: str) -> BatchResult:
    return BatchResult(row=_row(name), artifact=None, reason="could not fetch the feed: 404")


def test_shared_fix_counts_equal_the_per_feed_findings_both_ways() -> None:
    results = [
        _scored("Alpha", ["x", "y"]),
        _scored("Beta", ["x", "z"]),
        _scored("Gamma", ["y"]),
        _scored("Delta", ["x"]),
        _failed("Epsilon"),
    ]
    rollup = build_cohort_rollup(results, as_of=DATE, cohort_name="test")

    per_feed: Counter[tuple[str, str]] = Counter(
        (fix["code"], fix["fix"])
        for result in results
        if result.artifact is not None
        for fix in result.artifact["top_fixes"]
    )
    expected = {pair: n for pair, n in per_feed.items() if n > 1}
    published = {(f["code"], f["fix"]): f["feed_count"] for f in rollup["shared_fixes"]}
    assert published == expected
    assert [f["code"] for f in rollup["shared_fixes"]] == ["x", "y"]
    assert rollup["shared_fixes"][0]["feeds"] == ["Alpha", "Beta", "Delta"]


def test_the_written_rollup_counts_what_the_written_scorecards_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, tmp_path)
    out = tmp_path / "out"
    assert _batch(_cohort(tmp_path), out) == 0

    per_feed: Counter[tuple[str, str]] = Counter(
        (fix["code"], fix["fix"])
        for path in sorted((out / "feeds").glob("*.json"))
        for fix in json.loads(path.read_text())["top_fixes"]
    )
    rollup = json.loads((out / "rollup.json").read_text())
    published = {(f["code"], f["fix"]): f["feed_count"] for f in rollup["shared_fixes"]}
    assert published
    assert published == {pair: n for pair, n in per_feed.items() if n > 1}


def test_count_shared_fixes_keeps_the_published_rollup_semantics() -> None:
    shared = count_shared_fixes([[_fix("b"), _fix("a")], [_fix("a"), _fix("b")], [_fix("c")]])
    assert shared == [
        {"code": "b", "fix": "Fix b.", "agencies": 2},
        {"code": "a", "fix": "Fix a.", "agencies": 2},
    ]
    assert count_shared_fixes([]) == []


def test_worklists_omit_grades_and_point_at_the_local_scorecards() -> None:
    wheelchair = "scorecard_wheelchair_boarding_unknown"
    result = _scored("Alpha", [wheelchair])
    assert result.artifact is not None
    result.artifact["categories"]["completeness"] = {
        "status": "measured",
        "findings": [{"code": wheelchair, "count": 4, "what": "4 stops.", "fix": "Set it."}],
    }
    rollup = build_cohort_rollup([result, _failed("Beta")], as_of=DATE, cohort_name="test")

    accessibility = next(
        c for c in rollup["campaigns"] if c["campaign"]["kind"] == "accessibility-fields"
    )
    assert [t["scorecard_url"] for t in accessibility["targets"]] == ["feeds/alpha.html"]
    assert accessibility["baseline"]["agencies_checked"] == 1
    for campaign in rollup["campaigns"]:
        text = json.dumps(campaign)
        assert '"grade"' not in text
        assert '"score"' not in text


def test_the_expiring_section_orders_by_days_and_counts_unknown_expiry() -> None:
    results = [
        _scored("Later", ["x"], days=400),
        _scored("Soon", ["x"], days=10),
        _scored("Ended", ["x"], days=-5),
        _scored("Undated", ["x"], days=None),
        _failed("Dead"),
    ]
    rollup = build_cohort_rollup(results, as_of=DATE, cohort_name="test")

    assert [(m["name"], m["expiry_status"]) for m in rollup["expiring"]] == [
        ("Ended", "lapsed"),
        ("Soon", "expiring_soon"),
    ]
    assert rollup["expiry_unknown"] == 1
    markdown = render_rollup_markdown(rollup)
    assert "- Ended: -5 days (lapsed)" in markdown
    assert "1 scored feed publishes no date for the end of its service." in markdown
    assert "<p>1 scored feed publishes no date for the end of its service.</p>" in (
        render_rollup_html(rollup)
    )
    two = build_cohort_rollup(
        [_scored("A", ["x"], days=None), _scored("B", ["y"], days=None)],
        as_of=DATE,
        cohort_name="t",
    )
    assert "2 scored feeds publish no date for the end of their service." in (
        render_rollup_markdown(two)
    )


def test_renderings_handle_an_empty_cohort_section_and_escape_text() -> None:
    rollup = build_cohort_rollup(
        [_scored("Pipe | Transit", ["x"]), _failed("<b>Bad</b>")], as_of=DATE, cohort_name="c"
    )
    markdown = render_rollup_markdown(rollup)
    assert "Pipe \\| Transit" in markdown
    assert "No top fix appears in more than one scored feed." in markdown
    assert "No scored feed ends its service within 30 days." in markdown
    page = render_rollup_html(rollup)
    assert page.startswith('<!doctype html>\n<html lang="en">')
    assert "&lt;b&gt;Bad&lt;/b&gt;" in page
    assert "<script" not in page
    assert " src=" not in page
    assert "<link" not in page
    assert "No top fix appears in more than one scored feed." in page
    assert "No scored feed needs this fix." in page
    table = list(csv.reader(io.StringIO(rollup_members_csv(rollup))))
    assert table[0][0] == "feed_name"
    assert len(table) == 3


def test_score_batch_bounds_its_workers() -> None:
    for workers in (0, MAX_WORKERS + 1):
        with pytest.raises(ValueError, match="workers"):
            score_batch([], date=DATE, score=cli.run_adhoc_detailed, workers=workers)


def test_scrubbing_leaves_a_linked_feed_alone() -> None:
    row = _row("Alpha")
    artifact = {"feed": {"static_url": row.source}}
    assert scrub_local_paths(row, artifact) is artifact
