"""Validate and assemble a citable dataset release from a public site build.

The repository carries a bounded generated snapshot for review and offline
development.  It is not the publication source.  Monthly releases instead use
the deployed Pages projection, whose build hydrates S3 and reapplies the current
registry boundary.  This module makes that handoff fail closed: every tabular
format must describe exactly the current records in the deployed artifact
index, and no retired or unregistered identifier may enter the bundle.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION
from .agencies import load_agencies
from .config import AGENCIES, Agency
from .dataset import COLUMNS, build_quality_dataset, to_csv
from .instance import BASE_URL
from .location import resolve_published_location
from .mobilitydb import canonical_state
from .ntd import (
    AT_RISK,
    NOT_READY,
    READY,
    PortfolioSummary,
    one_fix_from_ready,
    portfolio_summary,
    shapes_portfolio_summary,
)
from .ntd import (
    assess as assess_ntd,
)
from .warehouse import to_parquet

_TEXT_EXPORTS = (
    "catalog.json",
    "catalog.csv",
    "dataset.json",
    "dataset.csv",
    "ntd.json",
)
_CATALOG_CSV_FIELDS = (
    "id",
    "name",
    "state",
    "grade",
    "score",
    "comparison_eligible",
    "size_tier",
    "snapshot_date",
    "days_until_expiry",
    "service_horizon_status",
    "expiry_status",
    "mdb_id",
    "rubric_version",
    "scoring_profile_id",
    "scoring_profile_rubric_version",
    "validator_version",
    "reader_archive_profile",
    "feed_sha256",
    "feed_url",
    "top_fix",
    "scorecard_url",
    "country",
    "subdivision_code",
    "subdivision_name",
)
_NTD_STATUSES = ("ready", "at_risk", "not_ready")
_NTD_PILLARS = ("published", "valid", "current", "agency_id")


class DatasetReleaseError(RuntimeError):
    """The proposed release is incomplete or not the canonical current corpus."""


@dataclass(frozen=True)
class ReleaseSummary:
    """Small release-note facts derived only after all formats agree."""

    agencies: int
    rubric_version: str


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetReleaseError(f"{label} is missing or invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DatasetReleaseError(f"{label} must be a JSON object")
    return value


def _rows_by_id(value: object, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise DatasetReleaseError(f"{label} must be a list")
    rows: dict[str, dict[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, dict):
            raise DatasetReleaseError(f"{label} contains a non-object row")
        agency_id = raw.get("id")
        if not isinstance(agency_id, str) or not agency_id:
            raise DatasetReleaseError(f"{label} contains a row without an id")
        if agency_id in rows:
            raise DatasetReleaseError(f"{label} contains a duplicate id")
        rows[agency_id] = raw
    return rows


def _index_current(index: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    agencies = index.get("agencies")
    if not isinstance(agencies, dict):
        raise DatasetReleaseError("artifact index must contain an agencies object")
    current: dict[str, dict[str, Any]] = {}
    for agency_id, raw_entry in agencies.items():
        if not isinstance(agency_id, str) or not isinstance(raw_entry, dict):
            raise DatasetReleaseError("artifact index contains a malformed agency entry")
        history = raw_entry.get("history")
        if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
            raise DatasetReleaseError("artifact index contains an agency without current history")
        current[agency_id] = history[-1]
    return current


def _require_exact_ids(rows: Mapping[str, object], expected_ids: set[str], label: str) -> None:
    if set(rows) != expected_ids:
        raise DatasetReleaseError(
            f"{label} ids do not exactly match the authoritative current index "
            f"({len(rows)} rows versus {len(expected_ids)})"
        )


def _values_equal(actual: object, expected: object) -> bool:
    if expected is None:
        return actual is None or actual == ""
    if isinstance(expected, bool):
        return actual is expected or str(actual).casefold() == str(expected).casefold()
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        try:
            return float(actual) == float(expected)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    if isinstance(actual, dt.date):
        actual = actual.isoformat()
    return str(actual) == str(expected)


def _require_rows_match(
    rows: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
    fields: Sequence[str],
    field_aliases: Mapping[str, str] | None = None,
    strict_types: bool = False,
) -> None:
    _require_exact_ids(rows, set(expected), label)
    aliases = field_aliases or {}
    for agency_id, expected_row in expected.items():
        row = rows[agency_id]
        for field in fields:
            actual_field = aliases.get(field, field)
            actual = row.get(actual_field)
            expected_value = expected_row.get(field)
            values_match = (
                type(actual) is type(expected_value) and actual == expected_value
                if strict_types
                else _values_equal(actual, expected_value)
            )
            if actual_field not in row or not values_match:
                raise DatasetReleaseError(
                    f"{label} disagrees with the canonical current dataset field {field}"
                )


def _read_csv_rows(path: Path, label: str, fields: Sequence[str]) -> dict[str, dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise DatasetReleaseError(f"{label} columns do not match its format contract")
            return _rows_by_id(list(reader), label)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DatasetReleaseError(f"{label} is missing or invalid CSV: {exc}") from exc


def _read_parquet_rows(
    path: Path, expected: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise DatasetReleaseError("agencies.parquet is missing")
    canonical_path: Path | None = None
    try:
        import duckdb

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as handle:
            canonical_path = Path(handle.name)
        canonical_path.unlink()
        to_parquet([dict(row) for row in expected.values()], str(canonical_path))
        connection = duckdb.connect(":memory:")
        try:
            schema = connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
            canonical_schema = connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(canonical_path)]
            ).fetchall()
            schema_contract = tuple((str(row[0]), str(row[1])) for row in schema)
            canonical_contract = tuple((str(row[0]), str(row[1])) for row in canonical_schema)
            if schema_contract != canonical_contract:
                raise DatasetReleaseError(
                    "agencies.parquet columns or types do not match the canonical dataset contract"
                )
            fields = tuple(name for name, _type in canonical_contract)
            result = connection.execute(
                f"SELECT {', '.join(fields)} FROM read_parquet(?)",  # noqa: S608
                [str(path)],
            ).fetchall()
        finally:
            connection.close()
    except Exception as exc:
        raise DatasetReleaseError(f"agencies.parquet is invalid: {exc}") from exc
    finally:
        if canonical_path is not None:
            canonical_path.unlink(missing_ok=True)
    return _rows_by_id(
        [dict(zip(fields, values, strict=True)) for values in result],
        "agencies.parquet",
    )


def _validated_ntd_counts(value: object, label: str) -> tuple[dict[str, int], int]:
    if not isinstance(value, dict):
        raise DatasetReleaseError(f"{label} must be an object")
    raw_counts = {key: value.get(key) for key in _NTD_STATUSES}
    total = value.get("total")
    if not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in (*raw_counts.values(), total)
    ):
        raise DatasetReleaseError(f"{label} has invalid counts")
    counts = {key: cast(int, raw_counts[key]) for key in _NTD_STATUSES}
    total_count = cast(int, total)
    if total_count != sum(counts.values()):
        raise DatasetReleaseError(f"{label} counts do not add up")
    return counts, total_count


def _validate_ntd_summary(
    value: object,
    label: str,
    *,
    require_breakdown: bool = True,
    require_pct: bool = True,
) -> None:
    counts, total_count = _validated_ntd_counts(value, label)
    value = cast(dict[str, Any], value)
    if require_pct:
        expected_pct = round(counts[READY] / total_count * 100, 1) if total_count else 0.0
        if not _values_equal(value.get("pct_ready"), expected_pct):
            raise DatasetReleaseError(f"{label} ready percentage is inconsistent")
    if not require_breakdown:
        return
    by_state = value.get("by_state")
    if not isinstance(by_state, dict):
        raise DatasetReleaseError(f"{label} has no state breakdown")
    state_counts = Counter[str]()
    for state, raw in by_state.items():
        if not isinstance(state, str) or not state:
            raise DatasetReleaseError(f"{label} has an invalid state key")
        if not isinstance(raw, dict) or set(raw) != {"total", *_NTD_STATUSES}:
            raise DatasetReleaseError(f"{label} state does not match its format contract")
        _validate_ntd_summary(
            raw,
            f"{label} state",
            require_breakdown=False,
            require_pct=False,
        )
        state_counts["total"] += int(raw["total"])
        for status in _NTD_STATUSES:
            state_counts[status] += int(raw[status])
    expected_counts = {"total": total_count, **{status: counts[status] for status in _NTD_STATUSES}}
    if any(state_counts[field] != expected for field, expected in expected_counts.items()):
        raise DatasetReleaseError(f"{label} state counts do not match its national counts")


def _retired_pattern(retired_ids: Iterable[str]) -> re.Pattern[str] | None:
    alternatives = sorted((re.escape(value) for value in retired_ids), key=len, reverse=True)
    if not alternatives:
        return None
    return re.compile(
        rf"(?<![a-z0-9_-])(?:{'|'.join(alternatives)})(?![a-z0-9_-])",
        flags=re.IGNORECASE,
    )


def _require_no_retired_references(web_root: Path, retired_ids: set[str]) -> None:
    pattern = _retired_pattern(retired_ids)
    if pattern is None:
        return
    for relative in _TEXT_EXPORTS:
        path = web_root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DatasetReleaseError(f"{relative} is missing or unreadable: {exc}") from exc
        if pattern.search(text):
            raise DatasetReleaseError(f"{relative} cites a retired registry identifier")


def _validate_catalog_surfaces(
    *,
    catalog_doc: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]],
    catalog_csv: Mapping[str, Mapping[str, Any]],
    expected_rows: Mapping[str, Mapping[str, Any]],
    current_registry: Mapping[str, Agency],
) -> None:
    expected_metadata = {
        "source": BASE_URL,
        "schema_version": SCHEMA_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
    }
    for field, expected_value in expected_metadata.items():
        if (
            type(catalog_doc.get(field)) is not type(expected_value)
            or catalog_doc.get(field) != expected_value
        ):
            raise DatasetReleaseError(
                f"catalog.json {field} disagrees with the publication contract"
            )

    _require_rows_match(
        catalog,
        expected_rows,
        label="catalog.json",
        fields=COLUMNS,
        field_aliases={"date": "snapshot_date"},
        strict_types=True,
    )
    _require_rows_match(
        catalog_csv,
        catalog,
        label="catalog.csv",
        fields=_CATALOG_CSV_FIELDS,
    )
    for agency_id, agency in current_registry.items():
        if agency_id not in catalog:
            continue
        row = catalog[agency_id]
        if row.get("feed_url") != agency.static_gtfs_url:
            raise DatasetReleaseError("catalog.json feed URL disagrees with the registry")
        location = resolve_published_location(
            registry_country=agency.country,
            registry_subdivision_code=agency.subdivision_code,
            registry_subdivision_name=agency.subdivision_name,
            legacy_state=agency.state,
        )
        expected_state = agency.state.strip()
        if not expected_state and location.country_code == "US":
            expected_state = canonical_state(location.subdivision_name)
        expected_geography = {
            "country": location.country_code,
            "state": expected_state,
            "subdivision_code": location.subdivision_code,
            "subdivision_name": location.subdivision_name,
        }
        if any(
            str(row.get(field) or "") != expected for field, expected in expected_geography.items()
        ):
            raise DatasetReleaseError(
                "catalog.json geography disagrees with the canonical registry"
            )

    rubric_versions = sorted(
        {str(row.get("rubric_version") or "").strip() or "unknown" for row in catalog.values()}
    )
    catalog_rubric = rubric_versions[0] if len(rubric_versions) == 1 else "mixed"
    if (
        catalog_doc.get("rubric_version") != catalog_rubric
        or catalog_doc.get("rubric_versions") != rubric_versions
    ):
        raise DatasetReleaseError("catalog.json rubric metadata disagrees with its rows")


def _validate_one_fix_rows(
    ntd_doc: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]],
    expected_ids: set[str],
    canonical_artifacts: Sequence[dict[str, Any]],
) -> None:
    one_fix = _rows_by_id(ntd_doc.get("one_fix_from_ready", []), "ntd.json one-fix rows")
    if not set(one_fix) <= expected_ids:
        raise DatasetReleaseError("ntd.json cites a record outside the current index")
    one_fix_total = ntd_doc.get("one_fix_total")
    if (
        not isinstance(one_fix_total, int)
        or isinstance(one_fix_total, bool)
        or one_fix_total < 0
        or len(one_fix) != min(one_fix_total, 40)
    ):
        raise DatasetReleaseError("ntd.json one-fix count is inconsistent")
    nonready_us_rows = sum(
        1
        for row in catalog.values()
        if row.get("country") == "US" and row.get("ntd_ready") in {AT_RISK, NOT_READY}
    )
    if one_fix_total > nonready_us_rows:
        raise DatasetReleaseError("ntd.json one-fix total exceeds its eligible catalog rows")
    for agency_id, row in one_fix.items():
        catalog_row = catalog[agency_id]
        if set(row) != {"id", "name", "state", "pillar", "fix", "status"}:
            raise DatasetReleaseError("ntd.json one-fix row does not match its format contract")
        for field, catalog_field in (
            ("name", "name"),
            ("state", "state"),
            ("status", "ntd_ready"),
        ):
            if not _values_equal(row.get(field), catalog_row.get(catalog_field)):
                raise DatasetReleaseError(f"ntd.json one-fix {field} disagrees with catalog.json")
        _validate_one_fix_contract(row, catalog_row)

    expected = one_fix_from_ready(list(canonical_artifacts))
    if one_fix_total != len(expected) or list(one_fix.values()) != expected[:40]:
        raise DatasetReleaseError(
            "ntd.json one-fix rows disagree with the canonical current artifacts"
        )


def _validate_one_fix_contract(row: Mapping[str, Any], catalog_row: Mapping[str, Any]) -> None:
    """Regenerate a visible row's pillar wording with the production assessor."""
    pillar_key = row.get("pillar")
    fix = row.get("fix")
    if pillar_key not in _NTD_PILLARS or not isinstance(fix, str) or not fix.strip():
        raise DatasetReleaseError("ntd.json one-fix pillar or fix is invalid")

    artifact: dict[str, Any] = {
        "agency": {"country": "US"},
        "feed": {"static_url": catalog_row.get("feed_url"), "reachable": True},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {
                "details": {
                    "days_until_expiry": catalog_row.get("days_until_expiry"),
                    "service_horizon_status": catalog_row.get("service_horizon_status"),
                }
            },
        },
        "snapshot_date": catalog_row.get("snapshot_date"),
        "ntd_id_alignment": {"feed_agency_ids": ["present"]},
    }
    if pillar_key == "published":
        artifact["feed"]["reachable"] = False
    elif pillar_key == "valid":
        error_match = re.fullmatch(r"([1-9][0-9]*) validator errors? to resolve\.", fix)
        if error_match is None:
            raise DatasetReleaseError("ntd.json one-fix fix is not canonical assessor text")
        artifact["categories"]["correctness"]["findings"] = [{"severity": "ERROR"}] * int(
            error_match.group(1)
        )
    elif pillar_key == "agency_id":
        artifact["ntd_id_alignment"]["feed_agency_ids"] = []

    failing = [pillar for pillar in assess_ntd(artifact).pillars if pillar.status != READY]
    if (
        len(failing) != 1
        or failing[0].key != pillar_key
        or failing[0].status != row.get("status")
        or failing[0].detail != fix
    ):
        raise DatasetReleaseError("ntd.json one-fix pillar or fix is not canonical")


def _expected_ntd_summary(
    catalog: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    counts = Counter[str]()
    by_state: dict[str, Counter[str]] = {}
    for row in catalog.values():
        country = row.get("country")
        status = row.get("ntd_ready")
        if country == "US":
            if status not in _NTD_STATUSES:
                raise DatasetReleaseError("catalog.json has an invalid US NTD readiness status")
            state = str(row.get("state") or "").strip() or "Unlocated"
            counts[cast(str, status)] += 1
            by_state.setdefault(state, Counter())[cast(str, status)] += 1
        elif "ntd_ready" not in row or status is not None:
            raise DatasetReleaseError("catalog.json must use null NTD readiness outside the US")

    total = sum(counts[status] for status in _NTD_STATUSES)
    return {
        "total": total,
        **{status: counts[status] for status in _NTD_STATUSES},
        "pct_ready": round(counts[READY] / total * 100, 1) if total else 0.0,
        "by_state": {
            state: {
                "total": sum(state_counts[status] for status in _NTD_STATUSES),
                **{status: state_counts[status] for status in _NTD_STATUSES},
            }
            for state, state_counts in sorted(by_state.items())
        },
    }


def _require_ntd_summary_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    for field in (*_NTD_STATUSES, "total", "pct_ready", "by_state"):
        if actual.get(field) != expected.get(field):
            raise DatasetReleaseError(f"{label} disagrees with the canonical catalog rollup")


def _summary_payload(summary: PortfolioSummary) -> dict[str, Any]:
    return {
        "total": summary.total,
        "ready": summary.ready,
        "at_risk": summary.at_risk,
        "not_ready": summary.not_ready,
        "pct_ready": summary.pct_ready,
        "by_state": summary.by_state,
    }


def _canonical_ntd_artifacts(
    *,
    artifacts_root: Path,
    current: Mapping[str, Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Load full indexed-current artifacts and bind them to release rows.

    ``index.json`` intentionally carries only compact trend points. Those points
    cannot independently establish one-fix eligibility or shapes.txt coverage,
    so a release must also provide every corresponding full ``latest.json``.
    """
    from .publish import _history_entry

    canonical: list[dict[str, Any]] = []
    for agency_id in sorted(current):
        artifact = _read_json(
            artifacts_root / agency_id / "latest.json",
            f"canonical current artifact {agency_id}",
        )
        agency = artifact.get("agency")
        if not isinstance(agency, dict) or agency.get("id") != agency_id:
            raise DatasetReleaseError(
                f"canonical current artifact identity disagrees with the index for {agency_id}"
            )
        try:
            compact = _history_entry(artifact)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise DatasetReleaseError(
                f"canonical current artifact is malformed for {agency_id}: {exc}"
            ) from exc
        if any(compact.get(field) != value for field, value in current[agency_id].items()):
            raise DatasetReleaseError(
                f"canonical current artifact disagrees with the index for {agency_id}"
            )

        catalog_row = catalog[agency_id]
        feed = artifact.get("feed")
        if not isinstance(feed, dict) or feed.get("static_url") != catalog_row.get("feed_url"):
            raise DatasetReleaseError(
                f"canonical current artifact feed URL disagrees with catalog.json for {agency_id}"
            )

        normalized = copy.deepcopy(artifact)
        normalized_agency = normalized["agency"]
        normalized_agency["name"] = catalog_row.get("name")
        normalized_agency["state"] = catalog_row.get("state")
        normalized_agency["country"] = catalog_row.get("country")
        if normalized_agency["country"] == "US":
            status = assess_ntd(normalized).status
            if status != catalog_row.get("ntd_ready"):
                raise DatasetReleaseError(
                    "canonical current artifact NTD readiness disagrees with catalog.json"
                )
        canonical.append(normalized)
    return canonical


def _validate_ntd_document(
    ntd_doc: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]],
    expected_ids: set[str],
    canonical_artifacts: Sequence[dict[str, Any]],
) -> None:
    _validate_ntd_summary(ntd_doc, "ntd.json")
    _validate_ntd_summary(ntd_doc.get("shapes"), "ntd.json shapes")
    expected_summary = _expected_ntd_summary(catalog)
    _require_ntd_summary_matches(ntd_doc, expected_summary, "ntd.json")
    canonical_summary = _summary_payload(portfolio_summary(list(canonical_artifacts)))
    _require_ntd_summary_matches(ntd_doc, canonical_summary, "ntd.json")
    canonical_shapes = _summary_payload(shapes_portfolio_summary(list(canonical_artifacts)))
    if ntd_doc.get("shapes") != canonical_shapes:
        raise DatasetReleaseError("ntd.json shapes disagree with the canonical current artifacts")
    _validate_one_fix_rows(ntd_doc, catalog, expected_ids, canonical_artifacts)


def validate_release_inputs(
    *,
    artifacts_root: Path,
    web_root: Path,
    current_registry: Mapping[str, Agency],
    retired_registry_ids: set[str],
) -> ReleaseSummary:
    """Validate every release format against one canonical current dataset."""
    index = _read_json(artifacts_root / "index.json", "artifact index")
    current = _index_current(index)
    expected_ids = set(current)
    if not expected_ids:
        raise DatasetReleaseError("authoritative current index is empty")
    if not expected_ids <= set(current_registry):
        raise DatasetReleaseError("artifact index contains retired or unregistered ids")

    expected_dataset = build_quality_dataset(index, agencies=current_registry.values())
    expected_rows = _rows_by_id(expected_dataset.get("rows"), "canonical dataset rows")
    _require_exact_ids(expected_rows, expected_ids, "canonical dataset")

    catalog_doc = _read_json(web_root / "catalog.json", "catalog.json")
    dataset_doc = _read_json(web_root / "dataset.json", "dataset.json")
    ntd_doc = _read_json(web_root / "ntd.json", "ntd.json")
    if dataset_doc != expected_dataset:
        raise DatasetReleaseError(
            "dataset.json does not equal the canonical dataset rebuilt from the index"
        )
    catalog = _rows_by_id(catalog_doc.get("agencies"), "catalog.json agencies")
    dataset = _rows_by_id(dataset_doc.get("rows"), "dataset.json rows")
    catalog_csv = _read_csv_rows(web_root / "catalog.csv", "catalog.csv", _CATALOG_CSV_FIELDS)
    dataset_csv = _read_csv_rows(web_root / "dataset.csv", "dataset.csv", COLUMNS)
    parquet = _read_parquet_rows(web_root / "api" / "v1" / "agencies.parquet", expected_rows)

    try:
        csv_text = (web_root / "dataset.csv").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DatasetReleaseError(f"dataset.csv is unreadable: {exc}") from exc
    if csv_text != to_csv(expected_dataset):
        raise DatasetReleaseError("dataset.csv is not the canonical dataset serialization")

    _require_rows_match(dataset, expected_rows, label="dataset.json", fields=COLUMNS)
    _require_rows_match(dataset_csv, expected_rows, label="dataset.csv", fields=COLUMNS)
    _require_rows_match(parquet, expected_rows, label="agencies.parquet", fields=COLUMNS)
    _validate_catalog_surfaces(
        catalog_doc=catalog_doc,
        catalog=catalog,
        catalog_csv=catalog_csv,
        expected_rows=expected_rows,
        current_registry=current_registry,
    )
    canonical_artifacts = _canonical_ntd_artifacts(
        artifacts_root=artifacts_root,
        current=current,
        catalog=catalog,
    )
    _validate_ntd_document(ntd_doc, catalog, expected_ids, canonical_artifacts)
    _require_no_retired_references(web_root, retired_registry_ids)
    rubric = str(catalog_doc.get("rubric_version") or "unknown")
    return ReleaseSummary(agencies=len(expected_ids), rubric_version=rubric)


def assemble_release_bundle(
    *,
    artifacts_root: Path,
    web_root: Path,
    repo_root: Path,
    bundle_root: Path,
    current_registry: Mapping[str, Agency],
    retired_registry_ids: set[str],
) -> ReleaseSummary:
    """Validate all inputs first, then copy the complete flat release bundle."""
    summary = validate_release_inputs(
        artifacts_root=artifacts_root,
        web_root=web_root,
        current_registry=current_registry,
        retired_registry_ids=retired_registry_ids,
    )
    if bundle_root.exists() and any(bundle_root.iterdir()):
        raise DatasetReleaseError("release bundle destination is not empty")
    bundle_root.mkdir(parents=True, exist_ok=True)
    sources = {
        "catalog.json": web_root / "catalog.json",
        "catalog.csv": web_root / "catalog.csv",
        "dataset.json": web_root / "dataset.json",
        "dataset.csv": web_root / "dataset.csv",
        "agencies.parquet": web_root / "api" / "v1" / "agencies.parquet",
        "ntd.json": web_root / "ntd.json",
        "DATA-DICTIONARY.md": repo_root / "docs" / "api.md",
        "CITATION.cff": repo_root / "CITATION.cff",
    }
    for destination, source in sources.items():
        if not source.is_file():
            raise DatasetReleaseError(f"required release input is missing: {destination}")
    for destination, source in sources.items():
        shutil.copy2(source, bundle_root / destination)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate and assemble a dataset release")
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        load_agencies()
        current_registry = {
            agency_id: agency for agency_id, agency in AGENCIES.items() if agency.is_canonical_feed
        }
        summary = assemble_release_bundle(
            artifacts_root=args.artifacts_root.resolve(),
            web_root=args.web_root.resolve(),
            repo_root=args.repo_root.resolve(),
            bundle_root=args.bundle_root.resolve(),
            current_registry=current_registry,
            retired_registry_ids=set(AGENCIES) - set(current_registry),
        )
    except DatasetReleaseError as exc:
        print(f"Dataset release refused: {exc}", file=sys.stderr)
        return 2
    print(
        f"Validated dataset release for {summary.agencies} current records "
        f"(rubric {summary.rubric_version})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
