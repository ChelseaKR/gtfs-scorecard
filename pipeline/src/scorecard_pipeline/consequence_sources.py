"""Read the snapshots the consequence layer joins at render time (issue #367).

``consequence.join_feed_context`` is pure. This module is the disk side: it
loads the NTD ridership snapshot, the US state-level need overlay, and the
Canadian CIMD overlay, each with the stamp that says where it came from and
when it was taken. A snapshot without a stamp loads with ``stamp=None``, and
the join then refuses to show its numbers, because a page must name the source
and date of every number it joins.

The stamps are written by the producers themselves: ``scorecard ntd-ridership
--fetch`` writes ``data/ntd-ridership.meta.json`` next to the CSV, and ``scorecard
equity`` and ``scorecard canada-equity`` record ``generated_on`` in their JSON.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .consequence import NeedOverlay, RenderSources, RidershipSnapshot, SourceStamp
from .ridership import load_ridership

RIDERSHIP_CSV = Path("data") / "ntd-ridership.csv"
RIDERSHIP_META = Path("data") / "ntd-ridership.meta.json"
US_NEED_JSON = Path("web") / "api" / "v1" / "equity.json"
CA_NEED_JSON = Path("data") / "artifacts" / "canada-equity.json"

RIDERSHIP_SOURCE = "FTA National Transit Database"
CIMD_SOURCE = "Canadian Index of Multiple Deprivation 2021"


def _iso_date(value: object) -> str:
    """``value`` as an ISO date, or "" when it is not one."""
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return ""


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def ridership_meta(report_year: int, fetched_on: dt.date) -> dict[str, Any]:
    """The stamp ``ntd-ridership --fetch`` writes beside the CSV it fetched."""
    return {
        "source": RIDERSHIP_SOURCE,
        "report_year": report_year,
        "fetched_on": fetched_on.isoformat(),
    }


def load_ridership_snapshot(root: Path) -> RidershipSnapshot | None:
    """The ridership CSV with its stamp, or ``None`` when the CSV is missing."""
    trips = load_ridership(root / RIDERSHIP_CSV)
    if trips is None:
        return None
    meta = _read_json(root / RIDERSHIP_META) or {}
    year = meta.get("report_year")
    fetched = _iso_date(meta.get("fetched_on"))
    stamp = None
    if isinstance(year, int) and not isinstance(year, bool) and fetched:
        stamp = SourceStamp(f"{RIDERSHIP_SOURCE}, report year {year}", fetched)
    return RidershipSnapshot(trips=trips, stamp=stamp)


def load_us_need(root: Path) -> NeedOverlay | None:
    """State need tiers from the published ACS overlay, keyed by state name."""
    doc = _read_json(root / US_NEED_JSON)
    if doc is None:
        return None
    tiers = {
        str(row["state"]): str(row.get("need_tier") or "")
        for row in doc.get("states") or []
        if isinstance(row, dict) and row.get("state")
    }
    year = str(doc.get("acs_year") or "").strip()
    built = _iso_date(doc.get("generated_on"))
    stamp = None
    if year and built:
        stamp = SourceStamp(f"US Census ACS 5-year {year}, statewide overlay", built)
    return NeedOverlay(tiers=tiers, stamp=stamp)


def load_ca_need(root: Path) -> NeedOverlay | None:
    """CIMD served-area tiers, keyed by agency id."""
    doc = _read_json(root / CA_NEED_JSON)
    if doc is None:
        return None
    agencies = doc.get("agencies")
    tiers = {
        str(agency_id): str((row or {}).get("need_tier") or "")
        for agency_id, row in (agencies.items() if isinstance(agencies, dict) else [])
        if isinstance(row, dict)
    }
    built = _iso_date(doc.get("generated_on"))
    source = str(doc.get("source") or "").strip()
    stamp = SourceStamp(source, built) if source and built else None
    return NeedOverlay(tiers=tiers, stamp=stamp)


def load_render_sources(root: Path, quarantined_ntd_ids: frozenset[str]) -> RenderSources:
    """Everything the render-time join reads, from one repository root."""
    return RenderSources(
        ridership=load_ridership_snapshot(root),
        quarantined_ntd_ids=quarantined_ntd_ids,
        us_need=load_us_need(root),
        ca_need=load_ca_need(root),
    )
