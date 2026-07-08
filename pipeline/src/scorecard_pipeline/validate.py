"""Wrap the MobilityData gtfs-validator and normalize its JSON report.

The canonical validator already encodes hundreds of GTFS rules; this project
runs it as a subprocess and builds scoring on top of its notices rather than
re-validating GTFS from scratch (see CLAUDE.md, "Data sources").
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import cache_dir
from .fetch import USER_AGENT
from .net import safe_get

log = logging.getLogger(__name__)

VALIDATOR_VERSION = "8.0.1"
VALIDATOR_JAR_URL = (
    "https://github.com/MobilityData/gtfs-validator/releases/download/"
    "v{version}/gtfs-validator-{version}-cli.jar"
)

SEVERITIES = ("ERROR", "WARNING", "INFO")


@dataclass(frozen=True)
class NoticeGroup:
    """All occurrences of one validator notice code in a feed."""

    code: str
    severity: str
    total: int
    sample_notices: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationReport:
    """Normalized findings from one gtfs-validator run."""

    validator_version: str
    notices: list[NoticeGroup]

    def count_by_severity(self) -> dict[str, int]:
        """Total notice instances per severity level."""
        counts = dict.fromkeys(SEVERITIES, 0)
        for group in self.notices:
            counts[group.severity] = counts.get(group.severity, 0) + group.total
        return counts


def _java_binary() -> str:
    """The validator needs Java 17+; prefer an explicit override, then PATH."""
    override = os.environ.get("SCORECARD_JAVA")
    if override:
        return override
    for candidate in ("/opt/homebrew/opt/openjdk/bin/java", shutil.which("java") or ""):
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No java binary found; set SCORECARD_JAVA")


def ensure_validator(version: str = VALIDATOR_VERSION) -> Path:
    """Download the validator CLI jar into the cache if not already present."""
    jar = cache_dir() / f"gtfs-validator-{version}-cli.jar"
    if jar.exists():
        return jar
    jar.parent.mkdir(parents=True, exist_ok=True)
    url = VALIDATOR_JAR_URL.format(version=version)
    log.info("downloading gtfs-validator %s", version)
    body = safe_get(url, headers={"User-Agent": USER_AGENT}, timeout=300)
    tmp = jar.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(jar)
    return jar


def run_validator(
    gtfs_zip: Path,
    output_dir: Path,
    country_code: str = "us",
    version: str = VALIDATOR_VERSION,
) -> Path:
    """Run the validator on a GTFS zip; return the path to report.json.

    ``version`` defaults to the pinned production validator; the canary shadow
    run (canary.py) passes a candidate version to dual-score the same feed.
    """
    jar = ensure_validator(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        _java_binary(),
        "-jar",
        str(jar),
        "-i",
        str(gtfs_zip),
        "-o",
        str(output_dir),
        "-c",
        country_code,
    ]
    log.info("running gtfs-validator on %s", gtfs_zip)
    # Reasoning for the S603 suppression below: argv list (no shell=True), every
    # element is an internally constructed path/flag or the validated country_code
    # — never shell-interpreted, so this is not an injection vector despite the
    # blanket bandit audit rule.
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)  # noqa: S603
    report = output_dir / "report.json"
    # The validator exits non-zero in some error-notice situations; the report
    # existing is the real success signal.
    if not report.exists():
        # Keep the head and the tail of stderr: the head names the cause (a
        # missing Java, an OOM), the tail carries the final stack frame; a
        # tail-only slice cut the cause off exactly when it was verbose.
        stderr = result.stderr or ""
        if len(stderr) > 12000:
            stderr = stderr[:6000] + "\n... [stderr truncated] ...\n" + stderr[-6000:]
        raise RuntimeError(
            f"gtfs-validator produced no report (exit {result.returncode}):\n{stderr}"
        )
    return report


def parse_report_data(data: dict[str, Any]) -> ValidationReport:
    """Normalize a parsed gtfs-validator report (its report.json structure).

    Split out from ``parse_report`` so any source of the same report JSON parses
    identically: a local run, or MobilityData's hosted report for a dataset it
    already validated (feedapi.py). The schema is the validator's own, so the
    field names match whichever produced it.
    """
    version = str(data.get("summary", {}).get("validatorVersion", "unknown"))
    groups: list[NoticeGroup] = []
    for notice in data.get("notices", []):
        severity = str(notice.get("severity", "INFO")).upper()
        groups.append(
            NoticeGroup(
                code=str(notice.get("code", "unknown")),
                severity=severity if severity in SEVERITIES else "INFO",
                total=int(notice.get("totalNotices", len(notice.get("sampleNotices", [])))),
                sample_notices=list(notice.get("sampleNotices", []))[:5],
            )
        )
    groups.sort(key=lambda g: (SEVERITIES.index(g.severity), -g.total))
    return ValidationReport(validator_version=version, notices=groups)


def parse_report(report_path: Path) -> ValidationReport:
    """Parse a gtfs-validator report.json into the normalized findings model."""
    return parse_report_data(json.loads(report_path.read_text()))
