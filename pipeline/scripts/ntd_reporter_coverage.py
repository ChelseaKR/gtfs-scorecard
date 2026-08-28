#!/usr/bin/env python3
"""Run the inverted NTD join and write the reporter-coverage snapshot.

Reads three public sources over the network, joins them with
`scorecard_pipeline.ntd_coverage`, and writes `data/ntd/`. Not part of
`make verify`: it needs the network, and the answer only moves when FTA
publishes a new report year or a catalogue changes.

    cd pipeline && uv run python scripts/ntd_reporter_coverage.py

Sources, all public domain or openly licensed:

  Agency Information (the roster)   data.transportation.gov dataset ccvf-fykn
  Service (by Mode)                 data.transportation.gov dataset 4fir-qbim
  Transitland Atlas                 github.com/transitland/transitland-atlas
  Mobility Database catalog         storage.googleapis.com mdb-csv/sources.csv

The two FTA tables are Socrata mirrors of the annual-database products on
transit.dot.gov, which is behind an edge filter that refuses non-browser
clients. The mirror is the same product and is machine-readable, so it is what
this pins.

The Mobility Database leg deliberately reads the storage.googleapis.com catalog
that `scorecard discover` already reads weekly, not `feeds_v2.csv`. The v2
catalog is larger and better, and its host `files.mobilitydatabase.org` serves
`User-agent: * / Disallow: /` (checked 2026-08-15). Adding a new automated
reader of a host that asks not to be read is not a trade worth making for a
wider join, so this takes the smaller catalog and says so in the write-up.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scorecard_pipeline.agencies import read_agencies
from scorecard_pipeline.location import US_SUBDIVISIONS
from scorecard_pipeline.ntd_coverage import (
    TIER_ORDER,
    US_AND_TERRITORY_CODES,
    CatalogIndex,
    FeedRecord,
    atlas_ntd_ids_with_a_feed,
    classify,
    obligated_reporters,
    summarize,
)

ROSTER_URL = "https://data.transportation.gov/api/views/ccvf-fykn/rows.csv?accessType=DOWNLOAD"
MODE_URL = "https://data.transportation.gov/api/views/4fir-qbim/rows.csv?accessType=DOWNLOAD"
ATLAS_URL = "https://codeload.github.com/transitland/transitland-atlas/tar.gz/refs/heads/main"
CATALOG_URL = "https://storage.googleapis.com/storage/v1/b/mdb-csv/o/sources.csv?alt=media"
REPORT_YEAR = "2024"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "ntd"

_STATE_BY_NAME = {name.lower(): code.split("-")[-1] for code, name in US_SUBDIVISIONS.items()}
_STATE_BY_NAME.update(
    {
        "puerto rico": "PR",
        "virgin islands": "VI",
        "u.s. virgin islands": "VI",
        "guam": "GU",
        "american samoa": "AS",
        "northern mariana islands": "MP",
    }
)


@dataclass(frozen=True)
class Fetched:
    url: str
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def fetch(url: str) -> Fetched:
    # Same as the urlopen below: the four source URLs are pinned https
    # constants in this module, never caller-supplied.
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "gtfs-scorecard/ntd-coverage"}
    )
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - pinned https
        return Fetched(url=url, body=response.read())


def rows_of(fetched: Fetched) -> list[dict[str, str]]:
    text = fetched.body.decode("utf-8-sig")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def atlas_docs(fetched: Fetched) -> list[dict[str, object]]:
    docs: list[dict[str, object]] = []
    with tarfile.open(fileobj=io.BytesIO(fetched.body), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "/feeds/" not in member.name:
                continue
            if not member.name.endswith(".json"):
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            try:
                parsed = json.loads(handle.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                docs.append(parsed)
    return docs


def registry_records() -> tuple[list[FeedRecord], dict[str, list[str]]]:
    records: list[FeedRecord] = []
    by_ntd_id: dict[str, list[str]] = {}
    for agency in read_agencies():
        if agency.country not in US_AND_TERRITORY_CODES:
            continue
        if agency.subdivision_code.startswith("US-"):
            state = agency.subdivision_code.split("-")[-1]
        else:
            state = "" if agency.country == "US" else agency.country
        urls = (agency.static_gtfs_url, *sorted((agency.rt_urls or {}).values()))
        records.append(FeedRecord(key=agency.id, state=state, name=agency.name, urls=urls))
        if agency.ntd_id:
            by_ntd_id.setdefault(agency.ntd_id.strip(), []).append(agency.id)
    return records, by_ntd_id


def catalog_records(rows: list[dict[str, str]]) -> list[FeedRecord]:
    out: list[FeedRecord] = []
    for row in rows:
        if row.get("data_type") != "gtfs":
            continue
        if row.get("location.country_code") not in US_AND_TERRITORY_CODES:
            continue
        subdivision = (row.get("location.subdivision_name") or "").strip().lower()
        out.append(
            FeedRecord(
                key="mdb-" + row.get("mdb_source_id", ""),
                state=_STATE_BY_NAME.get(subdivision, ""),
                name=(row.get("provider") or row.get("name") or "").strip(),
                urls=((row.get("urls.direct_download") or "").strip(),),
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-year", default=REPORT_YEAR)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    print("fetching FTA Agency Information ...", flush=True)
    roster_raw = fetch(ROSTER_URL)
    print("fetching FTA Service (by Mode) ...", flush=True)
    mode_raw = fetch(MODE_URL)
    print("fetching Transitland Atlas ...", flush=True)
    atlas_raw = fetch(ATLAS_URL)
    print("fetching Mobility Database catalog ...", flush=True)
    catalog_raw = fetch(CATALOG_URL)

    roster = rows_of(roster_raw)
    modes = rows_of(mode_raw)
    reporters = obligated_reporters(roster, modes, report_year=args.report_year)
    registry, registry_by_ntd_id = registry_records()
    registry_index = CatalogIndex(registry, label="registry")
    catalog_index = CatalogIndex(catalog_records(rows_of(catalog_raw)), label="mdb")
    atlas_ids = atlas_ntd_ids_with_a_feed(atlas_docs(atlas_raw))

    matches = [
        classify(
            reporter,
            registry_by_ntd_id=registry_by_ntd_id,
            registry=registry_index,
            atlas_ntd_ids=atlas_ids,
            catalog=catalog_index,
        )
        for reporter in reporters
    ]
    coverage = summarize(matches, report_year=args.report_year, obligated=len(reporters))

    args.out.mkdir(parents=True, exist_ok=True)
    detail = args.out / f"reporter-coverage-ry{args.report_year}.csv"
    with detail.open("w", newline="", encoding="utf-8") as handle:
        # LF, not the csv module's default CRLF: this file is committed.
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "ntd_id",
                "agency_name",
                "doing_business_as",
                "state",
                "reporter_type",
                "organization_type",
                "agency_url",
                "match_tier",
                "match_evidence",
            ]
        )
        for reporter, match in zip(reporters, matches, strict=True):
            writer.writerow(
                [
                    reporter.ntd_id,
                    reporter.name,
                    reporter.dba,
                    reporter.state,
                    reporter.reporter_type,
                    reporter.organization_type,
                    reporter.url,
                    match.tier,
                    match.evidence,
                ]
            )

    unmatched = [r for r, m in zip(reporters, matches, strict=True) if m.tier == "no_candidate"]
    summary = {
        "unit": "ntd_reporters",
        "unit_note": (
            "Every count here is a count of NTD reporters. The registry counts feed "
            "records, which is a different unit; the two are never added."
        ),
        "report_year": args.report_year,
        "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "obligated_reporters": coverage.obligated,
        "obligated_definition": (
            "NTD reporters with at least one fixed-route mode in Service (by Mode) for "
            "the report year. Deviated fixed route has no distinct NTD mode code, so "
            "this is a lower bound on the population the RY2023 D-10 rule covers."
        ),
        "by_tier": coverage.by_tier,
        "tracked_by_registry": coverage.tracked_by_registry,
        "discoverable_elsewhere": coverage.discoverable_elsewhere,
        "no_candidate_strict": coverage.no_candidate_strict,
        "no_candidate_lenient": coverage.no_candidate_lenient,
        "unmatched_by_state": dict(Counter(r.state for r in unmatched).most_common()),
        "unmatched_by_reporter_type": dict(
            Counter(r.reporter_type for r in unmatched).most_common()
        ),
        "unmatched_by_organization_type": dict(
            Counter(r.organization_type for r in unmatched).most_common()
        ),
        "sources": [
            {
                "name": "FTA NTD Annual Database, Agency Information",
                "url": ROSTER_URL,
                "sha256": roster_raw.sha256,
                "rows": len(roster),
                "license": (
                    "Public domain (US Government work); attribution: "
                    "Federal Transit Administration"
                ),
            },
            {
                "name": "FTA NTD Annual Data View, Service (by Mode)",
                "url": MODE_URL,
                "sha256": mode_raw.sha256,
                "rows": len(modes),
                "license": (
                    "Public domain (US Government work); attribution: "
                    "Federal Transit Administration"
                ),
            },
            {
                "name": "Transitland Atlas",
                "url": ATLAS_URL,
                "sha256": atlas_raw.sha256,
                "license": "CC-BY 4.0, Interline Technologies and contributors",
            },
            {
                "name": "Mobility Database catalog (storage.googleapis.com copy)",
                "url": CATALOG_URL,
                "sha256": catalog_raw.sha256,
                "license": "See mobilitydatabase.org terms; per-feed licences vary",
            },
        ],
    }
    (args.out / f"reporter-coverage-ry{args.report_year}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    print()
    print(f"obligated reporters (RY{args.report_year} fixed route): {coverage.obligated}")
    for tier in TIER_ORDER:
        print(f"  {tier:22} {coverage.by_tier.get(tier, 0)}")
    print(f"tracked in our registry:      {coverage.tracked_by_registry}")
    print(f"discoverable elsewhere only:  {coverage.discoverable_elsewhere}")
    print(
        "no discoverable feed: "
        f"{coverage.no_candidate_lenient} to {coverage.no_candidate_strict} "
        "(lenient to strict matching)"
    )
    print(f"wrote {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
