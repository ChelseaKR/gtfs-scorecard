"""GBFS expansion: a version-currency check over the open GBFS catalog.

The scorecard's home is fixed-route GTFS, but the same agencies and the same
state programs increasingly run shared micromobility (bikeshare, scooters), which
publishes GBFS, not GTFS. The first step into that world is the cheapest useful
check: is each system's GBFS feed on a current spec version, or stuck on an old
one that modern trip planners and the MobilityData tooling no longer prefer.

MobilityData's open GBFS catalog (systems.csv) already records each system's
supported versions, so this reads currency straight from the catalog: no need to
fetch every system's discovery document. Parsing and the currency decision are
pure and unit-tested; fetching the catalog is a thin call.

References: the GBFS catalog at github.com/MobilityData/gbfs (systems.csv) and the
GBFS spec version history.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from .net import safe_get

# The published GBFS catalog as a single CSV.
DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/MobilityData/gbfs/master/systems.csv"

# GBFS 3.0 is the current major line; 2.3 is the last 2.x and still widely
# deployed, so it is treated as supported rather than outdated. Anything below
# 2.3 is outdated, and a system that states no version is unknown. These are the
# bands a state program would act on, not a judgment on any one operator.
CURRENT_MAJOR = 3
SUPPORTED_FLOOR = (2, 3)

CURRENT = "current"  # on the current major line (3.x)
SUPPORTED = "supported"  # 2.3 or newer, below 3.0
OUTDATED = "outdated"  # below 2.3
UNKNOWN = "unknown"  # no parseable version stated

_VERSION_RE = re.compile(r"(\d+)\.(\d+)")


@dataclass(frozen=True)
class GbfsSystem:
    """One row of the GBFS catalog, narrowed to the fields this check uses."""

    system_id: str
    name: str
    location: str
    country_code: str
    auto_discovery_url: str
    supported_versions: tuple[str, ...]


def _cell(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def _parse_versions(raw: str) -> tuple[str, ...]:
    """Versions from a catalog cell. The column lists them separated by ';' or
    ',', sometimes with stray spaces; keep only well-formed X.Y tokens."""
    parts = re.split(r"[;,]", raw)
    out = []
    for part in parts:
        m = _VERSION_RE.search(part)
        if m:
            out.append(f"{int(m.group(1))}.{int(m.group(2))}")
    return tuple(out)


def parse_systems_csv(csv_text: str) -> list[GbfsSystem]:
    """Parse the GBFS catalog CSV, skipping rows without an auto-discovery URL."""
    systems: list[GbfsSystem] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        url = _cell(row, "Auto-Discovery URL", "URL")
        if not url:
            continue
        systems.append(
            GbfsSystem(
                system_id=_cell(row, "System ID", "System Id", "id"),
                name=_cell(row, "Name", "name"),
                location=_cell(row, "Location", "location"),
                country_code=_cell(row, "Country Code", "country_code").upper(),
                auto_discovery_url=url,
                supported_versions=_parse_versions(_cell(row, "Supported Versions", "version")),
            )
        )
    return systems


def _highest(versions: tuple[str, ...]) -> tuple[int, int] | None:
    parsed = []
    for v in versions:
        m = _VERSION_RE.fullmatch(v)
        if m:
            parsed.append((int(m.group(1)), int(m.group(2))))
    return max(parsed) if parsed else None


def version_status(versions: tuple[str, ...]) -> str:
    """Classify a system by the highest GBFS version it supports."""
    top = _highest(versions)
    if top is None:
        return UNKNOWN
    if top[0] >= CURRENT_MAJOR:
        return CURRENT
    if top >= SUPPORTED_FLOOR:
        return SUPPORTED
    return OUTDATED


@dataclass(frozen=True)
class GbfsSummary:
    """A currency roll-up over a set of GBFS systems."""

    total: int
    current: int
    supported: int
    outdated: int
    unknown: int
    pct_current_line: float  # share on 3.x
    outdated_systems: list[GbfsSystem]


def assess_catalog(systems: list[GbfsSystem]) -> GbfsSummary:
    """Roll up version currency across GBFS systems.

    The headline a program lead wants: how many shared-mobility systems are on
    the current GBFS line, and which are stuck on an outdated version that newer
    trip planners may not consume well. Outdated systems are listed so the gap is
    actionable rather than just a number.
    """
    counts = {CURRENT: 0, SUPPORTED: 0, OUTDATED: 0, UNKNOWN: 0}
    outdated: list[GbfsSystem] = []
    for system in systems:
        status = version_status(system.supported_versions)
        counts[status] += 1
        if status == OUTDATED:
            outdated.append(system)
    total = len(systems)
    pct_current = round(counts[CURRENT] / total * 100, 1) if total else 0.0
    return GbfsSummary(
        total=total,
        current=counts[CURRENT],
        supported=counts[SUPPORTED],
        outdated=counts[OUTDATED],
        unknown=counts[UNKNOWN],
        pct_current_line=pct_current,
        outdated_systems=sorted(outdated, key=lambda s: s.name.lower()),
    )


def render_report(summary: GbfsSummary, *, country: str | None = None) -> str:
    """A markdown currency report over the GBFS catalog."""
    scope = f" in {country}" if country else ""
    if summary.total == 0:
        return f"# GBFS version currency\n\nNo GBFS systems found{scope}."
    lines = [
        f"# GBFS version currency{scope}",
        "",
        f"**{summary.current} of {summary.total} systems are on the current GBFS 3.x line "
        f"({summary.pct_current_line}%).**",
        "",
        f"- Current (3.x): {summary.current}",
        f"- Supported (2.3 to 2.x): {summary.supported}",
        f"- Outdated (below 2.3): {summary.outdated}",
        f"- No version stated: {summary.unknown}",
    ]
    if summary.outdated_systems:
        lines += ["", "## Outdated systems to upgrade", ""]
        for s in summary.outdated_systems:
            vers = ", ".join(s.supported_versions) or "none stated"
            where = f" ({s.location})" if s.location else ""
            lines.append(f"- {s.name}{where}: supports {vers}")
    lines.append("")
    lines.append(
        "Currency is read from the MobilityData GBFS catalog's stated versions. "
        "An outdated line is a prompt to ask the operator's vendor about upgrading."
    )
    return "\n".join(lines)


def fetch_systems_csv(url: str = DEFAULT_CATALOG_URL) -> str:
    """Download the GBFS catalog CSV. Split out so tests use a local fixture."""
    data = safe_get(url, timeout=60, max_bytes=32 * 1024 * 1024)
    return data.decode("utf-8", errors="replace")
