"""Weight feed quality by ridership, so impact reads in rider-trips not agencies.

"63 feeds are expired" understates the stakes when one of those feeds carries a
million annual trips and another carries a thousand. The National Transit Database
publishes annual unlinked passenger trips (UPT) per reporter, keyed by the
five-digit NTD ID that ADR 0016's crosswalk now puts on matched feeds. Joining the
two lets the national numbers read in rider-trips: how many trips ride on an
expired feed, how quality distributes across actual ridership.

This module is the join and the weighting, pure and tested. It is deliberately
gated on data the repository does not yet hold: the public NTD ridership file is
not reachable from the build environment, and only a minority of feeds carry an
NTD ID so far, so the weighting is honest only over the matched subset and reports
its own coverage. Commit a ridership snapshot to ``data/ntd-ridership.csv`` and
broaden NTD-ID coverage to make it national. Nothing here fabricates ridership;
absent data yields an empty, clearly-labelled result rather than a guess.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from ._stats import _GRADES

# FTA's NTD annual metrics on data.transportation.gov (Socrata): one row per
# reporter per report year, carrying the five-digit NTD ID and annual unlinked
# passenger trips. This is the public source the paragraph above said was out
# of reach; fetch_ridership_csv pulls it so nothing is hand-committed.
NTD_METRICS_URL = "https://data.transportation.gov/resource/g27i-aq2u.csv"


def fetch_ridership_csv(report_year: int, *, timeout: int = 60) -> str:
    """Fetch annual UPT per NTD reporter from the FTA Socrata dataset as CSV.

    Column aliases are chosen so ``parse_ridership_csv`` finds them by header
    (an ntd_id column and a trips column containing "upt"). Raises on HTTP
    failure; callers treat a failed fetch as "no data this run", never as a
    scoring failure.
    """
    from .net import safe_get

    query = (
        "?$select=ntd_id,sum_unlinked_passenger_trips%20AS%20upt"
        f"&report_year={report_year}&$limit=50000"
    )
    return safe_get(NTD_METRICS_URL + query, timeout=timeout).decode("utf-8")


def _norm(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def parse_ridership_csv(text: str) -> dict[str, int]:
    """Parse an NTD ridership CSV into annual trips (UPT) per NTD ID.

    The NTD publishes ridership in several layouts, so the columns are found by
    header rather than position: an NTD-ID column (header containing "ntdid") and a
    trips column (header containing "upt", "unlinkedpassengertrips", or
    "ridership"). Values are summed per NTD ID, so a per-mode or per-month file
    collapses to one annual total per reporter. Rows with no parseable id or number
    are skipped. NTD IDs are normalized to their digits (zero-padding and stray
    decimals from spreadsheet exports are stripped) so they join to the registry's
    five-digit ids.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {}
    header = rows[0]
    norm = [_norm(h) for h in header]

    def _find(*needles: str, exclude: tuple[str, ...] = ()) -> int | None:
        # Prefer an exact normalized match before falling back to contains, so
        # "State/Parent NTD ID" (stateparentntdid) does not shadow "NTD ID"
        # (ntdid) when both columns are present.
        for i, h in enumerate(norm):
            if h in needles and not any(x in h for x in exclude):
                return i
        for i, h in enumerate(norm):
            if any(n in h for n in needles) and not any(x in h for x in exclude):
                return i
        return None

    id_col = _find("ntdid", exclude=("parent", "state"))
    upt_col = _find("upt", "unlinkedpassengertrips", "ridership", "passengertrips")
    if id_col is None or upt_col is None:
        return {}

    out: dict[str, int] = {}
    for row in rows[1:]:
        if len(row) <= max(id_col, upt_col):
            continue
        # Strip stray ".0" decimal suffixes from spreadsheet exports before taking
        # digits, then drop zero-padding so "0090001" joins to the registry's
        # unpadded id ("90001"). float() handles both "90001.0" and plain ints.
        raw_id = row[id_col].strip()
        try:
            raw_id = str(int(float(raw_id)))
        except ValueError:
            raw_id = "".join(ch for ch in raw_id if ch.isdigit())
        ntd = raw_id.lstrip("0")
        if not ntd:
            continue
        raw = row[upt_col].strip().replace(",", "")
        if not raw:
            continue
        try:
            trips = int(round(float(raw)))
        except ValueError:
            continue
        out[ntd] = out.get(ntd, 0) + trips
    return out


def load_ridership(csv_path: str | Path) -> dict[str, int] | None:
    """Load an NTD ridership snapshot into annual trips per NTD ID, or None.

    A thin wrapper over ``parse_ridership_csv`` for call sites that only have a
    path: returns ``None`` when the file is absent — the common case in an
    environment without the snapshot — so a caller can degrade gracefully to
    unweighted ordering, and the parsed map otherwise. A present-but-empty or
    unparseable file yields an empty dict, not ``None``, so "no file" and "file
    matched nothing" stay distinguishable.
    """
    path = Path(csv_path)
    if not path.exists():
        return None
    return parse_ridership_csv(path.read_text())


def annual_trips_for(record: dict[str, Any], ridership: dict[str, int] | None) -> int | None:
    """Annual trips for one record's NTD ID, or ``None`` when unknown.

    Resolves the record's ``ntd_id`` the same way ``weighted_impact`` does (as a
    plain string), so the two agree on which feeds are matched. Returns ``None``
    — never ``0`` — when the ridership map is absent, the record carries no NTD
    ID, or the id is unmatched, so "no data" never reads as "no riders".
    """
    if not ridership:
        return None
    ntd = str(record.get("ntd_id") or "")
    if not ntd:
        return None
    return ridership.get(ntd)


def weighted_impact(records: list[dict[str, Any]], ridership: dict[str, int]) -> dict[str, Any]:
    """Weight the matched feeds' quality by annual ridership.

    ``records`` are per-agency rows carrying ntd_id, score, grade, and
    expiry_status. ``ridership`` maps NTD ID to annual trips. Only agencies with
    both an NTD ID and a ridership figure are weighted; the rest are reported as
    coverage so the result never overstates how national it is. Returns the matched
    agency count, total annual trips covered, trips on expired feeds and their
    share, the ridership-weighted average score, and trips by grade.
    """
    matched = []
    for r in records:
        ntd = str(r.get("ntd_id") or "")
        trips = ridership.get(ntd)
        if ntd and trips:
            matched.append((r, trips))

    total_trips = sum(t for _, t in matched)
    by_grade = dict.fromkeys(_GRADES, 0)
    expired_trips = 0
    weighted_score_num = 0.0
    for r, trips in matched:
        g = r.get("grade")
        if g in by_grade:
            by_grade[g] += trips
        if r.get("expiry_status") in ("lapsed", "stale"):
            expired_trips += trips
        if isinstance(r.get("score"), int | float):
            weighted_score_num += float(r["score"]) * trips

    return {
        "matched_agencies": len(matched),
        "total_agencies": len(records),
        "total_annual_trips": total_trips,
        "trips_on_expired_feeds": expired_trips,
        "expired_trips_pct": (round(expired_trips / total_trips * 100, 1) if total_trips else 0.0),
        "weighted_average_score": (
            round(weighted_score_num / total_trips, 1) if total_trips else None
        ),
        "trips_by_grade": by_grade,
    }
