"""Reconcile a program's feed records against the Caltrans report directory.

Caltrans and Cal-ITP publish a monthly GTFS quality report for each California
agency they carry, and the directory of those reports is the closest thing the
state has to a roster of who publishes transit data here. This scorecard's
registry grew from open feed catalogues instead, so the two populations were
never lined up: some records here describe a feed the state does not carry,
some organizations there have no record here, and one operator can appear
under several feed records.

This module reads the curated crosswalk in
``data/california-caltrans-crosswalk.yaml`` and reports how a program's members
line up with that directory. It is pure over the committed file, so it adds no
network access and the same input always gives the same numbers.

The crosswalk itself is built by ``pipeline/scripts/build_california_crosswalk.py``
and the method is written up in ``docs/california-reconciliation.md``. A record
is only ``matched`` when the evidence identifies one organization; otherwise it
stays ``uncertain``, which is reported as its own figure rather than folded into
either side. Nothing here changes a grade.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import repo_root

MATCHED = "matched"
UNCERTAIN = "uncertain"
ABSENT = "absent"
STATUSES = (MATCHED, UNCERTAIN, ABSENT)


@dataclass(frozen=True)
class CrosswalkRecord:
    """One registry record's standing against the Caltrans report directory."""

    agency_id: str
    name: str
    status: str
    method: str
    evidence: str
    caltrans_id: int | None = None
    caltrans_name: str = ""


@dataclass(frozen=True)
class Crosswalk:
    """The curated crosswalk, with the directory snapshot it was built from."""

    directory_source: str
    directory_month: str
    directory_retrieved_on: str
    directory_agencies: int
    records: tuple[CrosswalkRecord, ...]
    directory_only: tuple[dict[str, Any], ...]

    def by_id(self) -> dict[str, CrosswalkRecord]:
        return {record.agency_id: record for record in self.records}


def crosswalk_path() -> Path:
    return repo_root() / "data" / "california-caltrans-crosswalk.yaml"


def _as_record(row: dict[str, Any]) -> CrosswalkRecord:
    status = str(row.get("status") or "")
    if status not in STATUSES:
        raise ValueError(f"unknown crosswalk status {status!r} for {row.get('id')!r}")
    caltrans_id = row.get("caltrans_id")
    return CrosswalkRecord(
        agency_id=str(row["id"]),
        name=str(row.get("name") or row["id"]),
        status=status,
        method=str(row.get("method") or ""),
        evidence=str(row.get("evidence") or ""),
        caltrans_id=int(caltrans_id) if caltrans_id is not None else None,
        caltrans_name=str(row.get("caltrans_name") or ""),
    )


def load_crosswalk(path: Path | None = None) -> Crosswalk | None:
    """Read the curated crosswalk, or return None when the file is not present.

    Absence is normal: an instance of this software that carries no California
    program has nothing to reconcile, and the program page simply omits the
    section rather than showing an empty one.
    """
    import yaml

    target = path or crosswalk_path()
    try:
        raw = yaml.safe_load(target.read_text())
    except FileNotFoundError:
        return None
    if not isinstance(raw, dict) or not raw.get("records"):
        return None
    return Crosswalk(
        directory_source=str(raw.get("directory_source") or ""),
        directory_month=str(raw.get("directory_month") or ""),
        directory_retrieved_on=str(raw.get("directory_retrieved_on") or ""),
        directory_agencies=int(raw.get("directory_agencies") or 0),
        records=tuple(_as_record(row) for row in raw["records"]),
        directory_only=tuple(dict(row) for row in raw.get("directory_only") or ()),
    )


def reconciliation(crosswalk: Crosswalk, member_ids: list[str]) -> dict[str, Any]:
    """How one program's members line up with the Caltrans report directory.

    ``matched`` counts members whose evidence identifies one organization in
    the directory. ``uncertain`` counts members with a plausible but ambiguous
    candidate; they are never reported as matches. ``absent`` counts members
    with no candidate at all, which usually means a service the state's
    monthly reports do not carry rather than an error on either side.

    ``organizations_matched`` deduplicates: several feed records can describe
    one operator, so it is the honest denominator for "how much of their
    directory does this program cover".
    """
    index = crosswalk.by_id()
    members = [index[member] for member in member_ids if member in index]
    counts = {status: sum(1 for m in members if m.status == status) for status in STATUSES}
    organizations = sorted({m.caltrans_id for m in members if m.caltrans_id is not None})
    return {
        "directory_source": crosswalk.directory_source,
        "directory_month": crosswalk.directory_month,
        "directory_retrieved_on": crosswalk.directory_retrieved_on,
        "directory_agencies": crosswalk.directory_agencies,
        "reconciled_records": len(members),
        "unreconciled_records": len(member_ids) - len(members),
        "matched_records": counts[MATCHED],
        "uncertain_records": counts[UNCERTAIN],
        "absent_records": counts[ABSENT],
        "organizations_matched": len(organizations),
        "directory_only_agencies": len(crosswalk.directory_only),
    }
