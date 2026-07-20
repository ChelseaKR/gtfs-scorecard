"""Tests for parsing the gtfs-validator JSON report and the runner glue."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scorecard_pipeline import validate
from scorecard_pipeline.config import cache_dir
from scorecard_pipeline.validate import parse_report

SAMPLE_REPORT = {
    "summary": {"validatorVersion": "8.0.1", "gtfsInput": "gtfs.zip"},
    "notices": [
        {
            "code": "unused_stop",
            "severity": "WARNING",
            "totalNotices": 12,
            "sampleNotices": [{"stopId": f"S{i}"} for i in range(10)],
        },
        {
            "code": "unusable_trip",
            "severity": "ERROR",
            "totalNotices": 2,
            "sampleNotices": [{"tripId": "T1"}, {"tripId": "T2"}],
        },
        {
            "code": "unknown_file",
            "severity": "INFO",
            "totalNotices": 1,
            "sampleNotices": [{"filename": "extra.txt"}],
        },
    ],
}


def write_report(tmp_path: Path, payload: dict) -> Path:  # type: ignore[type-arg]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload))
    return path


def test_parses_and_sorts_by_severity(tmp_path: Path) -> None:
    report = parse_report(write_report(tmp_path, SAMPLE_REPORT))
    assert report.validator_version == "8.0.1"
    assert [g.code for g in report.notices] == ["unusable_trip", "unused_stop", "unknown_file"]
    assert report.count_by_severity() == {"ERROR": 2, "WARNING": 12, "INFO": 1}


def test_sample_notices_capped_at_five(tmp_path: Path) -> None:
    report = parse_report(write_report(tmp_path, SAMPLE_REPORT))
    unused = next(g for g in report.notices if g.code == "unused_stop")
    assert len(unused.sample_notices) == 5
    assert unused.total == 12


def test_empty_report(tmp_path: Path) -> None:
    report = parse_report(write_report(tmp_path, {"summary": {}, "notices": []}))
    assert report.notices == []
    assert report.count_by_severity() == {"ERROR": 0, "WARNING": 0, "INFO": 0}


def test_unknown_severity_downgraded_to_info(tmp_path: Path) -> None:
    payload = {
        "summary": {},
        "notices": [{"code": "weird", "severity": "CRITICAL", "totalNotices": 1}],
    }
    report = parse_report(write_report(tmp_path, payload))
    assert report.notices[0].severity == "INFO"


def test_total_falls_back_to_sample_length_when_total_missing(tmp_path: Path) -> None:
    # Some report variants omit totalNotices; the count must still reflect the
    # samples present rather than defaulting to zero (which would hide the issue).
    payload = {
        "summary": {},
        "notices": [
            {"code": "x", "severity": "WARNING", "sampleNotices": [{"a": 1}, {"a": 2}, {"a": 3}]}
        ],
    }
    report = parse_report(write_report(tmp_path, payload))
    assert report.notices[0].total == 3


# --------------------------------------------------------------- runner glue


def test_java_binary_prefers_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORECARD_JAVA", "/opt/custom/java")
    assert validate._java_binary() == "/opt/custom/java"


def test_java_binary_falls_back_to_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    java = tmp_path / "java"
    java.write_text("")
    monkeypatch.setenv("SCORECARD_JAVA", "")
    monkeypatch.setattr(shutil, "which", lambda _name: str(java))
    # The hardcoded Homebrew candidate is checked first; force it absent so the
    # PATH-resolved binary is the one selected.
    homebrew = "/opt/homebrew/opt/openjdk/bin/java"
    monkeypatch.setattr(Path, "exists", lambda self: str(self) != homebrew)
    assert validate._java_binary() == str(java)


def test_java_binary_raises_when_no_java(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORECARD_JAVA", "")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    with pytest.raises(FileNotFoundError):
        validate._java_binary()


def test_ensure_validator_reuses_cached_jar(
    monkeypatch: pytest.MonkeyPatch, isolated_repo_root: Path
) -> None:
    jar = cache_dir() / "gtfs-validator-9.9.9-cli.jar"
    jar.parent.mkdir(parents=True, exist_ok=True)
    jar.write_bytes(b"cached")

    def explode(*_a: object, **_k: object) -> bytes:
        raise AssertionError("must not download when the jar is already cached")

    monkeypatch.setattr(validate, "safe_get", explode)
    assert validate.ensure_validator("9.9.9") == jar


def test_ensure_validator_downloads_when_missing(
    monkeypatch: pytest.MonkeyPatch, isolated_repo_root: Path
) -> None:
    monkeypatch.setattr(validate, "safe_get", lambda *_a, **_k: b"JARBYTES")
    jar = validate.ensure_validator("9.9.9")
    assert jar.exists()
    assert jar.read_bytes() == b"JARBYTES"
    # The temp .part file is renamed into place, not left behind.
    assert not jar.with_suffix(".part").exists()


def _stub_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    jar = tmp_path / "validator.jar"
    jar.write_text("")
    monkeypatch.setattr(validate, "ensure_validator", lambda *a, **k: jar)
    monkeypatch.setattr(validate, "_java_binary", lambda: "java")
    gtfs = tmp_path / "g.zip"
    gtfs.write_text("")
    return gtfs


def test_run_validator_returns_report_even_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text("{}")
        # The validator exits non-zero when it finds error notices; a written
        # report is the real success signal, so this must NOT raise.
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="found errors")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert validate.run_validator(gtfs, out) == out / "report.json"


def test_run_validator_passes_normalized_country_to_java(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    validate.run_validator(gtfs, out, country_code=" ca ")

    assert calls[0][-2:] == ["-c", "ca"]


def test_run_validator_rejects_unassigned_country(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="assigned ISO 3166-1 alpha-2"):
        validate.run_validator(gtfs, tmp_path / "out", country_code="ZZ")


def _capture_cmd(monkeypatch: pytest.MonkeyPatch, out: Path) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_run_validator_gives_a_large_feed_an_explicit_heap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    monkeypatch.delenv("SCORECARD_LARGE_FEED_HEAP", raising=False)
    validate.run_validator(gtfs, out, large_feed=True)
    # The heap flag sits right after the java binary, before -jar.
    assert calls[0][1] == f"-Xmx{validate.DEFAULT_LARGE_FEED_HEAP}"
    assert calls[0][2] == "-jar"


def test_run_validator_heap_is_tunable_by_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    monkeypatch.setenv("SCORECARD_LARGE_FEED_HEAP", "10g")
    validate.run_validator(gtfs, out, large_feed=True)
    assert calls[0][1] == "-Xmx10g"


def test_run_validator_standard_feed_has_no_heap_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    validate.run_validator(gtfs, out)
    # An ordinary feed keeps the runner's default heap; no -Xmx is injected.
    assert not any(arg.startswith("-Xmx") for arg in calls[0])
    assert calls[0][1] == "-jar"


def test_country_scoped_output_dir_preserves_us_and_isolates_other_countries(
    tmp_path: Path,
) -> None:
    base = tmp_path / "validator"
    assert validate.country_scoped_output_dir(base, "US") == base
    assert validate.country_scoped_output_dir(base, "ca") == tmp_path / "validator-ca"
    assert validate.country_scoped_output_dir(base, "GB") == tmp_path / "validator-gb"


def test_run_validator_raises_when_no_report_produced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        out.mkdir(parents=True, exist_ok=True)  # but never writes report.json
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="boom on startup")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out)
    assert "exit 2" in str(excinfo.value)
    assert "boom on startup" in str(excinfo.value)
