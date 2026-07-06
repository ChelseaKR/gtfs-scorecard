"""Cross-agency query layer over the published data (ADR 0013).

The static API serves the bounded cross-agency endpoints. The next tier, for
arbitrary filters and joins, is a query engine over the same artifacts, not an
always-on database. DuckDB is that engine: embedded, no server, and it reads JSON
and writes Parquet directly, so a query runs against the published dataset in
process and pays nothing when idle.

This module loads the dataset rows into an in-memory DuckDB table named
``agencies`` and runs SQL against it, and exports the same rows as Parquet so a
DuckDB or Athena consumer can query the national table without this code at all.
DuckDB is an optional dependency (the ``query`` extra); the core pipeline never
imports it, and these functions raise a clear error if it is missing.

The row-shaping is pure and unit-tested; the engine calls are thin.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb

# The dataset's columns, as a stable view definition. Sourced from the dataset
# module so the SQL schema and the JSON table never drift apart.
TABLE = "agencies"


def _require_duckdb() -> Any:
    try:
        import duckdb
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via the CLI
        raise RuntimeError(
            "The query layer needs DuckDB. Install it with: pip install 'scorecard-pipeline[query]'"
        ) from exc
    return duckdb


def _load(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Register the dataset rows as the ``agencies`` table.

    The rows are written to a temporary JSON array and read back with DuckDB's
    JSON reader, which infers the column types. This keeps the dependency to
    DuckDB alone (no pandas or pyarrow) and handles nulls (a missing realtime
    score) the same way the dataset does.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(rows or [{}], tmp)
        tmp_path = tmp.name
    try:
        # TABLE is a module constant ("agencies"), not user input, and the path
        # is a bound parameter, so Semgrep's sqlalchemy-execute-raw-query rule
        # is a false positive here.
        # nosemgrep
        con.execute(
            f"CREATE TABLE {TABLE} AS SELECT * FROM read_json(?, format='array')",  # noqa: S608
            [tmp_path],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def query_rows(rows: list[dict[str, Any]], sql: str) -> list[dict[str, Any]]:
    """Run a SQL query against the dataset rows, returning a list of row dicts.

    The dataset is exposed as a table named ``agencies``. Read-only by nature:
    the table is in-memory and discarded when the call returns.
    """
    duckdb = _require_duckdb()
    con = duckdb.connect()
    try:
        _load(con, rows)
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, record, strict=False)) for record in cur.fetchall()]
    finally:
        con.close()


def to_parquet(rows: list[dict[str, Any]], out_path: str) -> str:
    """Write the dataset rows to a Parquet file for warehouse consumers.

    A single national table a DuckDB or Athena user can query directly:
    ``SELECT grade, count(*) FROM 'agencies.parquet' GROUP BY grade``.
    """
    duckdb = _require_duckdb()
    con = duckdb.connect()
    try:
        _load(con, rows)
        # TABLE is a module constant ("agencies"), not user input, and the
        # output path is a bound parameter, so Semgrep's
        # sqlalchemy-execute-raw-query rule is a false positive here.
        # nosemgrep
        con.execute(
            f"COPY (SELECT * FROM {TABLE}) TO ? (FORMAT PARQUET)",  # noqa: S608
            [out_path],
        )
    finally:
        con.close()
    return out_path


def duckdb_available() -> bool:
    """Whether the query extra is installed, so callers can skip the Parquet
    export without failing when DuckDB is absent."""
    try:
        import duckdb  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True
