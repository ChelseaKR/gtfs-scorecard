#!/usr/bin/env python3
"""Re-read the Caltrans monthly GTFS report directory into a dated snapshot.

Writes ``data/caltrans-report-directory.json``: for each agency in the most
recent published month, its report id, name, report URL, listed technology
vendors, and the feed URLs shown in that report's own "Show Source URLs" panel.

This is the one place in the repository that reaches their site, and it is never
run by a test or by the daily build. The monthly refresh workflow runs it and
opens a pull request when the directory has moved on; the committed snapshot is
what everything else reads, so the crosswalk stays reproducible offline.

Polite by construction: one request for the directory index, then one request
per agency report, spaced.

    uv run --project pipeline python pipeline/scripts/fetch_caltrans_directory.py
    uv run --project pipeline python pipeline/scripts/fetch_caltrans_directory.py --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "data" / "caltrans-report-directory.json"
BASE = "https://reports.dds.dot.ca.gov"
USER_AGENT = "gtfs-scorecard crosswalk refresh (monthly, one request per report)"

_MONTH_LINK = re.compile(r'href="(/gtfs_schedule/(\d{4})/(\d{2}))"')
_ROW = re.compile(
    r'data-agency-name="([^"]*)"\s+data-schedule-vendors="([^"]*)"\s+'
    r'data-rt-vendors="([^"]*)">\s*<a class="list-group__link"\s*'
    r'href="(/gtfs_schedule/\d{4}/\d{2}/(\d+)/index\.html)"',
    re.S,
)
_SOURCE_LINK = re.compile(r'<a href="([^"]+)" rel="external" target="_blank">([^<]*)</a>', re.S)


def _get(url: str) -> str:
    # S310 covers the scheme, not the caller: every URL this builds comes from
    # the module's own https:// constants and links parsed out of that page.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return str(response.read().decode("utf-8", "replace"))


def latest_month() -> str:
    """The most recent month their directory publishes, as ``YYYY/MM``."""
    months = sorted({m.group(1) for m in _MONTH_LINK.finditer(_get(BASE + "/"))})
    if not months:
        raise SystemExit("no monthly report links found; their page layout may have changed")
    return months[-1].removeprefix("/gtfs_schedule/")


def classify(label: str, url: str) -> str:
    """Which GTFS feed kind a listed source URL is, from its label and shape."""
    flat = label.lower().replace(" ", "")
    lowered = url.lower()
    if "tripupdate" in flat or "trip-update" in lowered or "tripupdate" in lowered:
        return "trip_updates"
    if "/trips" in lowered:
        return "trip_updates"
    if "vehicleposition" in flat or "vehicle-position" in lowered:
        return "vehicle_positions"
    if "vehicleposition" in lowered or "/vehicles" in lowered or "position_updates" in lowered:
        return "vehicle_positions"
    if "alert" in flat or "alrt" in flat or "alert" in lowered:
        return "service_alerts"
    return "schedule"


def agency_feeds(page: str) -> dict[str, list[str]]:
    start = page.find('<dialog id="feed-info-modal"')
    if start == -1:
        return {}
    panel = page[start : page.find("</dialog>", start)]
    feeds: dict[str, list[str]] = {}
    for url, label in _SOURCE_LINK.findall(panel):
        url, label = html.unescape(url).strip(), html.unescape(label).strip()
        feeds.setdefault(classify(label, url), []).append(url)
    return {kind: sorted(dict.fromkeys(urls)) for kind, urls in sorted(feeds.items())}


def harvest(month: str, *, delay: float = 0.7) -> dict[str, Any]:
    index = _get(f"{BASE}/gtfs_schedule/{month}")
    rows = _ROW.findall(index)
    if not rows:
        raise SystemExit("no agency rows found; their page layout may have changed")
    agencies = []
    for name, schedule_vendors, rt_vendors, path, caltrans_id in rows:
        page = _get(BASE + path)
        agencies.append(
            {
                "caltrans_id": int(caltrans_id),
                "name": html.unescape(name),
                "report_url": BASE + path,
                "schedule_vendors": json.loads(html.unescape(schedule_vendors)),
                "realtime_vendors": json.loads(html.unescape(rt_vendors)),
                "feeds": agency_feeds(page),
            }
        )
        time.sleep(delay)
    agencies.sort(key=lambda a: int(a["caltrans_id"]))
    return {
        "schema_version": "1.0",
        "source": (
            "California GTFS Quality Dashboard (Caltrans / Cal-ITP) monthly report directory"
        ),
        "source_url": f"{BASE}/gtfs_schedule/{month}",
        "report_month": month.replace("/", "-"),
        # UTC, not the machine's zone: this date is committed with the data file,
        # so two curators on different continents must stamp the same day.
        "retrieved_on": dt.datetime.now(dt.UTC).date().isoformat(),
        "note": (
            "Read once from the published monthly report pages. Each agency's feed URLs come "
            "from the Show Source URLs panel of its own report. Republished here so the "
            "crosswalk is reproducible offline; the reports themselves stay the authority."
        ),
        "agency_count": len(agencies),
        "agencies": agencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether a newer month has been published, and change nothing",
    )
    args = parser.parse_args()

    month = latest_month()
    committed = json.loads(OUT.read_text())["report_month"] if OUT.exists() else ""
    if args.check:
        current = month.replace("/", "-")
        if current == committed:
            print(f"OK  the committed snapshot is their current month ({committed})")
            return 0
        print(f"STALE  committed {committed or 'nothing'}, they now publish {current}")
        return 1

    snapshot = harvest(month)
    OUT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {snapshot['agency_count']} agencies, {month}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
