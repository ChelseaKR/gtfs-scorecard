from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scorecard_pipeline import DATA_ATTRIBUTION, DATA_LICENSE, SCHEMA_VERSION
from scorecard_pipeline.config import Agency
from scorecard_pipeline.dataset import build_quality_dataset, to_csv
from scorecard_pipeline.dataset_release import (
    DatasetReleaseError,
    assemble_release_bundle,
    validate_release_inputs,
)
from scorecard_pipeline.instance import BASE_URL
from scorecard_pipeline.ntd import (
    PortfolioSummary,
    assess,
    one_fix_from_ready,
    portfolio_summary,
    shapes_portfolio_summary,
)
from scorecard_pipeline.warehouse import to_parquet

CATALOG_CSV_FIELDS = (
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


def _write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _registry() -> dict[str, Agency]:
    agency = Agency(
        id="current-agency",
        name="Current Agency",
        static_gtfs_url="https://example.org/current.zip",
        state="California",
        country="US",
        subdivision_code="US-CA",
        subdivision_name="California",
    )
    return {agency.id: agency}


def _ntd_artifact(*, has_agency_id: bool = True) -> dict[str, object]:
    return {
        "agency": {
            "id": "current-agency",
            "name": "Current Agency",
            "state": "California",
            "country": "US",
        },
        "feed": {
            "static_url": "https://example.org/current.zip",
            "reachable": True,
            "sha256": "a" * 64,
        },
        "overall": {"grade": "B", "score": 88.5},
        "rubric_version": "1.3",
        "scoring_profile": {"id": "gtfs-scorecard-1.3", "rubric_version": "1.3"},
        "validator_version": "8.0.1",
        "reader_archive_profile": "raw-v1",
        "categories": {
            "correctness": {"status": "measured", "score": 91.0, "findings": []},
            "freshness": {
                "status": "measured",
                "score": 87.0,
                "details": {"days_until_expiry": 60},
            },
            "completeness": {"status": "measured", "score": 83.0},
        },
        "snapshot_date": "2026-08-01",
        "ntd_id_alignment": {"feed_agency_ids": ["current-agency"] if has_agency_id else []},
        "shapes_readiness": {"total_trips": 10, "trips_with_shape": 10},
    }


def _summary_payload(summary: PortfolioSummary) -> dict[str, object]:
    return {
        "total": summary.total,
        "ready": summary.ready,
        "at_risk": summary.at_risk,
        "not_ready": summary.not_ready,
        "pct_ready": summary.pct_ready,
        "by_state": summary.by_state,
    }


def _write_ntd(web: Path, artifact: dict[str, object]) -> None:
    summary = portfolio_summary([artifact])
    shapes = shapes_portfolio_summary([artifact])
    one_fix = one_fix_from_ready([artifact])
    (web / "ntd.json").write_text(
        json.dumps(
            {
                **_summary_payload(summary),
                "one_fix_from_ready": one_fix[:40],
                "one_fix_total": len(one_fix),
                "shapes": _summary_payload(shapes),
            }
        ),
        encoding="utf-8",
    )


def _write_current_artifact(artifacts: Path, artifact: dict[str, object]) -> None:
    agency_dir = artifacts / "current-agency"
    agency_dir.mkdir(exist_ok=True)
    (agency_dir / "latest.json").write_text(json.dumps(artifact), encoding="utf-8")


def _set_catalog_ntd_status(web: Path, status: str) -> None:
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog["agencies"][0]["ntd_ready"] = status
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")


def _release_tree(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    artifacts = tmp_path / "artifacts"
    web = tmp_path / "web"
    repo = tmp_path / "repo"
    (web / "api" / "v1").mkdir(parents=True)
    artifacts.mkdir()
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "api.md").write_text("# Data dictionary\n", encoding="utf-8")
    (repo / "CITATION.cff").write_text("cff-version: 1.2.0\n", encoding="utf-8")

    current: dict[str, object] = {
        "date": "2026-08-01",
        "grade": "B",
        "score": 88.5,
        "rubric_version": "1.3",
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": "1.3",
        "validator_version": "8.0.1",
        "feed_sha256": "a" * 64,
        "reader_archive_profile": "raw-v1",
        "categories": {
            "correctness": 91.0,
            "freshness": 87.0,
            "completeness": 83.0,
        },
        "days_until_expiry": 60,
        "service_horizon_status": "within_review_threshold",
    }
    index = {"agencies": {"current-agency": {"name": "Current Agency", "history": [current]}}}
    (artifacts / "index.json").write_text(json.dumps(index), encoding="utf-8")

    dataset = build_quality_dataset(index, agencies=_registry().values())
    dataset_row = dataset["rows"][0]
    ntd_artifact = _ntd_artifact()
    catalog_row = {
        **dataset_row,
        "snapshot_date": dataset_row["date"],
        "state": "California",
        "size_tier": "small",
        "expiry_status": "current",
        "mdb_id": "",
        "feed_url": "https://example.org/current.zip",
        "top_fix": None,
        "scorecard_url": "https://gtfsscorecard.org/agency/current-agency/",
        "country": "US",
        "subdivision_code": "US-CA",
        "subdivision_name": "California",
        "ntd_ready": assess(ntd_artifact).status,
        "stops": 10,
        "google_gate": "pass",
        "retrieved_at": "2026-08-01T00:00:00+00:00",
    }
    catalog_row.pop("date")
    (web / "catalog.json").write_text(
        json.dumps(
            {
                "source": BASE_URL,
                "schema_version": SCHEMA_VERSION,
                "rubric_version": "1.3",
                "rubric_versions": ["1.3"],
                "license": DATA_LICENSE,
                "attribution": DATA_ATTRIBUTION,
                "agencies": [catalog_row],
            }
        ),
        encoding="utf-8",
    )
    (web / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    _write_csv(web / "catalog.csv", [catalog_row], CATALOG_CSV_FIELDS)
    (web / "dataset.csv").write_text(to_csv(dataset), encoding="utf-8")
    _write_ntd(web, ntd_artifact)
    _write_current_artifact(artifacts, ntd_artifact)
    to_parquet([dataset_row], str(web / "api" / "v1" / "agencies.parquet"))
    return artifacts, web, repo, current


def test_assemble_release_bundle_validates_then_copies_every_format(tmp_path: Path) -> None:
    artifacts, web, repo, _current = _release_tree(tmp_path)
    bundle = tmp_path / "bundle"

    summary = assemble_release_bundle(
        artifacts_root=artifacts,
        web_root=web,
        repo_root=repo,
        bundle_root=bundle,
        current_registry=_registry(),
        retired_registry_ids={"retired-alias"},
    )

    assert summary.agencies == 1
    assert summary.rubric_version == "1.3"
    assert {path.name for path in bundle.iterdir()} == {
        "catalog.json",
        "catalog.csv",
        "dataset.json",
        "dataset.csv",
        "agencies.parquet",
        "ntd.json",
        "DATA-DICTIONARY.md",
        "CITATION.cff",
    }


def test_release_rejects_a_retired_or_unregistered_index_row(tmp_path: Path) -> None:
    artifacts, web, _repo, current = _release_tree(tmp_path)
    (artifacts / "index.json").write_text(
        json.dumps({"agencies": {"retired-alias": {"history": [current]}}}),
        encoding="utf-8",
    )

    with pytest.raises(DatasetReleaseError, match="retired or unregistered"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_stale_values_even_when_row_counts_match(tmp_path: Path) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog["agencies"][0]["score"] = 77.0
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="canonical current dataset field score"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source", "https://wrong.example"),
        ("license", "proprietary"),
        ("schema_version", "0.0"),
    ),
)
def test_release_rejects_catalog_metadata_outside_the_publication_contract(
    tmp_path: Path, field: str, replacement: str
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog[field] = replacement
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match=f"catalog.json {field}"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


@pytest.mark.parametrize(("field", "replacement"), (("state", "Nevada"), ("country", "CA")))
def test_release_rejects_catalog_geography_when_json_and_csv_agree_on_the_wrong_value(
    tmp_path: Path, field: str, replacement: str
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog["agencies"][0][field] = replacement
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    _write_csv(web / "catalog.csv", catalog["agencies"], CATALOG_CSV_FIELDS)

    with pytest.raises(DatasetReleaseError, match="geography disagrees"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_json_value_with_csv_style_type_coercion(tmp_path: Path) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog["agencies"][0]["score"] = "88.5"
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="canonical current dataset field score"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_parquet_with_stringified_canonical_values(tmp_path: Path) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    dataset = json.loads((web / "dataset.json").read_text(encoding="utf-8"))
    string_row = {
        field: "" if value is None else str(value) for field, value in dataset["rows"][0].items()
    }
    parquet = web / "api" / "v1" / "agencies.parquet"
    parquet.unlink()
    to_parquet([string_row], str(parquet))

    with pytest.raises(DatasetReleaseError, match="columns or types"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_torn_dataset_category_or_catalog_name(tmp_path: Path) -> None:
    for surface, field, replacement in (
        ("dataset.json", "correctness", 12.0),
        ("catalog.json", "name", "Wrong deployment"),
    ):
        case = tmp_path / surface.replace(".", "-")
        case.mkdir()
        artifacts, web, _repo, _current = _release_tree(case)
        document = json.loads((web / surface).read_text(encoding="utf-8"))
        rows_key = "rows" if surface == "dataset.json" else "agencies"
        document[rows_key][0][field] = replacement
        (web / surface).write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(DatasetReleaseError, match=r"canonical|disagrees"):
            validate_release_inputs(
                artifacts_root=artifacts,
                web_root=web,
                current_registry=_registry(),
                retired_registry_ids={"retired-alias"},
            )


def test_release_rejects_inconsistent_ntd_counts(tmp_path: Path) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    ntd["ready"] = 0
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="counts do not add up"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_ntd_state_statuses_that_do_not_reconcile_to_the_top(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    state = ntd["by_state"]["California"]
    state["ready"] = 0
    state["not_ready"] = 1
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="state counts do not match"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_one_fix_total_without_the_required_visible_rows(tmp_path: Path) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    ntd["one_fix_total"] = 1
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="one-fix count is inconsistent"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_accepts_one_fix_row_generated_by_the_production_assessor(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    artifact = _ntd_artifact(has_agency_id=False)
    _set_catalog_ntd_status(web, assess(artifact).status)
    _write_ntd(web, artifact)
    _write_current_artifact(artifacts, artifact)

    summary = validate_release_inputs(
        artifacts_root=artifacts,
        web_root=web,
        current_registry=_registry(),
        retired_registry_ids={"retired-alias"},
    )

    assert summary.agencies == 1


@pytest.mark.parametrize("pillar", ("invented", "agency_id"))
def test_release_rejects_fabricated_one_fix_pillar_or_fix(tmp_path: Path, pillar: str) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    artifact = _ntd_artifact(has_agency_id=False)
    _set_catalog_ntd_status(web, assess(artifact).status)
    _write_ntd(web, artifact)
    _write_current_artifact(artifacts, artifact)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    ntd["one_fix_from_ready"][0]["pillar"] = pillar
    ntd["one_fix_from_ready"][0]["fix"] = "Fabricated remediation text."
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="pillar or fix"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_empty_one_fix_when_current_artifact_has_a_near_miss(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    artifact = _ntd_artifact(has_agency_id=False)
    _set_catalog_ntd_status(web, assess(artifact).status)
    _write_ntd(web, artifact)
    _write_current_artifact(artifacts, artifact)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    ntd["one_fix_from_ready"] = []
    ntd["one_fix_total"] = 0
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="canonical current artifacts"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_fabricated_shapes_rollup_that_is_internally_consistent(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    ntd = json.loads((web / "ntd.json").read_text(encoding="utf-8"))
    ntd["shapes"] = {
        "total": 999,
        "ready": 999,
        "at_risk": 0,
        "not_ready": 0,
        "pct_ready": 100.0,
        "by_state": {"California": {"total": 999, "ready": 999, "at_risk": 0, "not_ready": 0}},
    }
    (web / "ntd.json").write_text(json.dumps(ntd), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match="canonical current artifacts"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_ntd_sections_without_canonical_current_artifacts(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    (artifacts / "current-agency" / "latest.json").unlink()

    with pytest.raises(DatasetReleaseError, match="canonical current artifact"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )


def test_release_rejects_retired_identifier_references_outside_id_columns(
    tmp_path: Path,
) -> None:
    artifacts, web, _repo, _current = _release_tree(tmp_path)
    catalog = json.loads((web / "catalog.json").read_text(encoding="utf-8"))
    catalog["agencies"][0]["scorecard_url"] = "https://gtfsscorecard.org/agency/retired-alias/"
    (web / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(DatasetReleaseError, match=r"cites a retired|disagrees"):
        validate_release_inputs(
            artifacts_root=artifacts,
            web_root=web,
            current_registry=_registry(),
            retired_registry_ids={"retired-alias"},
        )
