"""Tests for the scorecard history tables (ADR 0063, docs/history-tables.md).

The fixture is a small artifact tree with the shapes the corpus actually
holds: a full score, an intraday freshness sweep, a record with a share-alike
license block, one whose block contradicts itself, one with no block at all,
one on the opt-out ledger, an unreadable dated file, a non-dated file, and an
unregistered directory. The tests hold the rows to what each shape must
produce, the tables to their dictionary and the doc, the doc's license text to
the module's, the exclusion and license-notice rules, and determinism.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline.agencies import load_agencies
from scorecard_pipeline.cli import main
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.history_export import (
    CHECKS_COLUMNS,
    DICTIONARY_FILENAME,
    EXCLUSIONS_FILENAME,
    FINDINGS_COLUMNS,
    LICENSE_FILENAME,
    LICENSE_TEXT,
    PROVENANCE_FILENAME,
    Counters,
    Exclusions,
    HistoryExportError,
    check_row,
    export_files,
    export_history,
    finding_rows,
    iter_rows,
    parse_exclusions,
    read_exclusions,
    render_dictionary,
    rows_digest,
)
from scorecard_pipeline.license_notice import notice_for_agency
from scorecard_pipeline.score import published_overall
from scorecard_pipeline.warehouse import duckdb_available

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "history-tables.md"
LEDGER = REPO_ROOT / EXCLUSIONS_FILENAME

needs_duckdb = pytest.mark.skipif(
    not duckdb_available(), reason="DuckDB (query extra) not installed"
)

ALPHA = "alpha-transit"
BETA = "beta-transit"
DELTA = "delta-transit"
GAMMA = "gamma-transit"
UNLISTED = "zeta-unlisted"

_REGISTRY: dict[str, Any] = {
    "agencies": [
        {
            "id": ALPHA,
            "name": "Alpha Transit",
            "static_gtfs_url": "https://alpha.example/gtfs.zip",
            "license_note": "CC BY 4.0, per the publisher's open data page.",
            "mdb_id": "mdb-101",
            "ntd_id": "90101",
            "license": {
                "id": "CC-BY-4.0",
                "attribution_required": True,
                "redistribution_allowed": True,
                "share_alike": False,
                "status": "unreviewed",
                "terms_url": "https://alpha.example/terms",
                "attribution": "Data provided by Alpha Transit.",
            },
        },
        {
            "id": BETA,
            "name": "Beta Transit",
            "static_gtfs_url": "https://beta.example/gtfs.zip",
            "license_note": "ODbL 1.0.",
            "license": {
                "id": "ODbL-1.0",
                "attribution_required": True,
                "redistribution_allowed": "unknown",
                "share_alike": True,
                "status": "unreviewed",
                "terms_url": "https://beta.example/odbl",
                "attribution": "Contains data from Beta Transit.",
            },
        },
        {
            "id": DELTA,
            "name": "Delta Transit",
            "static_gtfs_url": "https://delta.example/gtfs.zip",
            "license_note": "CC BY 4.0.",
            # Marked share-alike for a license that is not: the lint reports it
            # and the notice must not name CC BY as share-alike.
            "license": {
                "id": "CC-BY-4.0",
                "attribution_required": True,
                "redistribution_allowed": True,
                "share_alike": True,
                "status": "unreviewed",
            },
        },
        {
            "id": GAMMA,
            "name": "Gamma Transit",
            "static_gtfs_url": "https://gamma.example/gtfs.zip",
            "license_note": "No stated data license in the Mobility Database.",
        },
    ]
}


def _finding(
    code: str, count: int, points: float, *, reach: dict[str, Any] | None = None
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "code": code,
        "count": count,
        "points": points,
        "severity": "WARNING",
        "owner": "Likely your team",
        "what": "plain language",
        "why": "plain language",
        "fix": "plain language",
        "effort": "One setting.",
    }
    if reach is not None:
        finding["consequence"] = {"code": code, "reach": reach, "line": "", "absences": []}
    return finding


def _artifact(
    agency_id: str,
    name: str,
    date: str,
    score: float,
    *,
    schema_version: str = "1.19",
    recompute: dict[str, Any] | None = None,
    realtime: float | None = None,
    reach: bool = False,
) -> dict[str, Any]:
    overall = published_overall(score)
    artifact: dict[str, Any] = {
        "schema_version": schema_version,
        "rubric_version": "1.3",
        "scoring_profile": {"id": "gtfs-scorecard-1.3", "rubric_version": "1.3"},
        "validator_version": "8.0.1",
        "agency": {
            "id": agency_id,
            "name": name,
            "country": "US",
            "subdivision_code": "US-CA",
            "subdivision_name": "California",
        },
        "generated_at": f"{date}T13:25:01+00:00",
        "snapshot_date": date,
        "feed": {
            "static_url": f"https://{agency_id}.example/gtfs.zip",
            "sha256": hashlib.sha256(f"{agency_id}-{date}".encode()).hexdigest(),
            "size_bytes": 4096,
            "source_provenance": "official",
        },
        "fetch": {"source": "origin", "final_url": f"https://{agency_id}.example/gtfs.zip"},
        "confidence": {"level": "high"},
        "geo": {"stop_count": 374},
        "mode_profile": {"measured": True, "graded": False, "primary_mode": "bus"},
        "overall": {"score": overall["score"], "grade": overall["grade"]},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 90.0,
                "findings": [
                    _finding(
                        "stop_too_far_from_shape",
                        4,
                        4.0,
                        reach=(
                            {
                                "basis": "stops",
                                "basis_label": "stops",
                                "affected": 4,
                                "total": 374,
                                "share": 0.0107,
                                "total_source": "geo.stop_count",
                                "reason": "",
                            }
                            if reach
                            else None
                        ),
                    )
                ],
                "details": {},
            },
            "freshness": {
                "status": "measured",
                "score": 36.7,
                "findings": [_finding("scorecard_feed_expires_soon", 1, 60.0)],
                "details": {
                    "days_until_expiry": 12,
                    "effective_expiry_date": "2026-07-13",
                    "service_horizon_status": "within_review_threshold",
                },
            },
            "completeness": {
                "status": "measured",
                "score": 62.4,
                "findings": [_finding("scorecard_wheelchair_boarding_unknown", 2, 0.1)],
                "details": {},
            },
            "realtime": (
                {"status": "measured", "score": realtime, "findings": [], "details": {}}
                if realtime is not None
                else {"status": "not_yet_measured", "summary": "Not yet published.", "weight": 0.2}
            ),
        },
        "top_fixes": [
            {"rank": 1, "code": "scorecard_feed_expires_soon", "count": 1},
            {"rank": 2, "code": "stop_too_far_from_shape", "count": 4},
        ],
    }
    if recompute is not None:
        artifact["recompute"] = recompute
    return artifact


def _write(root: Path, agency_id: str, artifact: dict[str, Any]) -> None:
    target = root / agency_id / f"{artifact['snapshot_date']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, sort_keys=True))


@pytest.fixture
def repo(isolated_repo_root: Path) -> Path:
    """A throwaway repository root: registry, artifacts, and an exclusion ledger."""
    root = isolated_repo_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "agencies.yaml").write_text(yaml.safe_dump(_REGISTRY, sort_keys=False))
    artifacts = root / "data" / "artifacts"
    _write(artifacts, ALPHA, _artifact(ALPHA, "Alpha Transit", "2026-07-01", 74.4, reach=True))
    _write(
        artifacts,
        ALPHA,
        _artifact(
            ALPHA,
            "Alpha Transit",
            "2026-07-03",
            71.9,
            schema_version="1.4",
            recompute={
                "kind": "freshness",
                "as_of": "2026-07-03",
                "feed_fetched_date": "2026-07-01",
            },
        ),
    )
    (artifacts / ALPHA / "2026-07-02.json").write_text("{not json")
    (artifacts / ALPHA / "latest.json").write_text(
        json.dumps(_artifact(ALPHA, "Alpha", "2026-07-03", 1.0))
    )
    _write(artifacts, BETA, _artifact(BETA, "Beta Transit", "2026-07-01", 88.0, realtime=95.0))
    _write(artifacts, DELTA, _artifact(DELTA, "Delta Transit", "2026-07-01", 55.0))
    _write(artifacts, GAMMA, _artifact(GAMMA, "Gamma Transit", "2026-07-01", 60.0))
    _write(artifacts, GAMMA, _artifact(GAMMA, "Gamma Transit", "2026-07-02", 61.0))
    _write(artifacts, UNLISTED, _artifact(UNLISTED, "Zeta", "2026-07-01", 50.0))
    (root / EXCLUSIONS_FILENAME).write_text(
        yaml.safe_dump(
            {
                "excluded": [
                    {
                        "agency_id": GAMMA,
                        "requested_on": "2026-10-01",
                        "reason": "Publisher asked by email to be left out of the paid tables.",
                    }
                ]
            }
        )
    )
    load_agencies()
    return root


def _rows(
    repo: Path, *, ledger: Exclusions | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counters]:
    counters = Counters()
    exclusions = ledger if ledger is not None else read_exclusions(repo / EXCLUSIONS_FILENAME)
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for row, rows in iter_rows(
        repo / "data" / "artifacts", agencies=AGENCIES, exclusions=exclusions, counters=counters
    ):
        checks.append(row)
        findings.extend(rows)
    return checks, findings, counters


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


# --- shape ---------------------------------------------------------------------


def test_column_names_are_unique_and_the_dictionary_lists_each_once() -> None:
    for columns in (CHECKS_COLUMNS, FINDINGS_COLUMNS):
        names = [column.name for column in columns]
        assert len(names) == len(set(names))
    dictionary = render_dictionary()
    checks_part, findings_part = dictionary.split("## findings.parquet", 1)
    for part, columns in ((checks_part, CHECKS_COLUMNS), (findings_part, FINDINGS_COLUMNS)):
        for column in columns:
            assert part.count(f"| `{column.name}` |") == 1, column.name


def test_the_doc_names_every_column_and_no_other() -> None:
    text = DOC.read_text()
    checks_section = text.split("### checks", 1)[1].split("### findings", 1)[0]
    findings_section = text.split("### findings", 1)[1].split("## The license", 1)[0]
    for section, columns in (
        (checks_section, CHECKS_COLUMNS),
        (findings_section, FINDINGS_COLUMNS),
    ):
        documented = set(re.findall(r"`([a-z0-9_]+)`", section))
        assert documented == {column.name for column in columns}


def test_the_doc_carries_the_license_text_verbatim_and_says_not_on_sale() -> None:
    text = DOC.read_text()
    begin = "<!-- history-license:begin -->\n"
    end = "<!-- history-license:end -->"
    assert text.count(begin) == 1 and text.count(end) == 1
    body = text.split(begin, 1)[1].split(end, 1)[0]
    assert body == LICENSE_TEXT
    assert "Not yet on sale" in text
    assert "not for sale" in text


def test_export_files_are_the_five_the_doc_describes(tmp_path: Path) -> None:
    assert export_files(tmp_path) == (
        "checks.parquet",
        "findings.parquet",
        DICTIONARY_FILENAME,
        LICENSE_FILENAME,
        PROVENANCE_FILENAME,
    )


# --- rows ------------------------------------------------------------------------


def test_golden_rows_for_the_fixture(repo: Path) -> None:
    checks, findings, counters = _rows(repo)
    assert [(row["agency_id"], row["snapshot_date"]) for row in checks] == [
        (ALPHA, "2026-07-01"),
        (ALPHA, "2026-07-03"),
        (BETA, "2026-07-01"),
        (DELTA, "2026-07-01"),
    ]
    first = checks[0]
    expected = {
        "agency_id": ALPHA,
        "agency_name": "Alpha Transit",
        "country": "US",
        "subdivision_code": "US-CA",
        "subdivision_name": "California",
        "mdb_id": "mdb-101",
        "ntd_id": "90101",
        "snapshot_date": "2026-07-01",
        "generated_at": "2026-07-01T13:25:01+00:00",
        "recompute_kind": None,
        "feed_fetched_date": "2026-07-01",
        "artifact_schema_version": "1.19",
        "rubric_version": "1.3",
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": "1.3",
        "validator_version": "8.0.1",
        "reader_archive_profile": "raw-v1",
        "grade": "C",
        "score": 74.4,
        "correctness": 90.0,
        "freshness": 36.7,
        "completeness": 62.4,
        "realtime": None,
        "categories_measured": 3,
        "confidence_level": "high",
        "days_until_expiry": 12,
        "effective_expiry_date": "2026-07-13",
        "expiry_status": "expiring_soon",
        "service_horizon_status": "within_review_threshold",
        "feed_sha256": hashlib.sha256(f"{ALPHA}-2026-07-01".encode()).hexdigest(),
        "feed_size_bytes": 4096,
        "feed_static_url": "https://alpha-transit.example/gtfs.zip",
        "fetch_source": "origin",
        "fetch_final_url": "https://alpha-transit.example/gtfs.zip",
        "source_provenance": "official",
        "stop_count": 374,
        "primary_mode": "bus",
        "finding_count": 3,
        "top_fix_code": "scorecard_feed_expires_soon",
        "license_id": "CC-BY-4.0",
        "license_status": "unreviewed",
        "attribution_required": "true",
        "redistribution_allowed": "true",
        "share_alike": "false",
        "license_terms_url": "https://alpha.example/terms",
        "publisher_credit": "Data provided by Alpha Transit.",
        "license_note": "CC BY 4.0, per the publisher's open data page.",
        "license_notice": None,
    }
    assert first == expected
    assert list(first) == [column.name for column in CHECKS_COLUMNS]

    alpha_findings = [
        row
        for row in findings
        if row["agency_id"] == ALPHA and row["snapshot_date"] == "2026-07-01"
    ]
    assert alpha_findings[0] == {
        "agency_id": ALPHA,
        "snapshot_date": "2026-07-01",
        "category": "correctness",
        "finding_index": 0,
        "code": "stop_too_far_from_shape",
        "severity": "WARNING",
        "count": 4,
        "points": 4.0,
        "owner": "Likely your team",
        "top_fix_rank": 2,
        "reach_basis": "stops",
        "reach_affected": 4,
        "reach_total": 374,
        "reach_share": 0.0107,
        "reach_reason": None,
    }
    assert list(alpha_findings[0]) == [column.name for column in FINDINGS_COLUMNS]
    assert [(row["category"], row["code"], row["top_fix_rank"]) for row in alpha_findings] == [
        ("correctness", "stop_too_far_from_shape", 2),
        ("freshness", "scorecard_feed_expires_soon", 1),
        ("completeness", "scorecard_wheelchair_boarding_unknown", None),
    ]
    assert counters.feed_records == 3
    assert counters.artifacts_read == 4
    assert counters.artifacts_unreadable == 1
    assert counters.first_snapshot == "2026-07-01"
    assert counters.last_snapshot == "2026-07-03"
    assert counters.artifact_schema_versions == {"1.19": 3, "1.4": 1}


def test_a_sweep_row_says_so_and_dates_its_bytes(repo: Path) -> None:
    checks, _findings, _counters = _rows(repo)
    sweep = checks[1]
    assert sweep["snapshot_date"] == "2026-07-03"
    assert sweep["recompute_kind"] == "freshness"
    assert sweep["feed_fetched_date"] == "2026-07-01"
    assert sweep["artifact_schema_version"] == "1.4"


def test_a_measured_realtime_score_is_a_number_and_an_unmeasured_one_is_null(repo: Path) -> None:
    checks, _findings, _counters = _rows(repo)
    by_id = {row["agency_id"]: row for row in checks}
    assert by_id[BETA]["realtime"] == 95.0
    assert by_id[BETA]["categories_measured"] == 4
    assert by_id[ALPHA]["realtime"] is None


def test_reach_fields_are_null_before_the_consequence_block_existed(repo: Path) -> None:
    _checks, findings, _counters = _rows(repo)
    older = next(row for row in findings if row["snapshot_date"] == "2026-07-03")
    assert older["reach_basis"] is None
    assert older["reach_share"] is None
    assert older["reach_reason"] is None


def test_an_unregistered_directory_and_a_non_dated_file_produce_no_rows(repo: Path) -> None:
    checks, _findings, _counters = _rows(repo)
    assert UNLISTED not in {row["agency_id"] for row in checks}
    assert all(row["score"] != 1.0 for row in checks)


def test_check_row_tolerates_a_bare_legacy_artifact() -> None:
    artifact = {
        "snapshot_date": "2026-06-11",
        "overall": {"score": 50.0, "grade": "F"},
        "categories": {},
    }
    row = check_row("old-transit", artifact, agency=None, finding_count=0)
    assert row["grade"] == "F"
    assert row["categories_measured"] == 0
    assert row["fetch_source"] == "unknown"
    assert row["expiry_status"] == "unknown"
    assert row["license_id"] is None
    assert row["license_note"] is None
    assert row["feed_fetched_date"] == "2026-06-11"
    assert finding_rows("old-transit", artifact) == []


# --- license fields and the notice rule ---------------------------------------------


def test_license_fields_follow_the_notice_rule(repo: Path) -> None:
    checks, _findings, _counters = _rows(repo)
    by_id = {row["agency_id"]: row for row in checks}
    beta = by_id[BETA]
    assert beta["license_id"] == "ODbL-1.0"
    assert beta["share_alike"] == "true"
    assert beta["publisher_credit"] == "Contains data from Beta Transit."
    expected_notice = notice_for_agency(AGENCIES[BETA])
    assert expected_notice is not None
    assert beta["license_notice"] == expected_notice.export_text()
    assert beta["license_notice"].startswith("Share-alike license. ")
    assert "Open Database License (ODbL) 1.0" in beta["license_notice"]
    assert "Contains data from Beta Transit." in beta["license_notice"]
    # A block that marks CC BY as share-alike contradicts itself: the fields are
    # carried as recorded, and no notice names CC BY as share-alike.
    delta = by_id[DELTA]
    assert delta["share_alike"] == "true"
    assert delta["license_id"] == "CC-BY-4.0"
    assert delta["license_notice"] is None
    assert delta["license_terms_url"] is None
    assert delta["publisher_credit"] is None


def test_no_block_means_null_license_fields_not_a_permissive_reading() -> None:
    agency = Agency(
        id="plain", name="Plain", static_gtfs_url="https://p.example/g.zip", license_note="Unknown."
    )
    row = check_row(
        "plain",
        {"snapshot_date": "2026-07-01", "overall": {"score": 70.0}, "categories": {}},
        agency=agency,
        finding_count=0,
    )
    assert row["license_id"] is None
    assert row["attribution_required"] is None
    assert row["redistribution_allowed"] is None
    assert row["share_alike"] is None
    assert row["license_notice"] is None
    assert row["license_note"] == "Unknown."


# --- the opt-out ledger ---------------------------------------------------------------


def test_an_excluded_record_has_no_rows_in_either_table_and_is_only_counted(repo: Path) -> None:
    checks, findings, counters = _rows(repo)
    assert GAMMA not in {row["agency_id"] for row in checks}
    assert GAMMA not in {row["agency_id"] for row in findings}
    assert counters.excluded_records == 1
    assert counters.excluded_artifacts == 2
    assert counters.feed_records == 3


def test_an_empty_ledger_excludes_nothing(repo: Path) -> None:
    checks, _findings, counters = _rows(repo, ledger=Exclusions())
    assert GAMMA in {row["agency_id"] for row in checks}
    assert counters.excluded_records == 0


def test_the_committed_ledger_parses() -> None:
    assert isinstance(read_exclusions(LEDGER), Exclusions)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (["x"], "one top-level key"),
        ({"excluded": [], "extra": 1}, "one top-level key"),
        ({"excluded": "gamma"}, "must be a list"),
        ({"excluded": [{"agency_id": GAMMA}]}, "exactly agency_id, requested_on, reason"),
        (
            {
                "excluded": [
                    {"agency_id": "Gamma Transit", "requested_on": "2026-10-01", "reason": "x"}
                ]
            },
            "is not a record id",
        ),
        (
            {"excluded": [{"agency_id": GAMMA, "requested_on": "October 1", "reason": "x"}]},
            "ISO date",
        ),
        (
            {"excluded": [{"agency_id": GAMMA, "requested_on": "2026-02-30", "reason": "x"}]},
            "not a real date",
        ),
        (
            {"excluded": [{"agency_id": GAMMA, "requested_on": "2026-10-01", "reason": "  "}]},
            "non-empty string",
        ),
        (
            {
                "excluded": [
                    {"agency_id": GAMMA, "requested_on": "2026-10-01", "reason": "x"},
                    {"agency_id": GAMMA, "requested_on": "2026-10-02", "reason": "y"},
                ]
            },
            "listed twice",
        ),
    ],
)
def test_a_malformed_ledger_is_refused(raw: object, message: str) -> None:
    with pytest.raises(HistoryExportError, match=message):
        parse_exclusions(raw)


def test_a_null_list_is_an_empty_ledger() -> None:
    assert parse_exclusions({"excluded": None}) == Exclusions()


def test_a_missing_or_unparseable_ledger_stops_the_export(tmp_path: Path) -> None:
    with pytest.raises(HistoryExportError, match="missing"):
        read_exclusions(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("excluded: [\n")
    with pytest.raises(HistoryExportError, match="not valid YAML"):
        read_exclusions(bad)


# --- determinism and the files -----------------------------------------------------


def test_rows_digest_is_stable_for_a_fixed_tree(repo: Path) -> None:
    first_checks, first_findings, _ = _rows(repo)
    second_checks, second_findings, _ = _rows(repo)
    assert rows_digest(first_checks) == rows_digest(second_checks)
    assert rows_digest(first_findings) == rows_digest(second_findings)
    assert rows_digest(first_checks) != rows_digest(first_findings)


@needs_duckdb
def test_export_writes_the_same_bytes_twice_and_leaves_the_artifacts_alone(repo: Path) -> None:
    artifacts = repo / "data" / "artifacts"
    before = _tree_digest(artifacts)
    outputs = []
    for name in ("one", "two"):
        out = repo / "exports" / name
        counters = export_history(out, zip_path=repo / "exports" / f"{name}.zip")
        assert counters.checks == 4
        outputs.append(out)
    for filename in export_files(outputs[0]):
        assert (outputs[0] / filename).read_bytes() == (outputs[1] / filename).read_bytes(), (
            filename
        )
    assert (repo / "exports" / "one.zip").read_bytes() == (
        repo / "exports" / "two.zip"
    ).read_bytes()
    assert _tree_digest(artifacts) == before


@needs_duckdb
def test_export_tables_carry_the_declared_schema_and_the_excluded_id_never_appears(
    repo: Path,
) -> None:
    import duckdb

    out = repo / "exports" / "schema"
    counters = export_history(out)
    con = duckdb.connect()
    try:
        for table, columns in (("checks", CHECKS_COLUMNS), ("findings", FINDINGS_COLUMNS)):
            described = con.execute(
                "DESCRIBE SELECT * FROM read_parquet($p)", {"p": str(out / f"{table}.parquet")}
            ).fetchall()
            assert [(row[0], row[1]) for row in described] == [(c.name, c.type) for c in columns]
        ids = con.execute(
            "SELECT DISTINCT agency_id FROM read_parquet($p) ORDER BY 1",
            {"p": str(out / "checks.parquet")},
        ).fetchall()
        assert [row[0] for row in ids] == [ALPHA, BETA, DELTA]
        sweep = con.execute(
            "SELECT recompute_kind, feed_fetched_date::VARCHAR FROM read_parquet($p) "
            "WHERE agency_id = $a AND snapshot_date = DATE '2026-07-03'",
            {"p": str(out / "checks.parquet"), "a": ALPHA},
        ).fetchone()
        assert sweep == ("freshness", "2026-07-01")
    finally:
        con.close()
    for filename in export_files(out):
        assert GAMMA.encode() not in (out / filename).read_bytes(), filename
    provenance = json.loads((out / PROVENANCE_FILENAME).read_text())
    assert provenance["excluded_by_request"] == {"feed_records": 1, "artifacts": 2}
    assert provenance["generated_on"] == "2026-07-03"
    assert provenance["tables"]["checks"]["rows"] == counters.checks == 4
    assert provenance["tables"]["findings"]["rows"] == counters.findings == 12
    assert provenance["artifact_schema_versions"] == {"1.19": 3, "1.4": 1}
    assert provenance["artifacts_unreadable"] == 1
    assert (out / LICENSE_FILENAME).read_text() == LICENSE_TEXT
    assert (out / DICTIONARY_FILENAME).read_text() == render_dictionary()


@needs_duckdb
def test_export_refuses_a_non_empty_directory_and_a_bad_date(repo: Path) -> None:
    out = repo / "exports" / "full"
    out.mkdir(parents=True)
    (out / "stale.txt").write_text("x")
    with pytest.raises(HistoryExportError, match="new or empty"):
        export_history(out)
    with pytest.raises(HistoryExportError, match="ISO date"):
        export_history(repo / "exports" / "dated", generated_on="yesterday")


@needs_duckdb
def test_the_cli_builds_the_export_and_refuses_a_used_directory(repo: Path) -> None:
    out = repo / "exports" / "cli"
    zip_path = repo / "exports" / "cli.zip"
    assert (
        main(
            [
                "history-export",
                "--out",
                str(out),
                "--zip",
                str(zip_path),
                "--generated-on",
                "2026-10-05",
            ]
        )
        == 0
    )
    assert sorted(p.name for p in out.iterdir()) == sorted(export_files(out))
    assert zip_path.is_file()
    assert json.loads((out / PROVENANCE_FILENAME).read_text())["generated_on"] == "2026-10-05"
    with pytest.raises(SystemExit) as refused:
        main(["history-export", "--out", str(out)])
    assert refused.value.code == 2
