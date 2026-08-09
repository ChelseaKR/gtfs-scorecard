"""Vendor view: expiry status aggregated by the host that serves each feed.

The finding a statewide program acts on is rarely about one agency. When most
of the stale feeds in a cohort sit behind a single hosting vendor, the fix is
one upstream conversation, not dozens of agency calls. This rolls the freshness
status up by feed host so that pattern is visible.

This is an operator's view, printed for whoever supports the agencies. It is
deliberately not rendered into the public site: it points at where to spend
support time, and must never read as a vendor leaderboard or a public ranking.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any
from urllib.parse import urlparse

from .config import artifacts_dir, current_agency_ids
from .metrics import expiry_status

# A host needs at least this many agencies before its quality numbers carry as a
# benchmark. One agency behind a host describes that agency, not the export tool.
MIN_AGENCIES_FOR_BENCHMARK = 2


def _feed_host(url: str) -> str:
    """The bare host that serves a feed, lowercased, without a leading www. or a
    port. This stands in for the vendor: shared services (Trillium, an S3
    bucket) put many small agencies behind one host."""
    netloc = urlparse(url).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    return netloc.removeprefix("www.") or "unknown"


@dataclass
class VendorStat:
    """Freshness counts for all feeds served by one host."""

    host: str
    total: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    stale_agencies: list[str] = field(default_factory=list)

    @property
    def expired(self) -> int:
        return self.counts["lapsed"] + self.counts["stale"]


def _load_latest(agency_id: str) -> dict[str, Any] | None:
    path = artifacts_dir() / agency_id / "latest.json"
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        return None


def vendor_breakdown(agency_ids: list[str] | None = None) -> list[VendorStat]:
    """Aggregate each feed's expiry status by its host.

    Reads `latest.json` for the given agencies (or every agency with artifacts).
    Hosts are sorted worst-first: most long-stale feeds, then most expired
    overall, then largest, so the line worth acting on sits at the top.
    """
    root = artifacts_dir()
    if agency_ids is None:
        if not root.exists():
            return []
        agency_ids = current_agency_ids(
            sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "latest.json").exists())
        )
    else:
        # A named program can retain a retired id in old configuration. Current
        # operator reports still use the active-canonical registry boundary.
        agency_ids = current_agency_ids(agency_ids)

    by_host: dict[str, VendorStat] = {}
    for agency_id in agency_ids:
        latest = _load_latest(agency_id)
        if not latest:
            continue
        host = _feed_host(latest.get("feed", {}).get("static_url", ""))
        days = (
            latest.get("categories", {})
            .get("freshness", {})
            .get("details", {})
            .get("days_until_expiry")
        )
        status = expiry_status(days)
        stat = by_host.setdefault(host, VendorStat(host=host))
        stat.total += 1
        stat.counts[status] += 1
        if status == "stale":
            stat.stale_agencies.append(latest.get("agency", {}).get("name", host))

    return sorted(
        by_host.values(),
        key=lambda s: (s.counts["stale"], s.expired, s.total),
        reverse=True,
    )


def render_vendor_report(stats: list[VendorStat]) -> str:
    """A plain-text operator report: the headline pattern, then a per-host table.

    Framed as where to spend support time. No ranking language, no scores; just
    where the stale feeds cluster.
    """
    lines = ["Feed freshness by host (operator view)", ""]
    total_stale = sum(s.counts["stale"] for s in stats)
    total_feeds = sum(s.total for s in stats)
    if total_stale and stats and stats[0].counts["stale"]:
        top = stats[0]
        lines.append(
            f"{top.host} accounts for {top.counts['stale']} of {total_stale} feeds that have "
            f"been expired over a year. One conversation upstream there would clear the most."
        )
        lines.append("")

    header = f"{'host':<34} {'feeds':>5} {'current':>7} {'soon':>5} {'lapsed':>6} {'stale':>5}"
    lines.append(header)
    lines.append("-" * len(header))
    for s in stats:
        lines.append(
            f"{s.host[:34]:<34} {s.total:>5} {s.counts['current']:>7} "
            f"{s.counts['expiring_soon']:>5} {s.counts['lapsed']:>6} {s.counts['stale']:>5}"
        )
    lines.append("")
    lines.append(f"{len(stats)} hosts, {total_feeds} feeds, {total_stale} long-stale.")
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class VendorQuality:
    """Quality summary for all feeds served by one host.

    The host stands in for the export tool or hosting vendor: many small
    agencies sit behind one shared service, and feed quality traces back to how
    that tool writes GTFS. Comparing hosts shows where a producing tool, not an
    individual agency, sets the ceiling on quality.
    """

    host: str
    agency_count: int
    avg_score: float
    grade_distribution: dict[str, int]
    median_score: float


def vendor_quality(records: list[dict[str, Any]]) -> list[VendorQuality]:
    """Group already-loaded agency records by feed host and summarize quality.

    Each record is a plain dict carrying at least `feed_url`, `grade`, and
    `score`. Records are grouped by `_feed_host(feed_url)`. Only hosts serving
    `MIN_AGENCIES_FOR_BENCHMARK` or more agencies are returned: a single-agency
    host is not a benchmark, just one data point.

    The result is sorted by agency count descending, then host name, so the
    hosts with the most evidence behind them come first. This function reads no
    disk; pass the records in so it stays a unit under test.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        host = _feed_host(record.get("feed_url", ""))
        grouped.setdefault(host, []).append(record)

    summaries: list[VendorQuality] = []
    for host, group in grouped.items():
        if len(group) < MIN_AGENCIES_FOR_BENCHMARK:
            continue
        scores = [float(r.get("score", 0.0)) for r in group]
        distribution: Counter[str] = Counter(str(r.get("grade", "")) for r in group)
        summaries.append(
            VendorQuality(
                host=host,
                agency_count=len(group),
                avg_score=round(mean(scores), 1),
                grade_distribution=dict(distribution),
                median_score=round(median(scores), 1),
            )
        )

    return sorted(summaries, key=lambda v: (-v.agency_count, v.host))


def render_vendor_report_markdown(
    stats: list[VendorStat],
    min_agencies: int = MIN_AGENCIES_FOR_BENCHMARK,
) -> str:
    """Markdown operator report for GitHub Actions step summaries.

    Filters to hosts with at least min_agencies feeds so one-off custom URLs
    do not clutter the table. Framed as where to spend support time, not as a
    ranking. Must not be published to the public site.
    """
    qualified = [s for s in stats if s.total >= min_agencies]
    lines: list[str] = []
    if not qualified:
        lines.append("No feed host has enough agencies to report yet.")
        lines.append("")
        lines.append("_Internal support tool — not for public distribution._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Host | Agencies | Expired | Stale | Example agencies |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for s in qualified:
        examples = ", ".join(s.stale_agencies[:3])
        if len(s.stale_agencies) > 3:
            examples += f" (+{len(s.stale_agencies) - 3} more)"
        lines.append(f"| {s.host} | {s.total} | {s.expired} | {s.counts['stale']} | {examples} |")
    lines.append("")
    lines.append(
        "_Internal support tool — shows which feed hosts have the most expiry problems. "
        "Not for public distribution._"
    )
    lines.append("")
    return "\n".join(lines)


def render_vendor_report_csv(
    stats: list[VendorStat],
    min_agencies: int = MIN_AGENCIES_FOR_BENCHMARK,
) -> str:
    """CSV version of the vendor freshness report for download or further analysis."""
    import csv
    import io

    qualified = [s for s in stats if s.total >= min_agencies]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["host", "agencies", "expired", "stale", "example_agencies"])
    for s in qualified:
        examples = "; ".join(s.stale_agencies[:3])
        writer.writerow([s.host, s.total, s.expired, s.counts["stale"], examples])
    return buf.getvalue()


def render_vendor_quality(stats: list[VendorQuality]) -> str:
    """A small markdown table comparing data quality across feed hosts.

    Framed as a benchmark of the feeds as published, not a verdict on the
    agencies behind them. The fairness note states the limits plainly.
    """
    lines = ["## Data quality by feed host", ""]
    if not stats:
        lines.append("No feed host has enough agencies to benchmark yet.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Host | Agencies | Avg score | Median score | Grade spread |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for s in stats:
        spread = ", ".join(
            f"{grade}: {count}" for grade, count in sorted(s.grade_distribution.items())
        )
        lines.append(
            f"| {s.host} | {s.agency_count} | {s.avg_score:.1f} | {s.median_score:.1f} | {spread} |"
        )
    lines.append("")
    lines.append(
        "These numbers reflect the feeds as published. They are not adjusted for "
        "agency size or for the quality of the source data each tool was given."
    )
    lines.append("")
    return "\n".join(lines)
