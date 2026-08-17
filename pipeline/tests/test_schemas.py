"""Machine-enforcement of the published data contracts (web/schemas/).

Every published document type has a JSON Schema, the schemas themselves are
valid Draft 2020-12, and publish() refuses to write an artifact that violates
the per-agency contract — so a shape change must ship with a schema update,
never reach consumers as a surprise.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from scorecard_pipeline import RUBRIC_VERSION, SCHEMA_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.config import Agency, artifacts_dir
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult, Finding
from scorecard_pipeline.publish import (
    RESERVED_ARTIFACT_DIRS,
    build_artifact,
    publish,
    validate_artifact,
)
from scorecard_pipeline.score import build_scorecard, letter_grade
from scorecard_pipeline.validate import VALIDATOR_VERSION

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


def _legacy_comparison() -> dict[str, Any]:
    """API v1 comparison metadata from before reader archive profiles shipped."""
    return {
        "eligible_count": 0,
        "excluded_count": 0,
        "required_rubric_version": RUBRIC_VERSION,
        "required_scoring_profile_id": SCORING_PROFILE_ID,
        "required_validator_version": VALIDATOR_VERSION,
        "required_measured_categories": [],
        "measured_category_cohorts": {},
        "exclusion_counts": {},
        "absolute_rankings_published": False,
        "individual_percentiles_published": False,
        "note": "No comparable records.",
    }


def _legacy_aggregate_documents() -> dict[str, dict[str, Any]]:
    comparison = _legacy_comparison()
    return {
        "directory.schema.json": {
            "schema_version": "1.14",
            "summary": {
                "agencies": 0,
                "grade_distribution": {},
                "comparison": comparison.copy(),
            },
            "agencies": [],
        },
        "rollup.schema.json": {
            "schema_version": "1.14",
            "rollup": {"id": "legacy", "name": "Legacy cohort"},
            "generated_at": "2026-07-01T00:00:00+00:00",
            "agency_count": 0,
            "average_score": None,
            "grade_distribution": {},
            "needs_attention": 0,
            "expired": {"lapsed": 0, "stale": 0, "total": 0},
            "members": [],
            "common_fixes": [],
            "comparison": comparison.copy(),
        },
        "by-location.schema.json": {
            "countries": [],
            "comparison": comparison.copy(),
        },
    }


def make_artifact(date: dt.date, agency: Agency = AGENCY) -> dict:  # type: ignore[type-arg]
    fetch = FetchResult(
        agency_id=agency.id,
        path=Path("/tmp/gtfs.zip"),
        url=agency.static_gtfs_url,
        fetched_date=date,
        sha256="a" * 64,
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
        "global-coverage.schema.json",
        "sync-source-metadata.schema.json",
        "sync-source-metadata-1.1.schema.json",
        "sync-source-metadata-1.2.schema.json",
    } <= names


def test_sync_source_metadata_11_contract_stays_frozen_and_retrievable() -> None:
    compatibility_path = SCHEMA_DIR / "sync-source-metadata.schema.json"
    compatibility_sha = hashlib.sha256(compatibility_path.read_bytes()).hexdigest()
    assert compatibility_sha == "f32446988f9a67e3fc32eb0994d384d0a99f2024598c819475219db95eaf2fe9"

    versioned = _load(SCHEMA_DIR / "sync-source-metadata-1.1.schema.json")
    assert versioned["$ref"] == (
        "https://gtfsscorecard.org/schemas/sync-source-metadata.schema.json"
    )
    assert versioned["x-referenced-schema-sha256"] == compatibility_sha


def test_sync_source_metadata_12_contract_has_an_immutable_public_id() -> None:
    schema_path = SCHEMA_DIR / "sync-source-metadata-1.2.schema.json"
    schema = _load(schema_path)
    schema_url = "https://gtfsscorecard.org/schemas/sync-source-metadata-1.2.schema.json"

    assert hashlib.sha256(schema_path.read_bytes()).hexdigest() == (
        "efe5468c02220fabb99c544b9b47c278f7c242b65ef7ec50dc7739c95e551a96"
    )
    assert schema["$id"] == schema_url
    assert schema["properties"]["schema_url"]["const"] == schema_url


@pytest.mark.parametrize(
    ("schema_name", "document"),
    _legacy_aggregate_documents().items(),
)
def test_legacy_aggregate_comparison_without_reader_archive_profile_remains_valid(
    schema_name: str,
    document: dict[str, Any],
) -> None:
    _validator(schema_name).validate(document)


@pytest.mark.parametrize(
    ("schema_name", "document"),
    _legacy_aggregate_documents().items(),
)
def test_aggregate_comparison_rejects_malformed_reader_archive_profile_when_present(
    schema_name: str,
    document: dict[str, Any],
) -> None:
    if schema_name == "directory.schema.json":
        comparison = document["summary"]["comparison"]
    else:
        comparison = document["comparison"]
    comparison["required_reader_archive_profile"] = {"unexpected": "object"}

    with pytest.raises(ValidationError, match="is not of type 'string'"):
        _validator(schema_name).validate(document)


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


def test_global_coverage_api_conforms_to_its_schema() -> None:
    from scorecard_pipeline.config import ReuseEvidence
    from scorecard_pipeline.global_coverage import build_global_coverage

    evidence = ReuseEvidence(
        decision="approved",
        source_kind="official_portal",
        provider_source_url="https://transport.example.org/datasets/demo",
        terms_url="https://transport.example.org/terms",
        scope=("gtfs_schedule",),
        attribution="Example transport authority",
        reviewed_by="ChelseaKR",
        reviewed_on="2026-07-16",
        identity_reviewed=True,
    )
    agency = Agency(
        id="demo-fr",
        name="Demo France",
        static_gtfs_url="https://transport.example.org/demo.zip",
        country="FR",
        subdivision_code="FR-NOR",
        subdivision_name="Normandie",
        reuse_evidence=evidence,
    )
    generated_at = "2026-07-16T12:00:00+00:00"
    payload = build_global_coverage(
        [agency],
        {
            "agencies": [
                {
                    "id": agency.id,
                    "country": agency.country,
                    "subdivision_code": agency.subdivision_code,
                    "subdivision_name": agency.subdivision_name,
                    "retrieved_at": "2026-07-16T11:00:00+00:00",
                }
            ]
        },
        {
            "feed_record_count": 1,
            "feeds": [{"id": agency.id, "translations_measured": True}],
        },
        generated_at,
    )

    # The producer intentionally publishes absent optional identity and page
    # URLs as JSON null, rather than an empty or fabricated value.
    assert payload["records"][0]["organization_id"] is None
    assert payload["records"][0]["scorecard_url"] is None
    _validator("global-coverage.schema.json").validate(payload)

    empty_payload = build_global_coverage(
        [],
        {"agencies": []},
        {"feed_record_count": 0, "feeds": []},
        generated_at,
    )
    assert empty_payload["cohort"]["largest_country"] is None
    assert {
        row["actual"]
        for row in empty_payload["criteria"]
        if row["key"]
        in {
            "largest_country_share",
            "fresh_scorecards",
            "translations_measured",
            "portable_location",
            "identity_reviewed",
        }
    } == {None}
    _validator("global-coverage.schema.json").validate(empty_payload)


def test_by_location_api_conforms_to_its_schema() -> None:
    from scorecard_pipeline.publicapi import build_api

    index = {
        "agencies": {
            "demo": {
                "name": "Demo",
                "history": [
                    {
                        "date": "2026-06-11",
                        "score": 80.0,
                        "grade": "B",
                        "rubric_version": RUBRIC_VERSION,
                        "scoring_profile_id": SCORING_PROFILE_ID,
                        "scoring_profile_rubric_version": RUBRIC_VERSION,
                        "validator_version": VALIDATOR_VERSION,
                        "feed_sha256": "sha-demo",
                        "categories": {
                            "correctness": 80.0,
                            "freshness": 80.0,
                            "completeness": 80.0,
                        },
                        "days_until_expiry": 100,
                    }
                ],
            }
        }
    }
    payload = build_api(
        index,
        agencies=[Agency("demo", "Demo", "https://example.org/feed.zip")],
        states={"demo": "Ontario"},
        locations={
            "demo": {
                "country": "CA",
                "subdivision_code": "CA-ON",
                "subdivision_name": "Ontario",
            }
        },
        base_url="https://example.org",
        generated_at="2026-06-11T12:00:00+00:00",
    )["by-location.json"]
    assert payload["countries"][0]["comparison_eligible_count"] == 1
    assert payload["comparison"]["required_scoring_profile_id"] == SCORING_PROFILE_ID
    _validator("by-location.schema.json").validate(payload)


def test_current_directory_and_catalog_compatibility_fields_conform() -> None:
    from scorecard_pipeline.directory import build_directory

    record = {
        "id": "demo",
        "name": "Demo",
        "date": "2026-06-11",
        "grade": "B",
        "score": 80.0,
        "correctness": 80.0,
        "freshness": 80.0,
        "completeness": 80.0,
        "realtime": None,
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile_id": SCORING_PROFILE_ID,
        "scoring_profile_rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "feed_sha256": "sha-demo",
        "days_until_expiry": 100,
        "expiry_status": "current",
        "stops": 20,
        "country": "US",
        "subdivision_code": "US-CA",
        "subdivision_name": "California",
        "state": "California",
        "scorecard_url": "https://example.org/agency/demo/",
    }
    directory = build_directory([record], GENERATED_AT.isoformat())

    assert directory["agencies"][0]["national_percentile"] is None
    assert directory["agencies"][0]["peer_percentile"] is None
    assert directory["agencies"][0]["comparison_eligible"] is True
    assert directory["summary"]["comparison_eligible_count"] == 1
    _validator("directory.schema.json").validate(directory)
    _validator("catalog.schema.json").validate(
        {"schema_version": SCHEMA_VERSION, "agencies": directory["agencies"]}
    )


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
    assert SCHEMA_VERSION == "1.18"
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


def test_artifact_with_ungraded_mode_profile_conforms() -> None:
    from scorecard_pipeline.modes import build_mode_profile

    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["mode_profile"] = build_mode_profile(
        [{"route_id": "ferry", "route_type": "4"}],
        [{"route_id": "ferry", "trip_id": "sailing"}],
    )

    validate_artifact(artifact)


def test_artifact_with_ungraded_ferry_profile_conforms() -> None:
    from scorecard_pipeline.ferry_profile import build_ferry_profile

    artifact = make_artifact(dt.date(2026, 6, 11))
    profile = build_ferry_profile(
        [{"route_id": "ferry", "route_type": "4"}],
        [
            {
                "route_id": "ferry",
                "trip_id": "sailing",
                "wheelchair_accessible": "1",
                "bikes_allowed": "1",
                "cars_allowed": "0",
            }
        ],
        [{"trip_id": "sailing", "stop_id": "pier"}],
        [
            {
                "stop_id": "pier",
                "location_type": "0",
                "parent_station": "terminal",
                "stop_access": "1",
                "wheelchair_boarding": "1",
            },
            {"stop_id": "terminal", "location_type": "1"},
        ],
        fare_profile={"model": "legacy", "applied": True},
        configured_realtime_kinds={"trip_updates"},
    )
    assert profile is not None
    artifact["ferry_profile"] = profile

    validate_artifact(artifact)


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


def test_artifact_feed_hash_must_be_lowercase_sha256() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["feed"]["sha256"] = "../not-a-content-address"
    with pytest.raises(ValidationError, match="does not match"):
        validate_artifact(artifact)


def test_artifact_rejects_contradictory_reader_archive_provenance() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    assert artifact["fetch"]["reader_archive_profile"] == "raw-v1"
    artifact["fetch"]["reader_archive_normalized"] = True

    with pytest.raises(ValidationError):
        validate_artifact(artifact)


def test_artifact_accepts_legacy_normalized_reader_without_explicit_profile() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["fetch"]["reader_archive_profile"]
    artifact["fetch"]["reader_archive_normalized"] = True

    validate_artifact(artifact)


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


def test_current_artifact_requires_feed_source_provenance() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["feed"]["source_provenance"]
    with pytest.raises(ValidationError, match="source_provenance"):
        validate_artifact(artifact)


def test_current_artifact_requires_versioned_conformance() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    del artifact["conformance"]["version"]
    with pytest.raises(ValidationError, match="version"):
        validate_artifact(artifact)


def test_historical_artifact_before_source_provenance_still_conforms() -> None:
    artifact = make_artifact(dt.date(2026, 6, 11))
    artifact["schema_version"] = "1.17"
    del artifact["feed"]["source_provenance"]
    del artifact["conformance"]["version"]
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


# The current, rewritable published surfaces. docs/api.md's HTTP contract:
# dated artifacts (<agency>/<date>.json) are immutable once written so a
# consumer can pin one, while latest.json, catalog.json and directory.json are
# rewritten when a scoring run completes. Everything below is on the rewritable
# side, which is why the letters in it are required to be right today rather
# than only from the next run onward.
CURRENT_SURFACE_GLOBS = (
    "data/artifacts/*/latest.json",
    "data/artifacts/index.json",
    "data/artifacts/directory.json",
    "data/artifacts/rollups/*.json",
    "web/catalog.json",
    "web/dataset.json",
    "web/api/v1/*.json",
    "pipeline/tests/fixtures/golden_site/data/artifacts/*/latest.json",
    "pipeline/tests/fixtures/golden_site/data/artifacts/rollups/*.json",
)


def _graded_pairs(node: Any, path: str) -> list[tuple[str, float, str]]:
    """Every (json path, score, grade) pair anywhere in a published document."""
    found: list[tuple[str, float, str]] = []
    if isinstance(node, dict):
        grade, score = node.get("grade"), node.get("score")
        if isinstance(grade, str) and isinstance(score, (int, float)) and grade in set("ABCDF"):
            found.append((path, float(score), grade))
        for key, value in node.items():
            found.extend(_graded_pairs(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_graded_pairs(value, f"{path}[{i}]"))
    return found


def test_every_published_letter_is_the_letter_its_own_score_earns() -> None:
    """No published surface may show a grade its printed score contradicts.

    test_every_published_agency_artifact_conforms above walks the same
    latest.json files and cannot catch this: the schema constrains grade to the
    A-F enum and score to 0-100, and the relationship between them is not
    expressible there. It passed on nine agencies reading "Grade C * 80.0 /
    100" -- bus-eireann, express-bus-ie, slieve-bloom-coach-tours, cape-ann,
    sandy-area-metro-sam at 80.0/C, regional-transportation-commission-rtc at
    70.0/D, and stan-nancy, ukmerge and vilnius-district at 60.0/F -- while
    docs/rubric.md and the scoring.json this project publishes so a reader can
    "reproduce or contest the grade" say 80 is a B and 60 is a D.

    This is the check that reproduces the grade the way that reader would.
    """
    wrong: list[str] = []
    scanned = 0
    for pattern in CURRENT_SURFACE_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if path.parent.name in RESERVED_ARTIFACT_DIRS:
                continue
            scanned += 1
            rel = path.relative_to(REPO_ROOT)
            for json_path, score, grade in _graded_pairs(_load(path), "$"):
                earned = letter_grade(score)
                if grade != earned:
                    wrong.append(
                        f"{rel}{json_path[1:]}: {score} is a {earned}, published as {grade}"
                    )
    assert scanned, "no published current surfaces found in this checkout"
    assert not wrong, f"{len(wrong)} published letters contradict their own score:\n" + "\n".join(
        wrong[:40]
    )


def test_the_badge_a_consumer_embeds_shows_the_same_grade_as_the_artifact() -> None:
    """badge.json/badge.svg go on an agency's own developer page.

    They are pure functions of latest.json's overall block, written next to it
    by publish and rebuild_index, so a badge that disagrees with the artifact
    it links to is always wrong. 302 committed badges did: 268 showed a score
    latest.json no longer carried, and 20 of those a different letter --
    anchorage-people-mover's artifact read C 73.5 beside a badge reading D
    65.8. Nothing compared the two files.
    """
    wrong: list[str] = []
    checked = 0
    for latest_path in sorted((REPO_ROOT / "data" / "artifacts").glob("*/latest.json")):
        agency = latest_path.parent.name
        if agency in RESERVED_ARTIFACT_DIRS:
            continue
        badge_path = latest_path.parent / "badge.json"
        svg_path = latest_path.parent / "badge.svg"
        if not badge_path.exists():
            continue
        checked += 1
        overall = _load(latest_path)["overall"]
        expected = f"{overall['grade']} {overall['score']}"
        message = str(_load(badge_path).get("message", ""))
        # A status segment ("... - feed expired") is appended by design; the
        # grade and score are the leading two words either way.
        if " ".join(message.split(" ")[:2]) != expected:
            wrong.append(f"{agency}: badge.json says {message!r}, artifact says {expected!r}")
        elif f">{overall['grade']} {round(float(overall['score']))}<" not in svg_path.read_text():
            wrong.append(f"{agency}: badge.svg disagrees with badge.json {message!r}")
    assert checked, "no badges found in this checkout"
    assert not wrong, (
        f"{len(wrong)} of {checked} embeddable badges disagree with their own artifact:\n"
        + "\n".join(wrong[:40])
    )


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
    """The current rollup producer contract conforms as one complete payload."""
    from scorecard_pipeline.rollups import Rollup, build_rollup

    for agency_id, score, grade, days in [("a-one", 55.0, "D", 12), ("b-two", 91.0, "A", None)]:
        agency_dir = artifacts_dir() / agency_id
        agency_dir.mkdir(parents=True, exist_ok=True)
        (agency_dir / "latest.json").write_text(
            json.dumps(
                {
                    "rubric_version": RUBRIC_VERSION,
                    "scoring_profile": {
                        "id": SCORING_PROFILE_ID,
                        "rubric_version": RUBRIC_VERSION,
                    },
                    "validator_version": VALIDATOR_VERSION,
                    "agency": {"id": agency_id, "name": agency_id.title()},
                    "snapshot_date": "2026-06-11",
                    "overall": {"score": score, "grade": grade},
                    "feed": {"sha256": f"sha-{agency_id}"},
                    "categories": {
                        "correctness": {"status": "measured", "score": score},
                        "freshness": {
                            "status": "measured",
                            "score": score,
                            "details": {"days_until_expiry": days},
                        },
                        "completeness": {"status": "measured", "score": score},
                        "realtime": {"status": "not_yet_measured"},
                    },
                    "top_fixes": [{"code": "scorecard_feed_expired", "fix": "Re-export."}],
                }
            )
        )
    payload = build_rollup(
        Rollup(id="demo", name="Demo cohort", member_ids=("a-one", "b-two")),
        GENERATED_AT,
        attention={"a-one": "Service data expires in 12 days"},
    )
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
