"""Cut the public sample a marketplace listing shows (docs/data-marketplace.md).

A listing's sample is visible to anyone before they subscribe, so it is a
small, ordinary slice: every row of both tables for a few named feed records,
as CSV (Data Exchange previews CSV samples on the product page). Pick records
whose publishers state an open license; every number in the slice is already
free on those records' scorecard pages.

    uv run scorecard history-export --out ../history-out --zip ../history.zip
    uv run python scripts/build_marketplace_sample.py --tables ../history-out \\
        --out ../marketplace-sample nps-yosemite another-id
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

#: Data Exchange allows up to 10 samples of at most 50 MB each.
MAX_SAMPLE_BYTES = 50 * 1024 * 1024


def build(tables: Path, out: Path, agency_ids: list[str]) -> list[Path]:
    """Write sample-checks.csv and sample-findings.csv for ``agency_ids``."""
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    written = []
    for table, order in (
        ("checks", "agency_id, snapshot_date"),
        ("findings", "agency_id, snapshot_date, category, finding_index"),
    ):
        target = out / f"sample-{table}.csv"
        relation = con.sql(
            f"SELECT * FROM read_parquet(?) WHERE agency_id IN (SELECT unnest(?)) ORDER BY {order}",  # noqa: S608
            params=[str(tables / f"{table}.parquet"), agency_ids],
        )
        relation.write_csv(str(target), header=True)
        if target.stat().st_size > MAX_SAMPLE_BYTES:
            raise SystemExit(f"{target} is over the 50 MB sample limit; name fewer records")
        written.append(target)
    found = con.sql(
        "SELECT count(DISTINCT agency_id) FROM read_csv_auto(?)",
        params=[str(out / "sample-checks.csv")],
    ).fetchone()
    if not found or found[0] != len(set(agency_ids)):
        raise SystemExit("not every named record has rows in this build; check the ids")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tables", type=Path, required=True, help="a history-export --out dir")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("agency_ids", nargs="+")
    args = parser.parse_args()
    for path in build(args.tables, args.out, args.agency_ids):
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
