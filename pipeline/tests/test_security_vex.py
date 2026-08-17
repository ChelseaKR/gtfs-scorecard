"""Keep the time-bounded container CVE exceptions honest and synchronized."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline import validate
from scorecard_pipeline.validate import VALIDATOR_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_validator_vex_matches_trivy_exceptions_and_pin() -> None:
    root = REPOSITORY_ROOT
    vex = json.loads((root / "vex.json").read_text())
    ignored = yaml.safe_load((root / ".trivyignore.yaml").read_text())["vulnerabilities"]

    vex_ids = {item["id"] for item in vex["vulnerabilities"]}
    ignored_ids = {item["id"] for item in ignored}
    assert ignored_ids == vex_ids
    assert vex["metadata"]["component"]["version"] == VALIDATOR_VERSION
    assert all(item["analysis"]["state"] == "not_affected" for item in vex["vulnerabilities"])

    today = dt.date.today()
    expiries = {dt.date.fromisoformat(str(item["expired_at"])) for item in ignored}
    assert min(expiries) > today
    assert max(expiries) <= today + dt.timedelta(days=90)


def test_container_scan_consumes_the_reviewed_ignore_file() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "container-scan.yml").read_text()
    assert "trivyignores: .trivyignore.yaml" in workflow


# The gtfs-validator 8.0.1 CLI flags that make it fetch a feed itself:
# `-u/--url` is the download, and `-s/--storage_directory` is only accepted
# alongside it. Passing any of them is the only way the Apache HttpComponents
# parser and HPACK decoder inside the shaded jar are ever entered (measured;
# see the CVE-2026-54399 entry in vex.json).
VALIDATOR_NETWORK_FLAGS = ("-u", "--url", "-s", "--storage_directory")


def test_validator_is_never_handed_a_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The httpcore5 VEX rests on the validator never fetching anything itself.

    ``run_validator`` is the only place in the package that starts the JVM, so
    if its argv never carries a URL or a URL-fetch flag, the shaded HTTP client
    is unreachable. Adding one to the command breaks this test rather than
    silently invalidating the exception recorded in ``vex.json``.
    """
    jar = tmp_path / "validator.jar"
    jar.write_text("")
    monkeypatch.setattr(validate, "ensure_validator", lambda *a, **k: jar)
    monkeypatch.setattr(validate, "_java_binary", lambda: "java")
    gtfs = tmp_path / "feed.zip"
    gtfs.write_text("")
    out = tmp_path / "out"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    validate.run_validator(gtfs, out, country_code="us", large_feed=True)

    assert len(calls) == 1
    cmd = calls[0]
    assert not any(flag in cmd for flag in VALIDATOR_NETWORK_FLAGS), cmd
    assert not any(arg.startswith(("http://", "https://", "ftp://")) for arg in cmd), cmd
    # The feed reaches the validator as a local file that already exists.
    assert "-i" in cmd
    assert Path(cmd[cmd.index("-i") + 1]).is_file()


def test_httpcore5_exceptions_name_the_measurement_that_backs_them() -> None:
    """A code_not_reachable claim has to cite how it was established."""
    vex = json.loads((REPOSITORY_ROOT / "vex.json").read_text())
    by_id = {item["id"]: item for item in vex["vulnerabilities"]}
    for cve in ("CVE-2026-54399", "CVE-2026-54428"):
        analysis = by_id[cve]["analysis"]
        assert analysis["justification"] == "code_not_reachable"
        assert "org.apache.hc" in analysis["detail"]
    # The claim points at the test that keeps it true, so deleting the test
    # leaves a dangling reference someone has to resolve.
    assert "test_validator_is_never_handed_a_url" in by_id["CVE-2026-54399"]["analysis"]["detail"]
