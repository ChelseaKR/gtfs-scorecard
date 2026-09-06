"""Wrap the MobilityData gtfs-validator and normalize its JSON report.

The canonical validator already encodes hundreds of GTFS rules; this project
runs it as a subprocess and builds scoring on top of its notices rather than
re-validating GTFS from scratch (see CLAUDE.md, "Data sources").
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import textwrap
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

#: What the refusal says, in one sentence, everywhere it is said.
NO_REPORT_WAS_READ = (
    "this payload is not a gtfs-validator report: it carries no list of notices, "
    "so nothing was read about this feed's correctness and there is nothing to score"
)


class UnreadableValidatorReportError(ValueError):
    """The payload was not a validator report, so correctness was not measured.

    ``ValidationReport`` has one shape for "the validator reported no problems"
    and, until this refusal, the same shape for "there was no report to read":
    an empty ``notices`` list. ``correctness`` starts at 100 and deducts per
    notice, so the second case scored 100.0 and published "The validator found
    no problems in this feed. That is rare and worth celebrating." about a feed
    whose report had never been read. That is the upward twin of the fabricated
    0.0s withdrawn on 2026-09-01 (tests/test_unmeasurable_feed.py), and it is
    the more flattering of the two, which is what makes it harder to notice.

    Three payloads reached that: an empty dict, a dict of the wrong shape
    entirely, and a truncated report that kept its ``summary`` and lost its
    ``notices``. A fourth, ``notices`` present but null, raised TypeError from
    inside a comprehension.

    Refusal, not a zero and not a floor. A report we could not read says nothing
    about the feed in either direction, so no number derived from it may be
    published.

    Subclasses ValueError deliberately, for the reason
    :class:`~scorecard_pipeline.score.UnreadableFeedError` does: a response body
    that is not a zip already raises ValueError out of ``fetch.fetch_static``,
    and every caller that refuses a feed on that basis refuses this one by the
    same path with no new handling. One refusal, several causes, not several
    concepts.
    """


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


def validator_memory_limit_mb() -> str:
    """The configured ``SCORECARD_VALIDATOR_MEMORY_MB``, or ``""`` when unset.

    Read through one accessor so the ceiling that shapes the subprocess and the
    ceiling named in a failure message can never disagree about what was set.
    Empty-string normalization matches ``large_feed_heap()``: a workflow_dispatch
    input left at its default sets the variable present-but-empty, not absent.
    """
    return os.environ.get("SCORECARD_VALIDATOR_MEMORY_MB", "").strip()


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
    limit_mb = validator_memory_limit_mb()
    if not limit_mb or not shutil.which("prlimit"):
        return []
    return ["prlimit", f"--as={int(limit_mb) * 1024 * 1024}", "--"]


# Per-stream ceiling on captured validator output quoted into a failure
# message. A failure has to carry enough to diagnose itself, without giving a
# pathological validator a way to flood the run log; both streams together are
# bounded by twice this.
STREAM_EXCERPT_LIMIT = 8000


def _excerpt(stream: str, limit: int = STREAM_EXCERPT_LIMIT) -> str:
    """One captured stream, quoted for a failure message and truncated audibly.

    Keeps the head and the tail: the head names the cause (a missing Java, a
    heap the VM could not reserve), the tail carries the last frame before the
    exit, and a tail-only slice cut the cause off exactly when it was verbose.
    What was dropped is stated in the message rather than left to the reader to
    infer from a message that stops mid-sentence.
    """
    text = stream.strip("\n")
    if not text.strip():
        return "(empty)"
    if len(text) <= limit:
        return text
    half = limit // 2
    omitted = len(text) - 2 * half
    return (
        f"{text[:half]}\n"
        f"... [{omitted} of {len(text)} characters omitted here; "
        f"head and tail kept] ...\n"
        f"{text[-half:]}"
    )


def _no_report_message(
    result: subprocess.CompletedProcess[str],
    *,
    cmd: list[str],
    gtfs_zip: Path,
    output_dir: Path,
) -> str:
    """Say why the validator produced no report, with enough context to act.

    Both streams are quoted, and that is the point rather than thoroughness for
    its own sake. The JVM splits its startup failures across the two:

    - a malformed flag ("Invalid maximum heap size: -Xmx", issue #297's
      present-but-empty env var) goes to **stderr**;
    - a heap it cannot reserve ("Error occurred during initialization of VM /
      Could not reserve enough space for ... object heap") goes to **stdout**.

    This function's predecessor quoted stderr alone, so the second mode — the
    one an ``SCORECARD_VALIDATOR_MEMORY_MB`` set too close to ``-Xmx`` provokes
    — reported as an exit code followed by a blank line. Observed live in
    validate-one-feed.yml run 33264844507 on 2026-08-29, where the whole
    diagnosis had to be inferred from ``/usr/bin/time`` output instead. Quoting
    only one stream is quoting the wrong one half the time.

    The heap and the ceiling are named because they are the two settings that
    provoke a no-report exit, and RLIMIT_AS is the trap: it bounds virtual
    address space, not resident memory.
    """
    limit_mb = validator_memory_limit_mb()
    if not limit_mb:
        ceiling = "none (SCORECARD_VALIDATOR_MEMORY_MB unset)"
    elif cmd[:1] == ["prlimit"]:
        ceiling = (
            f"{limit_mb} MiB (SCORECARD_VALIDATOR_MEMORY_MB, applied as prlimit --as). "
            "RLIMIT_AS bounds virtual address space, not resident memory: a JVM "
            "reserves considerably more address space than its -Xmx, so a ceiling "
            "set near -Xmx stops the VM initializing at all rather than bounding it"
        )
    else:
        ceiling = f"{limit_mb} MiB requested, but prlimit is not on PATH, so not applied"
    heap = next((arg for arg in cmd if arg.startswith("-Xmx")), "JVM default (no -Xmx passed)")
    return (
        f"gtfs-validator produced no report (exit {result.returncode})\n"
        f"  feed: {gtfs_zip}\n"
        f"  expected report: {output_dir / 'report.json'}\n"
        f"  heap: {heap}\n"
        f"  address-space ceiling: {ceiling}\n"
        f"  command: {shlex.join(cmd)}\n"
        f"  stdout:\n{textwrap.indent(_excerpt(result.stdout or ''), '    ')}\n"
        f"  stderr:\n{textwrap.indent(_excerpt(result.stderr or ''), '    ')}"
    )


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
        raise RuntimeError(
            _no_report_message(result, cmd=cmd, gtfs_zip=gtfs_zip, output_dir=output_dir)
        )
    return report


def parse_report_data(data: dict[str, Any]) -> ValidationReport:
    """Normalize a parsed gtfs-validator report (its report.json structure).

    Split out from ``parse_report`` so any source of the same report JSON parses
    identically: a local run, or MobilityData's hosted report for a dataset it
    already validated (feedapi.py). The schema is the validator's own, so the
    field names match whichever produced it.

    Raises :class:`UnreadableValidatorReportError` when the payload is not a
    report. Every gtfs-validator report carries ``notices`` as a list, empty
    when the feed is clean, so the list's presence is what separates "the
    validator found nothing wrong" from "there was nothing to read". Without
    that separation both produced an empty ``ValidationReport``, and correctness
    scored the second one 100.0.
    """
    notices = data.get("notices") if isinstance(data, dict) else None
    if not isinstance(notices, list):
        raise UnreadableValidatorReportError(NO_REPORT_WAS_READ)
    version = str(data.get("summary", {}).get("validatorVersion", "unknown"))
    groups: list[NoticeGroup] = []
    for notice in notices:
        # Skipping a malformed entry would quietly lower the notice count, which
        # raises the score: the same fabrication one notice at a time.
        if not isinstance(notice, dict):
            raise UnreadableValidatorReportError(NO_REPORT_WAS_READ)
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
