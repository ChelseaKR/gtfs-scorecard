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


def test_run_validator_heap_falls_back_when_env_is_present_but_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression for issue #297's live validate-one-feed.yml dispatch: a
    workflow_dispatch input left blank sets the env var to "", not absent.
    os.environ.get(key, default) only falls back on a missing key, so this
    previously produced a bare "-Xmx" and the JVM refused to start."""
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    monkeypatch.setenv("SCORECARD_LARGE_FEED_HEAP", "")
    validate.run_validator(gtfs, out, large_feed=True)
    assert calls[0][1] == f"-Xmx{validate.DEFAULT_LARGE_FEED_HEAP}"


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


def test_memory_bound_prefix_absent_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCORECARD_VALIDATOR_MEMORY_MB", raising=False)
    assert validate._memory_bound_prefix() == []


def test_memory_bound_prefix_absent_when_prlimit_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configured, but the tool isn't on this machine (e.g. local macOS dev):
    # unwrapped, not a hard failure, so the same code path runs everywhere.
    monkeypatch.setenv("SCORECARD_VALIDATOR_MEMORY_MB", "10240")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert validate._memory_bound_prefix() == []


def test_memory_bound_prefix_wraps_with_prlimit_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_VALIDATOR_MEMORY_MB", "10240")
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "prlimit" else None
    )
    assert validate._memory_bound_prefix() == ["prlimit", "--as=10737418240", "--"]


def test_run_validator_unwrapped_without_memory_limit_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    monkeypatch.delenv("SCORECARD_VALIDATOR_MEMORY_MB", raising=False)
    validate.run_validator(gtfs, out)
    assert calls[0][0] == "java"


def test_run_validator_wraps_java_with_prlimit_when_memory_limit_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"
    calls = _capture_cmd(monkeypatch, out)
    monkeypatch.setenv("SCORECARD_VALIDATOR_MEMORY_MB", "8192")
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "prlimit" else None
    )
    validate.run_validator(gtfs, out, large_feed=True)
    # prlimit wraps the whole invocation ahead of the java binary and its
    # own flags; the heap flag is still where the pre-existing tests expect
    # it, just shifted past the wrapper.
    assert calls[0][:3] == ["prlimit", "--as=8589934592", "--"]
    assert calls[0][3] == "java"
    assert calls[0][4] == f"-Xmx{validate.DEFAULT_LARGE_FEED_HEAP}"


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


def _failing_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 1,
) -> tuple[Path, Path]:
    """A validator subprocess that exits without writing report.json."""
    gtfs = _stub_runner(monkeypatch, tmp_path)
    out = tmp_path / "out"

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        out.mkdir(parents=True, exist_ok=True)  # but never writes report.json
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return gtfs, out


def test_run_validator_failure_quotes_stdout_not_only_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression for validate-one-feed.yml run 33264844507 (2026-08-29).

    A JVM that cannot reserve its heap writes "Error occurred during
    initialization of VM" to *stdout* and leaves stderr empty, then exits 1.
    The failure message quoted stderr alone, so the run log read
    "produced no report (exit 1):" followed by a blank line, and the cause had
    to be inferred from `/usr/bin/time` output instead. Verified against a real
    JVM: `java -Xmx900000g -version` puts that text on stdout, while a
    malformed `-Xmx` puts its own error on stderr. Quoting one stream is
    quoting the wrong one half the time.
    """
    gtfs, out = _failing_run(
        monkeypatch,
        tmp_path,
        stdout=(
            "Error occurred during initialization of VM\n"
            "Could not reserve enough space for 4194304KB object heap"
        ),
        stderr="",
    )
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out, large_feed=True)
    message = str(excinfo.value)
    assert "Could not reserve enough space for 4194304KB object heap" in message
    assert "Error occurred during initialization of VM" in message
    # The empty stream is named as empty rather than rendered as a blank gap,
    # so a reader can tell "the validator said nothing" from "we dropped it".
    assert "stderr:" in message
    assert "(empty)" in message


def test_run_validator_failure_names_the_context_needed_to_act(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exit code, feed, heap and ceiling: the settings that provoke this exit."""
    monkeypatch.setenv("SCORECARD_LARGE_FEED_HEAP", "4g")
    monkeypatch.setenv("SCORECARD_VALIDATOR_MEMORY_MB", "6144")
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "prlimit" else None
    )
    gtfs, out = _failing_run(monkeypatch, tmp_path, stdout="nope", returncode=1)
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out, large_feed=True)
    message = str(excinfo.value)
    assert "exit 1" in message
    # Each assertion pins its own labelled line. Bare substrings would also
    # match the reproduced command below and so would pass with the context
    # block deleted, which is a test that cannot fail.
    assert f"feed: {gtfs}" in message
    assert "heap: -Xmx4g" in message
    assert "address-space ceiling: 6144 MiB" in message
    # The command is reproducible by hand from the message alone.
    assert "prlimit --as=6442450944 --" in message


def test_run_validator_failure_names_the_address_space_trap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RLIMIT_AS bounds virtual address space, not RSS.

    A ceiling set near -Xmx stops the VM initializing rather than bounding a
    runaway, which is exactly the trap run 33264844507 fell into. The message
    says so at the moment an operator is reading it.
    """
    monkeypatch.setenv("SCORECARD_VALIDATOR_MEMORY_MB", "6144")
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "prlimit" else None
    )
    gtfs, out = _failing_run(monkeypatch, tmp_path, stdout="nope")
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out, large_feed=True)
    message = str(excinfo.value)
    assert "virtual address space, not resident memory" in message


def test_run_validator_failure_reports_an_unset_ceiling_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SCORECARD_VALIDATOR_MEMORY_MB", raising=False)
    gtfs, out = _failing_run(monkeypatch, tmp_path, stderr="plain failure")
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out)
    message = str(excinfo.value)
    assert "SCORECARD_VALIDATOR_MEMORY_MB unset" in message
    assert "JVM default (no -Xmx passed)" in message


def test_run_validator_failure_truncates_a_flooding_stream_and_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pathological validator cannot flood the run log, and the cut is stated.

    Head and tail are both kept: the head names the cause, the tail carries the
    last frame before the exit.
    """
    flood = "HEAD-MARKER\n" + ("x" * 200_000) + "\nTAIL-MARKER"
    gtfs, out = _failing_run(monkeypatch, tmp_path, stdout=flood)
    with pytest.raises(RuntimeError) as excinfo:
        validate.run_validator(gtfs, out)
    message = str(excinfo.value)
    assert "HEAD-MARKER" in message
    assert "TAIL-MARKER" in message
    assert "characters omitted here" in message
    # Bounded: both streams together stay within twice the per-stream ceiling,
    # plus the small fixed context block.
    assert len(message) < 2 * validate.STREAM_EXCERPT_LIMIT + 2000
    assert len(message) < len(flood)


def test_excerpt_keeps_short_output_verbatim_and_names_an_empty_stream() -> None:
    assert validate._excerpt("short and whole") == "short and whole"
    assert validate._excerpt("") == "(empty)"
    assert validate._excerpt("   \n  ") == "(empty)"
    # Exactly at the ceiling is still verbatim; one past it truncates.
    assert validate._excerpt("y" * 40, limit=40) == "y" * 40
    assert "omitted here" in validate._excerpt("y" * 41, limit=40)
