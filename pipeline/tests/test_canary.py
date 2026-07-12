"""Tests for the validator-upgrade canary (FIX-06): deterministic sampling,
grade/notice diffing, the Markdown impact report, and the CLI wiring.

The diff and report layers are pure functions over synthetic result dicts, and
the shadow-run orchestration is exercised with the fetch/validate layer mocked,
so nothing here touches the network or the Java validator.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import scorecard_pipeline.canary as canary
from scorecard_pipeline.canary import (
    agency_result,
    changelog_summary,
    diff_results,
    render_report,
    run_canary,
    sample_agencies,
    shadow_score_agency,
    write_report,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.validate import VALIDATOR_VERSION, NoticeGroup, ValidationReport
from scorecard_pipeline.vcache import load_cached, store_cached

AS_OF = dt.date(2026, 7, 2)

# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_sample_is_deterministic_and_spread() -> None:
    ids = [f"agency-{i:04d}" for i in range(500)]
    first = sample_agencies(ids, size=100, seed=0)
    second = sample_agencies(ids, size=100, seed=0)
    assert first == second  # same seed, same sample: runs are reproducible
    assert len(first) == 100
    assert len(set(first)) == 100  # no duplicates
    assert set(first) <= set(ids)
    # Stride sampling spans the registry rather than clustering at the front.
    assert any(i >= "agency-0400" for i in first)


def test_sample_seed_rotates_the_selection() -> None:
    ids = [f"agency-{i:04d}" for i in range(500)]
    assert sample_agencies(ids, size=100, seed=0) != sample_agencies(ids, size=100, seed=3)


def test_sample_returns_everything_when_population_is_small() -> None:
    assert sample_agencies(["b", "a", "a"], size=100) == ["a", "b"]


def test_sample_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError):
        sample_agencies(["a"], size=0)


# ---------------------------------------------------------------------------
# Diffing (pure, over synthetic result dicts)
# ---------------------------------------------------------------------------


def _result(
    agency_id: str,
    grade: str,
    score: float,
    notices: dict[str, tuple[str, int]] | None = None,
) -> dict[str, Any]:
    report = ValidationReport(
        validator_version="x",
        notices=[
            NoticeGroup(code=code, severity=sev, total=total)
            for code, (sev, total) in (notices or {}).items()
        ],
    )
    return agency_result(agency_id, report, grade, score)


def test_diff_grades_band_moves_and_median() -> None:
    baseline = [
        _result("up", "B", 89.5),
        _result("flat", "A", 95.0),
        _result("down", "C", 70.5),
    ]
    candidate = [
        _result("up", "A", 90.2),
        _result("flat", "A", 95.0),
        _result("down", "D", 68.0),
    ]
    diff = diff_results(baseline, candidate)
    assert diff["agencies_compared"] == 3
    assert diff["median_score_delta"] == 0.0
    assert diff["band_move_histogram"] == {"+1": 1, "0": 1, "-1": 1}
    moves = {m["agency_id"]: m for m in diff["band_moves"]}
    assert set(moves) == {"up", "down"}
    assert moves["up"]["grade_before"] == "B"
    assert moves["up"]["grade_after"] == "A"
    assert moves["up"]["band_move"] == 1
    assert moves["down"]["band_move"] == -1
    assert moves["down"]["score_delta"] == -2.5


def test_diff_compares_only_shared_agencies_and_records_skips() -> None:
    diff = diff_results(
        [_result("only-baseline", "A", 95.0)],
        [_result("only-candidate", "A", 95.0)],
        skipped=["zeta", "alpha"],
    )
    assert diff["agencies_compared"] == 0
    assert diff["median_score_delta"] == 0.0
    assert diff["band_move_histogram"] == {}
    assert diff["skipped_agencies"] == ["alpha", "zeta"]  # sorted for stable reports


def test_diff_notice_population_changes() -> None:
    baseline = [
        _result("a", "B", 85.0, {"gone": ("WARNING", 10), "reclass": ("INFO", 3)}),
        _result("b", "B", 85.0, {"gone": ("WARNING", 5), "grows": ("WARNING", 2)}),
    ]
    candidate = [
        _result("a", "B", 85.0, {"reclass": ("ERROR", 3), "new": ("ERROR", 40)}),
        _result("b", "B", 85.0, {"grows": ("WARNING", 8)}),
    ]
    diff = diff_results(baseline, candidate)
    changes = {c["code"]: c for c in diff["notice_changes"]}
    assert changes["new"]["status"] == "added"
    assert changes["new"]["severity_before"] is None
    assert changes["new"]["instances_after"] == 40
    assert changes["new"]["agencies_after"] == 1
    assert changes["gone"]["status"] == "removed"
    assert changes["gone"]["instances_before"] == 15
    assert changes["gone"]["agencies_before"] == 2
    assert changes["reclass"]["status"] == "reclassified"
    assert changes["reclass"]["severity_before"] == "INFO"
    assert changes["reclass"]["severity_after"] == "ERROR"
    assert changes["grows"]["status"] == "changed"
    assert changes["grows"]["instances_before"] == 2
    assert changes["grows"]["instances_after"] == 8
    # Ranked by how many instances the change touches: the biggest driver first.
    assert [c["code"] for c in diff["notice_changes"]] == ["new", "gone", "grows", "reclass"]


def test_diff_omits_unchanged_codes() -> None:
    same = {"steady": ("WARNING", 4)}
    diff = diff_results([_result("a", "B", 85.0, same)], [_result("a", "B", 85.0, same)])
    assert diff["notice_changes"] == []


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _sample_diff() -> dict[str, Any]:
    return diff_results(
        [
            _result("up", "B", 89.5, {"gone": ("WARNING", 10)}),
            _result("flat", "A", 95.0),
        ],
        [
            _result("up", "A", 90.5, {"new": ("ERROR", 40)}),
            _result("flat", "A", 95.0),
        ],
        skipped=["broken"],
    )


def test_render_report_contents() -> None:
    text = render_report(_sample_diff(), "8.0.1", "8.1.0", as_of=AS_OF)
    assert "# Validator canary: 8.0.1 → 8.1.0" in text
    assert "Shadow run over 2 sampled agencies (2026-07-02)." in text
    assert "- Median score shift: +0.5 points" in text
    assert "- Agencies that changed grade band: 1 of 2" in text
    assert "- Skipped (fetch or validation failed): broken" in text
    # Grade-shift histogram as a text table.
    assert "| Band move | Agencies |" in text
    assert "| 0 | 1 |" in text
    assert "| +1 | 1 |" in text
    # The band-move listing and the notice-code drivers.
    assert "| up | B → A | 89.5 → 90.5 |" in text
    assert "| new | added | – → ERROR | 0 → 40 | 0 → 1 |" in text
    assert "| gone | removed | WARNING → – | 10 → 0 | 1 → 0 |" in text
    # Ready-to-paste METHODOLOGY_CHANGELOG entry.
    assert '"effective_date": "2026-07-02",' in text
    assert (
        "Validator 8.0.1→8.1.0: median score shift +0.5 points, "
        "1 of 2 sampled agencies changed grade band, driven by new." in text
    )


def test_render_report_with_no_differences() -> None:
    same = [_result("a", "B", 85.0, {"steady": ("WARNING", 4)})]
    text = render_report(diff_results(same, same), "8.0.1", "8.1.0", as_of=AS_OF)
    assert "None." in text  # no band moves
    assert "No notice-population differences between the two versions." in text
    assert "Validator 8.0.1→8.1.0: median score unchanged, 0 of 1 sampled agencies" in text


def test_changelog_summary_phrasing() -> None:
    quiet = diff_results([_result("a", "A", 95.0)], [_result("a", "A", 95.0)])
    assert changelog_summary(quiet, "8.0.1", "8.1.0") == (
        "Validator 8.0.1→8.1.0: median score unchanged, 0 of 1 sampled agencies changed grade band."
    )


def test_write_report_emits_markdown_and_json(tmp_path: Path) -> None:
    md_path, json_path = write_report(_sample_diff(), "8.0.1", "8.1.0", tmp_path, as_of=AS_OF)
    assert md_path.name == "validator-canary-8.0.1-vs-8.1.0.md"
    assert json_path.name == "validator-canary-8.0.1-vs-8.1.0.json"
    assert "# Validator canary: 8.0.1 → 8.1.0" in md_path.read_text()
    payload = json.loads(json_path.read_text())
    assert payload["old_version"] == "8.0.1"
    assert payload["new_version"] == "8.1.0"
    assert payload["as_of"] == "2026-07-02"
    assert payload["agencies_compared"] == 2
    assert payload["changelog_summary"].startswith("Validator 8.0.1→8.1.0:")
    assert payload["band_move_histogram"] == {"0": 1, "+1": 1}


# ---------------------------------------------------------------------------
# Shadow scoring (fetch/validate mocked; vcache and scoring are real)
# ---------------------------------------------------------------------------

FEED_FILES = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "demo,Demo Transit,https://demo.example,America/Los_Angeles\n"
    ),
    "feed_info.txt": (
        "feed_publisher_name,feed_publisher_url,feed_lang,feed_contact_email,"
        "feed_start_date,feed_end_date\n"
        "Demo,https://demo.example,en,data@demo.example,20260101,20261001\n"
    ),
    "stops.txt": "stop_id,stop_name,wheelchair_boarding\nS1,Main St & 2nd Ave,1\n",
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\nR1,WK,T1,Downtown,1\n"
    ),
    "fare_attributes.txt": "fare_id,price,currency_type\nbase,2.25,USD\n",
}

AGENCY = Agency(id="demo", name="Demo Transit", static_gtfs_url="https://demo.example/gtfs.zip")


def _fake_fetch(path: Path) -> Callable[..., FetchResult]:
    def fetch(agency: Agency, date: dt.date, force: bool = False) -> FetchResult:
        return FetchResult(
            agency_id=agency.id,
            path=path,
            url=agency.static_gtfs_url,
            fetched_date=date,
            sha256="feedhash",
            size_bytes=1,
            reused=True,
        )

    return fetch


def _fake_run_validator(
    calls: list[str],
) -> Callable[..., Path]:
    """A stand-in Java validator: writes a report.json whose notices depend on
    the version asked for, and records each requested version."""

    def run(
        gtfs_zip: Path,
        output_dir: Path,
        country_code: str = "us",
        version: str = VALIDATOR_VERSION,
    ) -> Path:
        calls.append(version)
        notices = [{"code": "old_code", "severity": "WARNING", "totalNotices": 3}]
        if version != VALIDATOR_VERSION:
            notices = [{"code": "new_code", "severity": "ERROR", "totalNotices": 7}]
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "report.json"
        report.write_text(
            json.dumps({"summary": {"validatorVersion": version}, "notices": notices})
        )
        return report

    return run


def test_shadow_score_agency_scores_both_versions(
    make_gtfs_zip: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = make_gtfs_zip(FEED_FILES)
    calls: list[str] = []
    monkeypatch.setattr(canary, "fetch_static", _fake_fetch(zip_path))
    monkeypatch.setattr(canary, "run_validator", _fake_run_validator(calls))

    baseline, candidate = shadow_score_agency(AGENCY, AS_OF, "8.1.0")

    assert calls == [VALIDATOR_VERSION, "8.1.0"]
    assert baseline["agency_id"] == candidate["agency_id"] == "demo"
    assert baseline["notices"] == {"old_code": {"severity": "WARNING", "total": 3}}
    assert candidate["notices"] == {"new_code": {"severity": "ERROR", "total": 7}}
    # The candidate's ERROR costs more than the baseline's WARNING.
    assert candidate["score"] < baseline["score"]
    # The baseline run is cached for the daily pipeline; the candidate must NOT
    # be, or it would evict the production-version entry.
    assert load_cached("demo", "feedhash", VALIDATOR_VERSION) is not None
    assert load_cached("demo", "feedhash", "8.1.0") is None


def test_shadow_score_agency_baseline_half_reuses_the_cache(
    make_gtfs_zip: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = make_gtfs_zip(FEED_FILES)
    calls: list[str] = []
    monkeypatch.setattr(canary, "fetch_static", _fake_fetch(zip_path))
    monkeypatch.setattr(canary, "run_validator", _fake_run_validator(calls))
    store_cached(
        "demo",
        "feedhash",
        VALIDATOR_VERSION,
        ValidationReport(
            validator_version=VALIDATOR_VERSION,
            notices=[NoticeGroup(code="cached_code", severity="WARNING", total=1)],
        ),
    )

    baseline, _candidate = shadow_score_agency(AGENCY, AS_OF, "8.1.0")

    assert calls == ["8.1.0"]  # only the candidate half paid for a validator run
    assert baseline["notices"] == {"cached_code": {"severity": "WARNING", "total": 1}}


def test_shadow_score_agency_country_scopes_cache_and_raw_reports(
    make_gtfs_zip: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = make_gtfs_zip(FEED_FILES)
    agency = Agency(
        id="demo",
        name="Demo Transit",
        static_gtfs_url="https://demo.example/gtfs.zip",
        country="CA",
    )
    calls: list[tuple[str, str, str]] = []

    def validate(
        _gtfs_zip: Path,
        output_dir: Path,
        country_code: str = "US",
        version: str = VALIDATOR_VERSION,
    ) -> Path:
        calls.append((country_code, version, output_dir.name))
        output_dir.mkdir(parents=True, exist_ok=True)
        report = output_dir / "report.json"
        report.write_text(json.dumps({"summary": {"validatorVersion": version}, "notices": []}))
        return report

    monkeypatch.setattr(canary, "fetch_static", _fake_fetch(zip_path))
    monkeypatch.setattr(canary, "run_validator", validate)

    shadow_score_agency(agency, AS_OF, "8.1.0")

    assert calls == [
        ("CA", VALIDATOR_VERSION, "validator-ca"),
        ("CA", "8.1.0", "validator-canary-8.1.0-ca"),
    ]
    assert load_cached("demo", "feedhash", VALIDATOR_VERSION, country_code="CA") is not None
    assert load_cached("demo", "feedhash", VALIDATOR_VERSION, country_code="US") is None


# ---------------------------------------------------------------------------
# Orchestration + CLI
# ---------------------------------------------------------------------------


def test_run_canary_writes_report_and_tolerates_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agencies = {
        aid: Agency(id=aid, name=aid, static_gtfs_url=f"https://{aid}.example/gtfs.zip")
        for aid in ("alpha", "beta")
    }
    monkeypatch.setattr(canary, "AGENCIES", agencies)

    def fake_shadow(
        agency: Agency, date: dt.date, candidate_version: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if agency.id == "beta":
            raise RuntimeError("origin unreachable")
        return _result(agency.id, "B", 85.0), _result(agency.id, "B", 84.0)

    monkeypatch.setattr(canary, "shadow_score_agency", fake_shadow)

    md_path, json_path = run_canary("8.1.0", date=AS_OF, out_dir=tmp_path / "report")

    payload = json.loads(json_path.read_text())
    assert payload["agencies_compared"] == 1
    assert payload["skipped_agencies"] == ["beta"]  # one bad feed never sinks the run
    assert payload["new_version"] == "8.1.0"
    assert "Skipped (fetch or validation failed): beta" in md_path.read_text()


def test_run_canary_defaults_to_data_canary_dir(
    monkeypatch: pytest.MonkeyPatch, isolated_repo_root: Path
) -> None:
    monkeypatch.setattr(
        canary,
        "AGENCIES",
        {"solo": Agency(id="solo", name="Solo", static_gtfs_url="https://s.example/gtfs.zip")},
    )
    monkeypatch.setattr(
        canary,
        "shadow_score_agency",
        lambda agency, date, version: (_result("solo", "A", 95.0), _result("solo", "A", 95.0)),
    )
    md_path, _json_path = run_canary("8.1.0", date=AS_OF)
    assert md_path.parent == isolated_repo_root / "data" / "canary"


def _write_registry(root: Path) -> None:
    """cli.main() loads agencies.yaml from the (isolated) repo root."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: test-agency\n"
        "    name: Test Agency\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )


def test_cli_canary_parses_args_and_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    isolated_repo_root: Path,
) -> None:
    from scorecard_pipeline import cli

    _write_registry(isolated_repo_root)
    recorded: dict[str, Any] = {}

    def fake_run_canary(candidate_version: str, **kwargs: Any) -> tuple[Path, Path]:
        recorded["candidate_version"] = candidate_version
        recorded.update(kwargs)
        return tmp_path / "r.md", tmp_path / "r.json"

    monkeypatch.setattr(canary, "run_canary", fake_run_canary)
    exit_code = cli.main(
        [
            "canary",
            "--candidate-version",
            "8.1.0",
            "--sample-size",
            "7",
            "--seed",
            "3",
            "--out",
            str(tmp_path / "out"),
            "--date",
            "2026-07-02",
        ]
    )
    assert exit_code == 0
    assert recorded == {
        "candidate_version": "8.1.0",
        "sample_size": 7,
        "seed": 3,
        "date": AS_OF,
        "out_dir": tmp_path / "out",
    }
    out = capsys.readouterr().out
    assert "r.md" in out
    assert "r.json" in out


def test_cli_canary_rejects_the_already_pinned_version(isolated_repo_root: Path) -> None:
    from scorecard_pipeline import cli

    _write_registry(isolated_repo_root)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["canary", "--candidate-version", VALIDATOR_VERSION])
    assert excinfo.value.code == 2
