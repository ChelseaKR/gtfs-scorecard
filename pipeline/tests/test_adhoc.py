"""The ad-hoc `scorecard try` path: score any feed without publishing it.

run_adhoc reuses the same fetch -> validate -> score chain as a tracked agency
but writes nothing to the public artifacts or index. These tests stub the
network and the Java validator so they run offline, and assert the artifact is
produced without touching artifacts_dir().
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scorecard_pipeline import cli
from scorecard_pipeline.config import Agency, artifacts_dir
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"


def _stub_fetch(monkeypatch: object) -> None:
    fr = FetchResult(
        agency_id="_adhoc",
        path=FIXTURE,
        url="https://example.test/gtfs.zip",
        fetched_date=dt.date(2026, 6, 11),
        sha256="ab" * 32,
        size_bytes=FIXTURE.stat().st_size,
        reused=False,
    )
    report = ValidationReport(
        validator_version="9.9.9",
        notices=[NoticeGroup(code="route_short_name_too_long", severity="WARNING", total=2)],
    )
    monkeypatch.setattr(cli, "fetch_static", lambda *a, **k: fr)  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: Path("unused.json"))  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "parse_report", lambda *a, **k: report)  # type: ignore[attr-defined]


def test_run_adhoc_scores_without_publishing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_fetch(monkeypatch)
    artifact = cli.run_adhoc("https://example.test/gtfs.zip", "Test Agency", dt.date(2026, 6, 11))

    assert artifact["agency"]["name"] == "Test Agency"
    assert artifact["agency"]["id"] == "_adhoc"
    assert artifact["overall"]["grade"] in {"A", "B", "C", "D", "F"}
    # realtime is never sampled for an ad-hoc URL
    assert artifact["categories"]["realtime"]["status"] != "measured"
    # nothing was published to the public artifacts tree
    assert not (artifacts_dir() / "_adhoc").exists()


def test_run_adhoc_defaults_name_to_host(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_fetch(monkeypatch)
    artifact = cli.run_adhoc("https://transit.example.org/feed.zip", None, dt.date(2026, 6, 11))
    assert artifact["agency"]["name"] == "transit.example.org"


def test_run_adhoc_scores_local_corrected_copy(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    local = tmp_path / "corrected.zip"
    local.write_bytes(FIXTURE.read_bytes())
    scratch = tmp_path / "raw"
    report = ValidationReport(validator_version="9.9.9", notices=[])

    monkeypatch.setattr(cli, "raw_dir", lambda: scratch)
    monkeypatch.setattr(
        cli,
        "fetch_static",
        lambda *_args, **_kwargs: pytest.fail("local input must not use the network fetcher"),
    )
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: Path("unused.json"))
    monkeypatch.setattr(cli, "parse_report", lambda *a, **k: report)

    artifact = cli.run_adhoc(str(local), None, dt.date(2026, 7, 18))

    assert artifact["agency"]["name"] == "corrected"
    assert artifact["feed"]["static_url"] == local.resolve().as_uri()
    assert artifact["fetch"]["source"] == "local"
    assert "local feed copy" in " ".join(artifact["confidence"]["notes"])
    assert artifact["overall"]["grade"] in {"A", "B", "C", "D", "F"}
    assert not (artifacts_dir() / "_adhoc").exists()


def test_run_adhoc_rejects_missing_local_path() -> None:
    with pytest.raises(FileNotFoundError, match="local GTFS zip not found"):
        cli.run_adhoc("missing-feed.zip", None, dt.date(2026, 7, 18))


def test_run_adhoc_isolates_parallel_work_by_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_fetch(monkeypatch)
    scratch_ids: list[str] = []
    report_dirs: list[Path] = []
    fr = FetchResult(
        agency_id="_adhoc",
        path=FIXTURE,
        url="https://example.test/gtfs.zip",
        fetched_date=dt.date(2026, 6, 11),
        sha256="ab" * 32,
        size_bytes=FIXTURE.stat().st_size,
        reused=False,
    )

    def fetch(agency: Agency, *_args: object, **_kwargs: object) -> FetchResult:
        scratch_ids.append(agency.id)
        return fr

    def validate(_feed: Path, output_dir: Path, *, country_code: str = "US") -> Path:
        report_dirs.append(output_dir)
        return Path("unused.json")

    monkeypatch.setattr(cli, "fetch_static", fetch)
    monkeypatch.setattr(cli, "run_validator", validate)
    first = cli.run_adhoc("https://one.example/feed.zip", "One", dt.date(2026, 6, 11))
    second = cli.run_adhoc("https://two.example/feed.zip", "Two", dt.date(2026, 6, 11))

    assert scratch_ids[0] != scratch_ids[1]
    assert all(value.startswith("_adhoc-") for value in scratch_ids)
    assert report_dirs[0] != report_dirs[1]
    assert first["agency"]["id"] == second["agency"]["id"] == "_adhoc"


def test_run_adhoc_passes_country_to_validator_and_artifact(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_fetch(monkeypatch)
    countries: list[str] = []

    def validate(
        _feed: Path,
        _output_dir: Path,
        *,
        country_code: str = "US",
    ) -> Path:
        countries.append(country_code)
        return Path("unused.json")

    monkeypatch.setattr(cli, "run_validator", validate)
    artifact = cli.run_adhoc(
        "https://example.test/gtfs.zip",
        "Canadian Example",
        dt.date(2026, 6, 11),
        country="ca",
    )

    assert countries == ["CA"]
    assert artifact["agency"]["country"] == "CA"


def test_run_adhoc_country_is_part_of_scratch_identity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _stub_fetch(monkeypatch)
    scratch_ids: list[str] = []

    def fetch(agency: Agency, *_args: object, **_kwargs: object) -> FetchResult:
        scratch_ids.append(agency.id)
        return FetchResult(
            agency_id=agency.id,
            path=FIXTURE,
            url="https://example.test/gtfs.zip",
            fetched_date=dt.date(2026, 6, 11),
            sha256="ab" * 32,
            size_bytes=FIXTURE.stat().st_size,
            reused=False,
        )

    monkeypatch.setattr(cli, "fetch_static", fetch)
    cli.run_adhoc("https://example.test/gtfs.zip", None, dt.date(2026, 6, 11), country="US")
    cli.run_adhoc("https://example.test/gtfs.zip", None, dt.date(2026, 6, 11), country="CA")

    assert scratch_ids[0] != scratch_ids[1]


def test_try_cli_normalizes_assigned_country(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def command(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
        seen.append(str(args.country))
        return 0

    monkeypatch.setattr(cli, "_cmd_try", command)
    assert cli.main(["try", "https://example.test/gtfs.zip", "--country", "ca"]) == 0
    assert seen == ["CA"]


def test_try_cli_rejects_unassigned_country() -> None:
    with pytest.raises(SystemExit):
        cli.main(["try", "https://example.test/gtfs.zip", "--country", "ZZ"])


def test_print_summary_includes_grade_and_fixes() -> None:
    artifact = {
        "agency": {"name": "Demo Transit"},
        "feed": {"static_url": "https://demo.test/gtfs.zip"},
        "overall": {"grade": "B", "score": 84.2},
        "categories": {
            "correctness": {"status": "measured", "score": 88.0},
            "freshness": {"status": "measured", "score": 75.0},
            "completeness": {"status": "measured", "score": 90.0},
            "realtime": {"status": "not_yet_measured"},
        },
        "top_fixes": [
            {"fix": "Re-export with a longer calendar window.", "effort": "One setting."}
        ],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli._print_scorecard_summary(artifact)
    out = buf.getvalue()
    assert "Demo Transit" in out
    assert "Overall grade: B" in out
    assert "Rider experience" in out  # completeness relabeled
    assert "not yet measured" in out  # realtime
    assert "Re-export with a longer calendar window." in out
