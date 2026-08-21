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
from .location import normalize_country_code
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


def validator_country_code(country_code: str) -> str:
    """Canonical assigned country code accepted by the validator boundary."""
    country = normalize_country_code(country_code)
    if not country:
        raise ValueError(
            f"validator country must be an assigned ISO 3166-1 alpha-2 code, got {country_code!r}"
        )
    return country


def country_scoped_output_dir(base_dir: Path, country_code: str) -> Path:
    """Country-bind a reusable report directory while preserving the U.S. path.

    Existing U.S. raw reports live at directories such as ``validator`` and
    remain reusable. A non-U.S. run uses ``validator-ca`` (or the corresponding
    country suffix), so changing registry geography cannot pick up a report
    produced with a different validator country.
    """
    country = validator_country_code(country_code)
    if country == "US":
        return base_dir
    return base_dir.with_name(f"{base_dir.name}-{country.lower()}")


# Heap ceiling handed to the JVM for a large-feed validation. A national
# rail-plus-bus or whole-metro feed unzips to hundreds of megabytes of tables
# the validator holds in memory, which can exceed the JVM default max heap on a
# smaller runner. Large feeds get this explicit, bounded ceiling so their memory
# need is a known quantity rather than the runner's implicit default; ordinary
# feeds are untouched. Tunable per environment without a code change.
DEFAULT_LARGE_FEED_HEAP = "6g"


def large_feed_heap() -> str:
    """The -Xmx value for a large-feed validation.

    Caught live dispatching validate-one-feed.yml (issue #297) against
    ovapi-netherlands: a workflow_dispatch input left at its default `""`
    sets the env var present-but-empty, not absent. `os.environ.get(key,
    default)` only falls back to `default` when `key` is missing entirely, so
    that produced `-Xmx` with no value and the JVM refused to start
    ("Invalid maximum heap size: -Xmx") — a different failure than anything
    this env var was meant to cause. Stripped and treated as unset here so
    every caller gets a real heap value regardless of how the empty case is
    spelled.
    """
    return os.environ.get("SCORECARD_LARGE_FEED_HEAP", "").strip() or DEFAULT_LARGE_FEED_HEAP


def _memory_bound_prefix() -> list[str]:
    """Wrap the validator subprocess in a hard virtual-memory ceiling, if configured.

    issue #297: on `ovapi-netherlands` (a `large_feed`), the Actions runner was
    observed dying outright ("received a shutdown signal" / "lost
    communication with the server") 2-4 minutes into validation, on some runs
    but not others under identical settings — the JVM taking the whole runner
    down with it, rather than the validator failing on its own. `-Xmx` alone
    only bounds the JVM heap; it does nothing to stop total process memory
    (heap + metaspace + native/off-heap) from growing enough to starve the
    runner's other processes or trip the platform's own health checks.

    ``SCORECARD_VALIDATOR_MEMORY_MB``, when set, runs the validator under
    ``prlimit --as=<bytes>``: a hard kernel-enforced ceiling on the child
    process's virtual address space (RLIMIT_AS), independent of whatever else
    is running on the same host. An overrun fails the allocating syscall, so
    the JVM exits (no ``report.json`` written) instead of the runner itself
    being killed; the existing ``RuntimeError`` below already treats that as
    an ordinary, catchable validator failure. Unset by default — this is an
    environment-specific ceiling (real Actions-runner memory, not local dev
    memory), so it opts in per workflow rather than always-on. Silently
    unwrapped wherever ``prlimit`` isn't on PATH (e.g. local macOS dev), so
    the same code path runs everywhere without platform special-casing.

    RLIMIT_AS is virtual memory, not resident set size: the JVM reserves
    address space up front for its heap arena, so this ceiling must sit well
    above ``-Xmx`` to leave room for that reservation plus metaspace and
    native memory — it is a coarse backstop against a genuine runaway, not a
    tight RSS budget.
    """
    limit_mb = os.environ.get("SCORECARD_VALIDATOR_MEMORY_MB", "").strip()
    if not limit_mb or not shutil.which("prlimit"):
        return []
    return ["prlimit", f"--as={int(limit_mb) * 1024 * 1024}", "--"]


def run_validator(
    gtfs_zip: Path,
    output_dir: Path,
    country_code: str = "US",
    version: str = VALIDATOR_VERSION,
    *,
    large_feed: bool = False,
) -> Path:
    """Run the validator on a GTFS zip; return the path to report.json.

    ``version`` defaults to the pinned production validator; the canary shadow
    run (canary.py) passes a candidate version to dual-score the same feed.
    ``country_code`` is the feed's assigned ISO 3166-1 alpha-2 country. The
    Java CLI expects its lower-case form; rejecting an unassigned code here
    keeps every caller on the same validator-country contract. ``large_feed``
    gives the JVM an explicit bounded max heap (``large_feed_heap()``) so an
    opted-in large feed validates against a known ceiling instead of the
    runner's default; ordinary feeds keep the default heap.
    """
    country = validator_country_code(country_code)
    jar = ensure_validator(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    heap_flags = [f"-Xmx{large_feed_heap()}"] if large_feed else []
    cmd = [
        *_memory_bound_prefix(),
        _java_binary(),
        *heap_flags,
        "-jar",
        str(jar),
        "-i",
        str(gtfs_zip),
        "-o",
        str(output_dir),
        "-c",
        country.lower(),
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
