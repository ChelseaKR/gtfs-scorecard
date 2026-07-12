"""Machine-enforcement of the published data contracts (web/schemas/).

Every published document type has a JSON Schema, the schemas themselves are
valid Draft 2020-12, and publish() refuses to write an artifact that violates
the per-agency contract — so a shape change must ship with a schema update,
never reach consumers as a surprise.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from scorecard_pipeline import SCHEMA_VERSION
from scorecard_pipeline.config import Agency, artifacts_dir
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult, Finding
from scorecard_pipeline.publish import (
    RESERVED_ARTIFACT_DIRS,
    build_artifact,
    publish,
    validate_artifact,
)
from scorecard_pipeline.score import build_scorecard

# The source checkout, not the SCORECARD_ROOT tmp dir the autouse fixture sets:
# the schemas and the real published outputs live here.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "web" / "schemas"
SCHEMA_PATHS = sorted(SCHEMA_DIR.glob("*.schema.json"))

AGENCY = Agency(
    id="unitrans",
    name="Unitrans",
    static_gtfs_url="https://example.org/gtfs.zip",
    license_note="test",
)
GENERATED_AT = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(_load(SCHEMA_DIR / schema_name))


def make_artifact(date: dt.date, agency: Agency = AGENCY) -> dict:  # type: ignore[type-arg]
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=date,
        sha256="abc123",
        size_bytes=1024,
        reused=False,
    )
    finding = Finding(
        code="expired_calendar",
        severity="WARNING",
        count=3,
        what="w",
        why="y",
        fix="f",
        effort="e",
        deduction=4.0,
    )
    card = build_scorecard(
        [CategoryResult(name="correctness", score=88.0, summary="s", findings=[finding])]
    )
    return build_artifact(agency, fetch, card, GENERATED_AT)


# ---------------------------------------------------------------------------
# The schemas themselves


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda p: p.name)
def test_every_published_schema_is_valid_draft_2020_12(schema_path: Path) -> None:
    Draft202012Validator.check_schema(_load(schema_path))


def test_a_schema_exists_for_every_published_document_type() -> None:
    names = {p.name for p in SCHEMA_PATHS}
    assert {
        "artifact.schema.json",
        "catalog.schema.json",
        "directory.schema.json",
        "rollup.schema.json",
        "rollup-index.schema.json",
        "coverage.schema.json",
        "by-location.schema.json",
    } <= names


def test_coverage_api_conforms_to_its_schema() -> None:
    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.dataset import build_quality_dataset
    from scorecard_pipeline.publicapi import coverage_endpoint

    index = {
        "agencies": {
            "demo": {
                "history": [{"score": 80.0}],
            }
        }
    }
    payload = coverage_endpoint(
        index,
        build_quality_dataset(index),
        [Agency("demo", "Demo", "https://example.org/feed.zip")],
    )
    _validator("coverage.schema.json").validate(payload)


def test_by_location_api_conforms_to_its_schema() -> None:
    from scorecard_pipeline.dataset import build_quality_dataset
    from scorecard_pipeline.publicapi import by_location

    index = {
        "agencies": {
            "demo": {
                "history": [{"score": 80.0, "grade": "B"}],
            }
        }
    }
    payload = by_location(
        build_quality_dataset(index),
        {
            "demo": {
                "country": "CA",
                "subdivision_code": "CA-ON",
                "subdivision_name": "Ontario",
            }
        },
    )
    _validator("by-location.schema.json").validate(payload)


def _country_contract_documents(country_code: str) -> dict[str, dict[str, Any]]:
    """Minimal published documents carrying one portable country location."""
    subdivision_code, subdivision_name, country_name = {
        "US": ("US-CA", "California", "United States"),
        "CA": ("CA-ON", "Ontario", "Canada"),
    }.get(country_code, ("GB-ENG", "England", "United Kingdom"))
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["agency"]["country"] = country_code
    artifact["agency"]["subdivision_code"] = subdivision_code
    artifact["agency"]["subdivision_name"] = subdivision_name
    agency = {
        "id": "demo-gb",
        "name": "Demo GB",
        "grade": "B",
        "score": 80.0,
        "country": country_code,
        "subdivision_code": subdivision_code,
        "subdivision_name": subdivision_name,
    }
    distribution = {"A": 0, "B": 1, "C": 0, "D": 0, "F": 0}
    country = {
        "country_code": country_code,
        "country_name": country_name,
        "count": 1,
        "median_score": 80.0,
        "grade_distribution": distribution,
        "subdivisions": [],
    }
    directory_country = {
        "country_code": country_code,
        "country_name": country_name,
        "agencies": 1,
        "subdivisions": [],
    }
    return {
        "artifact.schema.json": artifact,
        "catalog.schema.json": {"schema_version": SCHEMA_VERSION, "agencies": [agency]},
        "directory.schema.json": {
            "schema_version": SCHEMA_VERSION,
            "summary": {
                "agencies": 1,
                "grade_distribution": distribution,
                "countries": [directory_country],
            },
            "agencies": [agency],
        },
        "by-location.schema.json": {"countries": [country]},
    }


def test_country_contract_accepts_a_forward_compatible_iso_alpha_2_code() -> None:
    """Public schemas describe the portable shape, not the deployment allowlist."""
    assert SCHEMA_VERSION == "1.9"
    for schema_name, document in _country_contract_documents("GB").items():
        _validator(schema_name).validate(document)


def test_historical_1_8_us_and_canada_documents_remain_valid() -> None:
    for country_code in ("US", "CA"):
        for schema_name, document in _country_contract_documents(country_code).items():
            if "schema_version" in document:
                document["schema_version"] = "1.8"
            _validator(schema_name).validate(document)


@pytest.mark.parametrize("country_code", ["gb", "GBR", "G1", "G-"])
def test_country_contract_rejects_malformed_country_codes(country_code: str) -> None:
    for schema_name, document in _country_contract_documents(country_code).items():
        with pytest.raises(ValidationError, match="does not match"):
            _validator(schema_name).validate(document)


@pytest.mark.parametrize(
    "relative",
    [
        "web/api/v1/coverage.json",
        "pipeline/tests/goldens/api/v1/coverage.json",
        "pipeline/tests/fixtures/golden_site/web/api/v1/coverage.json",
    ],
)
def test_published_coverage_conforms_to_its_schema(relative: str) -> None:
    _validator("coverage.schema.json").validate(_load(REPO_ROOT / relative))


# ---------------------------------------------------------------------------
# The per-agency artifact contract (artifact.schema.json)


def test_build_artifact_output_conforms_to_the_artifact_schema() -> None:
    validate_artifact(make_artifact(dt.date(2026, 6, 11)))


def test_artifact_with_every_optional_agency_field_conforms() -> None:
    agency = Agency(
        id="barrie",
        name="Barrie Transit",
        static_gtfs_url="https://example.org/g.zip",
        country="CA",
        subdivision_code="CA-ON",
        subdivision_name="Ontario",
        operating_note="Confirmed operating.",
        ntd_note="Shared regional feed.",
    )
    validate_artifact(make_artifact(dt.date(2026, 6, 11), agency=agency))


def test_artifact_with_the_us_only_ntd_block_conforms() -> None:
    """cli.py's run_agency() attaches ntd_id_alignment, shapes_readiness, and
    ntd_readiness to a US agency's artifact *after* build_artifact() runs (they
    need the fetched feed and, for ntd_readiness, the artifact itself) --
    make_artifact() above never exercises that path, which is exactly the gap
    that let shapes_readiness ship to every US agency's artifact for a full day
    with no schema entry for it: every real run failed validate_artifact() and
    silently kept each agency's last good artifact (the shard step's designed
    fallback for a *transient* per-agency failure), so no committed artifact
    ever carried the field either, and test_every_published_agency_artifact_
    conforms() below had nothing to catch it on. Constructing the block the
    same way run_agency() does, from plain data with no GTFS zip required,
    closes that blind spot directly."""
    from scorecard_pipeline.ntd import assess as assess_ntd_readiness
    from scorecard_pipeline.ntd import assess_id_alignment, assess_shapes_readiness

    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["ntd_id_alignment"] = assess_id_alignment(["90001"], "90001").to_dict()
    artifact["shapes_readiness"] = assess_shapes_readiness(10, 7).to_dict()
    artifact["ntd_readiness"] = assess_ntd_readiness(artifact).to_dict()
    validate_artifact(artifact)


def test_shapes_readiness_conforms_in_every_status() -> None:
    from scorecard_pipeline.ntd import assess_shapes_readiness

    # not_ready (no trips), not_ready (trips but no shapes), at_risk (partial),
    # ready (full coverage, and to_dict() then omits the optional "fix" key).
    for total, with_shape in [(0, 0), (10, 0), (10, 7), (10, 10)]:
        artifact = make_artifact(dt.date(2026, 6, 11))
        artifact["shapes_readiness"] = assess_shapes_readiness(total, with_shape).to_dict()
        validate_artifact(artifact)


def test_validate_artifact_rejects_an_unknown_grade() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["overall"]["grade"] = "E"
    with pytest.raises(ValidationError, match="'E' is not one of"):
        validate_artifact(artifact)


def test_publish_refuses_an_artifact_with_an_undeclared_top_level_key() -> None:
    # additionalProperties: false at the top level is the enforcement point: a
    # new block cannot reach production without a schema update.
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["surprise_block"] = {"anything": True}
    with pytest.raises(ValidationError, match="surprise_block"):
        publish(artifact)
    # Nothing was written for the rejected artifact.
    assert not (artifacts_dir() / AGENCY.id).exists()


def test_publish_refuses_an_artifact_missing_feed_provenance() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["feed"]["sha256"]
    with pytest.raises(ValidationError, match="sha256"):
        publish(artifact)


def test_current_artifact_requires_scoring_profile() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["scoring_profile"]
    with pytest.raises(ValidationError, match="scoring_profile"):
        validate_artifact(artifact)


def test_historical_artifact_before_scoring_profile_still_conforms() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["schema_version"] = "1.7"
    del artifact["scoring_profile"]
    validate_artifact(artifact)


def test_a_measured_category_must_carry_score_findings_and_details() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["categories"]["correctness"]["details"]
    with pytest.raises(ValidationError, match="details"):
        validate_artifact(artifact)


# ---------------------------------------------------------------------------
# Real published outputs validate against the published schemas


def _published_agency_artifacts() -> list[Path]:
    root = REPO_ROOT / "data" / "artifacts"
    if not root.exists():
        return []
    return [
        p for p in sorted(root.glob("*/latest.json")) if p.parent.name not in RESERVED_ARTIFACT_DIRS
    ]


def test_every_published_agency_artifact_conforms() -> None:
    paths = _published_agency_artifacts()
    if not paths:
        pytest.skip("no published artifacts in this checkout")
    validator = _validator("artifact.schema.json")
    bad: dict[str, str] = {}
    for path in paths:
        error = next(iter(validator.iter_errors(_load(path))), None)
        if error is not None:
            bad[path.parent.name] = f"{error.json_path}: {error.message}"
    assert not bad, f"{len(bad)} published artifacts violate the schema: {bad}"


def test_golden_site_agency_artifacts_conform() -> None:
    root = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "golden_site" / "data" / "artifacts"
    validator = _validator("artifact.schema.json")
    paths = [
        p for p in sorted(root.glob("*/latest.json")) if p.parent.name not in RESERVED_ARTIFACT_DIRS
    ]
    assert paths, "golden_site fixture has no agency artifacts"
    for path in paths:
        validator.validate(_load(path))


@pytest.mark.parametrize(
    "relative",
    [
        "web/catalog.json",
        "pipeline/tests/goldens/catalog.json",
        "pipeline/tests/fixtures/golden_site/web/catalog.json",
    ],
)
def test_published_catalog_conforms_to_its_schema(relative: str) -> None:
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} not in this checkout")
    _validator("catalog.schema.json").validate(_load(path))


@pytest.mark.parametrize(
    "relative",
    [
        "data/artifacts/directory.json",
        "pipeline/tests/fixtures/golden_site/data/artifacts/directory.json",
    ],
)
def test_published_directory_conforms_to_its_schema(relative: str) -> None:
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} not in this checkout")
    _validator("directory.schema.json").validate(_load(path))


# ---------------------------------------------------------------------------
# The program rollup contract (rollup.schema.json, rollup-index.schema.json)


def test_build_rollup_output_conforms_to_the_rollup_schema() -> None:
    """publish_rollups() attaches state_percentile after build_rollup() runs
    (it needs every state's average first), the same after-the-build pattern
    as the artifact's NTD block, so the direct test attaches it too."""
    from scorecard_pipeline.rollups import Rollup, build_rollup

    for agency_id, score, grade, days in [("a-one", 55.0, "D", 12), ("b-two", 91.0, "A", None)]:
        agency_dir = artifacts_dir() / agency_id
        agency_dir.mkdir(parents=True, exist_ok=True)
        (agency_dir / "latest.json").write_text(
            json.dumps(
                {
                    "agency": {"id": agency_id, "name": agency_id.title()},
                    "snapshot_date": "2026-06-11",
                    "overall": {"score": score, "grade": grade},
                    "categories": {"freshness": {"details": {"days_until_expiry": days}}},
                    "top_fixes": [{"code": "scorecard_feed_expired", "fix": "Re-export."}],
                }
            )
        )
    payload = build_rollup(
        Rollup(id="demo", name="Demo cohort", member_ids=("a-one", "b-two")),
        GENERATED_AT,
        attention={"a-one": "Service data expires in 12 days"},
    )
    payload["state_percentile"] = None
    _validator("rollup.schema.json").validate(payload)


def _published_rollups() -> list[Path]:
    root = REPO_ROOT / "data" / "artifacts" / "rollups"
    if not root.exists():
        return []
    return [p for p in sorted(root.glob("*.json")) if p.name != "index.json"]


def test_every_published_rollup_conforms() -> None:
    paths = _published_rollups()
    if not paths:
        pytest.skip("no published rollups in this checkout")
    validator = _validator("rollup.schema.json")
    bad: dict[str, str] = {}
    for path in paths:
        error = next(iter(validator.iter_errors(_load(path))), None)
        if error is not None:
            bad[path.name] = f"{error.json_path}: {error.message}"
    assert not bad, f"{len(bad)} published rollups violate the schema: {bad}"


def test_golden_site_rollups_conform() -> None:
    root = REPO_ROOT / "pipeline" / "tests" / "fixtures" / "golden_site" / "data" / "artifacts"
    validator = _validator("rollup.schema.json")
    paths = [p for p in sorted((root / "rollups").glob("*.json")) if p.name != "index.json"]
    assert paths, "golden_site fixture has no rollups"
    for path in paths:
        validator.validate(_load(path))


@pytest.mark.parametrize(
    "relative",
    [
        "data/artifacts/rollups/index.json",
        "pipeline/tests/fixtures/golden_site/data/artifacts/rollups/index.json",
    ],
)
def test_published_rollup_index_conforms_to_its_schema(relative: str) -> None:
    path = REPO_ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} not in this checkout")
    _validator("rollup-index.schema.json").validate(_load(path))


def test_artifact_with_an_export_diff_block_conforms() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["export_diff"] = {
        "from_sha256": "a" * 64,
        "to_sha256": "b" * 64,
        "changes": ["Route 5 is no longer in the export."],
    }
    validate_artifact(artifact)


def test_export_diff_with_no_changes_is_rejected() -> None:
    # The block exists only to say what changed; an empty one is a bug.
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["export_diff"] = {"from_sha256": None, "to_sha256": "b" * 64, "changes": []}
    with pytest.raises(ValidationError, match="non-empty"):
        validate_artifact(artifact)
