"""Write data/clearance-logs-in-sitemap.json from a Search Console page export.

ADR 0080: the sitemap lists a clearance log (/agency/<id>/fixes/) only when it
is indexable and earned at least one search impression in the export's window.
This reads the Search Analytics API's page report, the JSON the query returns
(``{"start", "end", "rows": [{"keys": [url], "impressions": n}, ...]}``), and
writes the agency ids it finds, sorted, with the window they came from. It
makes no network call: the export is pulled separately with read-only access.

    uv run python scripts/clearance_log_sitemap_list.py EXPORT.json --pulled YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_LOG_URL = re.compile(r"https://gtfsscorecard\.org/agency/([a-z0-9][a-z0-9-]*)/fixes/")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_OUT = Path(__file__).resolve().parents[2] / "data" / "clearance-logs-in-sitemap.json"


def clearance_log_ids(export: dict[str, Any]) -> list[str]:
    """Agency ids whose clearance log had an impression, sorted and unique.

    Only the clean URL counts: a query-string or fragment variant is a
    different URL to Search Console and is not the page the sitemap lists.
    """
    ids: set[str] = set()
    for row in export.get("rows") or []:
        keys = row.get("keys") if isinstance(row, dict) else None
        if not isinstance(keys, list) or not keys:
            continue
        impressions = row.get("impressions")
        if isinstance(impressions, bool) or not isinstance(impressions, (int, float)):
            continue
        match = _LOG_URL.fullmatch(str(keys[0]))
        if match and impressions > 0:
            ids.add(match.group(1))
    return sorted(ids)


def build(export: dict[str, Any], pulled: str) -> dict[str, Any]:
    start, end = export.get("start"), export.get("end")
    for name, value in (("start", start), ("end", end), ("pulled", pulled)):
        if not (isinstance(value, str) and _DATE.fullmatch(value)):
            raise ValueError(f"{name} must be a YYYY-MM-DD date, got {value!r}")
    return {
        "schema_version": 1,
        "source": "Search Console page report, web search, all countries",
        "window_start": start,
        "window_end": end,
        "pulled": pulled,
        "agency_ids": clearance_log_ids(export),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path)
    parser.add_argument("--pulled", required=True, help="date the export was pulled")
    parser.add_argument("--out", type=Path, default=_OUT)
    args = parser.parse_args(argv)
    payload = build(json.loads(args.export.read_text()), args.pulled)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {len(payload['agency_ids'])} clearance logs to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
