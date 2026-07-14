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
from collections import Counter
from collections.abc import Iterable
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


def parse_ridership_csv(text: str) -> dict[str, int]:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
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
            trips = round(float(raw))
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


def normalize_ntd_id(value: object) -> str:
    """Return the canonical join key used by the NTD ridership snapshot.

    FTA exports commonly zero-pad reporter ids while the Socrata aggregate does
    not.  Keeping one normalization at every join and duplicate check prevents a
    registry value such as ``00007`` from either missing its ridership or evading
    a duplicate-reporter quarantine.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.lstrip("0") or ("0" if digits else "")


def duplicate_ntd_reporter_ids(records: Iterable[object]) -> set[str]:
    """NTD reporter ids claimed by more than one row in the full source set.

    ``records`` may be registry ``Agency`` objects or row dictionaries.  Callers
    intentionally compute this over the unfiltered registry/corpus *before*
    selecting a comparison cohort; otherwise an excluded sibling feed can make
    the remaining row look like a unique reporter and receive the reporter's
    entire annual UPT.
    """
    ids: list[str] = []
    for record in records:
        value = record.get("ntd_id") if isinstance(record, dict) else getattr(record, "ntd_id", "")
        ntd_id = normalize_ntd_id(value)
        if ntd_id:
            ids.append(ntd_id)
    counts = Counter(ids)
    return {ntd_id for ntd_id, count in counts.items() if count > 1}


def annual_trips_for(record: dict[str, Any], ridership: dict[str, int] | None) -> int | None:
    """Annual trips for one record's NTD ID, or ``None`` when unknown.

    Resolves the record's ``ntd_id`` the same way ``weighted_impact`` does (as a
    plain string), so the two agree on which feeds are matched. Returns ``None``
    — never ``0`` — when the ridership map is absent, the record carries no NTD
    ID, or the id is unmatched, so "no data" never reads as "no riders".
    """
    if not ridership:
        return None
    ntd = normalize_ntd_id(record.get("ntd_id"))
    if not ntd:
        return None
    return ridership.get(ntd)


def weighted_impact(
    records: list[dict[str, Any]],
    ridership: dict[str, int],
    *,
    quarantined_ntd_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Weight unambiguous NTD reporter matches by annual ridership.

    ``records`` are per-feed rows carrying ntd_id, score, grade, and
    expiry_status. ``ridership`` maps NTD ID to annual trips. One NTD reporter's
    annual UPT must never be applied to several feed rows: when an NTD ID occurs
    more than once, every row carrying that ID is quarantined from weighting
    until the registry can identify a single authoritative feed. This is more
    conservative than guessing among a reporter's regional, modal, or conflicting
    feeds, and it prevents national trip totals from being multiplied by feed
    count.

    Only unique feed-to-reporter matches with a ridership figure are weighted.
    Coverage and duplicate exclusions are returned alongside the totals. The
    legacy ``matched_agencies`` and ``total_agencies`` keys remain as compatibility
    aliases; their precise replacements are ``matched_ntd_reporters`` and
    ``total_feed_records``.
    """
    ntd_counts = Counter(normalize_ntd_id(r.get("ntd_id")) for r in records)
    ntd_counts.pop("", None)
    duplicate_ids = {ntd for ntd, count in ntd_counts.items() if count > 1}
    duplicate_ids.update(normalize_ntd_id(ntd) for ntd in quarantined_ntd_ids)
    duplicate_ids.discard("")
    present_duplicate_ids = duplicate_ids.intersection(ntd_counts)

    matched: list[tuple[dict[str, Any], int]] = []
    for r in records:
        ntd = normalize_ntd_id(r.get("ntd_id"))
        trips = ridership.get(ntd)
        if ntd and ntd not in duplicate_ids and trips is not None:
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

    duplicate_rows = sum(ntd_counts[ntd] for ntd in present_duplicate_ids)
    matched_reporters = len(matched)
    return {
        # Compatibility aliases retained for existing API consumers. The UI and
        # new integrations use the accurately named fields below.
        "matched_agencies": matched_reporters,
        "total_agencies": len(records),
        "matched_ntd_reporters": matched_reporters,
        "matched_feed_records": matched_reporters,
        "total_feed_records": len(records),
        "duplicate_ntd_reporter_count": len(present_duplicate_ids),
        "duplicate_feed_records_excluded": duplicate_rows,
        "duplicate_ntd_ids_excluded": sorted(present_duplicate_ids),
        "total_annual_trips": total_trips,
        "trips_on_expired_feeds": expired_trips,
        "expired_trips_pct": (round(expired_trips / total_trips * 100, 1) if total_trips else 0.0),
        "weighted_average_score": (
            round(weighted_score_num / total_trips, 1) if total_trips else None
        ),
        "trips_by_grade": by_grade,
    }
