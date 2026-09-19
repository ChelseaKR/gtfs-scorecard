"""Contract tests: the generated Python client against recorded responses of the read API.

Nothing here touches a network. `httpx.MockTransport` serves recorded files, the
way the real host serves them, and the generated code parses what it is given.
The recordings are `pipeline/tests/fixtures/golden_site` (what the renderer
writes for three agencies), plus real files copied out of `data/artifacts/`
under `clients/fixtures/`. `clients/fixtures/manifest.json` names the file
behind every documented path, and `pipeline/tests/test_clients_drift.py` holds
that manifest to the description.

Three things are asserted, in this order of importance:

1. Every documented response parses, and the parsed model writes back the exact
   JSON it was read from. A field the model dropped, coerced or invented shows
   up as a difference.
2. A value the scorecard did not measure never becomes a number. An absent
   field is `UNSET`, an explicit null is `None`, a measured zero is `0`.
3. A `schema_version` major the client was not generated for is refused.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import gtfs_scorecard_client as package
import httpx
import pytest
from gtfs_scorecard_client import (
    SUPPORTED_SCHEMA_MAJOR,
    UNSET,
    Unset,
    UnsupportedSchemaVersion,
    check_schema_version,
    make_client,
)
from gtfs_scorecard_client.generated import api as api_package
from gtfs_scorecard_client.generated import errors
from gtfs_scorecard_client.generated.models.artifact import Artifact
from gtfs_scorecard_client.generated.models.artifact_category_status import ArtifactCategoryStatus
from gtfs_scorecard_client.generated.models.catalog import Catalog

CLIENTS = Path(__file__).resolve().parents[2]
REPO = CLIENTS.parent
MANIFEST = json.loads((CLIENTS / "fixtures" / "manifest.json").read_text(encoding="utf-8"))
SPEC = json.loads((CLIENTS / "openapi.bundled.json").read_text(encoding="utf-8"))
SAMPLES: dict[str, str] = MANIFEST["samples"]
RECORDED_ARTIFACTS = sorted((CLIENTS / "fixtures" / "artifacts").glob("*.json"))
BASE_URL = "https://scorecard.test"

# The operations whose 200 names a published JSON Schema, and the model each one
# must return. Written out so that a schema losing its `$ref` (and so its type)
# fails here instead of degrading quietly to an untyped object.
TYPED_OPERATIONS = {
    "/data/artifacts/directory.json": "Directory",
    "/data/artifacts/{agency_id}/latest.json": "Artifact",
    "/data/artifacts/{agency_id}/{date}.json": "Artifact",
    "/data/artifacts/rollups/index.json": "RollupIndex",
    "/data/artifacts/rollups/{rollup_id}.json": "Rollup",
    "/catalog.json": "Catalog",
    "/api/v1/by-location.json": "ByLocation",
    "/api/v1/coverage.json": "Coverage",
    "/api/v1/global-coverage.json": "GlobalCoverage",
}


def _module_for_each_path() -> dict[str, ModuleType]:
    """URL template -> generated endpoint module, read from the URL each one requests."""
    root = Path(api_package.__file__).parent
    found: dict[str, ModuleType] = {}
    for source in sorted(root.rglob("*.py")):
        if source.name == "__init__.py":
            continue
        match = re.search(r'"url": "([^"]+)"', source.read_text(encoding="utf-8"))
        assert match, f"{source} requests no URL"
        dotted = ".".join(source.relative_to(root).with_suffix("").parts)
        found[match.group(1)] = importlib.import_module(f"{api_package.__name__}.{dotted}")
    return found


MODULES = _module_for_each_path()


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = SPEC
        for part in node["$ref"][2:].split("/"):
            target = target[part]
        node = target
    return node


def _success(path: str) -> tuple[str, dict[str, Any]]:
    """The media type and schema of a path's 200 response."""
    response = _resolve(SPEC["paths"][path]["get"]["responses"]["200"])
    media_type, media = next(iter(response["content"].items()))
    return media_type, media.get("schema", {})


def _kwargs(path: str) -> dict[str, str]:
    return {name: SAMPLES[name] for name in re.findall(r"{(\w+)}", path)}


def _concrete(path: str) -> str:
    return path.format(**SAMPLES)


def _recorded(path: str) -> bytes:
    file = MANIFEST["responses"][path]
    assert file is not None, f"{path} has no recording"
    return (REPO / file).read_bytes()


def serve(routes: dict[str, tuple[bytes, str]]) -> httpx.MockTransport:
    """A transport that serves `{url path: (body, content type)}` and 404s the rest."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            body, media_type = routes[request.url.path]
            return httpx.Response(200, content=body, headers={"content-type": media_type})
        return httpx.Response(404, content=b"not found")

    return httpx.MockTransport(handle)


def _client_serving(path: str, body: bytes) -> Any:
    media_type, _ = _success(path)
    return make_client(BASE_URL, transport=serve({_concrete(path): (body, media_type)}))


RECORDED_PATHS = sorted(p for p, f in MANIFEST["responses"].items() if f is not None)


# --- 1. every documented response parses, and writes back what it read ----------


def test_every_documented_path_has_a_generated_operation() -> None:
    assert set(SPEC["paths"]) == set(MODULES), (
        "the description and the generated client disagree about which paths exist: "
        f"{sorted(set(SPEC['paths']) ^ set(MODULES))}"
    )
    assert len(MODULES) >= 50


@pytest.mark.parametrize("path", RECORDED_PATHS)
def test_the_client_parses_the_recorded_response_and_writes_it_back(path: str) -> None:
    body = _recorded(path)
    media_type, schema = _success(path)
    response = MODULES[path].sync_detailed(client=_client_serving(path, body), **_kwargs(path))

    assert response.status_code == 200
    assert response.content == body

    if media_type == "application/json":
        raw = json.loads(body)
        if raw is None:
            # run-status.json is JSON null until a run publishes one.
            assert response.parsed is None
            return
        assert response.parsed is not None, f"{path}: a JSON object did not parse"
        assert response.parsed.to_dict() == raw, f"{path}: the model does not write back its input"
        expected = TYPED_OPERATIONS.get(path)
        if expected is not None:
            assert type(response.parsed).__name__ == expected
    elif media_type.startswith("text/"):
        # CSV and YAML come back as text.
        assert response.parsed == body.decode("utf-8")
    else:
        # Parquet, SVG and Atom are not modeled. The bytes must still arrive.
        assert response.parsed is None
        assert schema.get("type") in (None, "string")


def test_the_paths_without_a_recording_are_named_with_a_reason() -> None:
    unrecorded = {p for p, f in MANIFEST["responses"].items() if f is None}
    assert unrecorded == set(MANIFEST["not_recorded"]), "an unrecorded path must say why"


def test_an_unrecorded_path_is_served_as_the_documented_404() -> None:
    path = "/api/v1/ridership-impact.json"
    client = make_client(BASE_URL, transport=serve({}))
    response = MODULES[path].sync_detailed(client=client)
    assert response.status_code == 404
    assert response.parsed is None
    assert "404" in SPEC["paths"][path]["get"]["responses"]


def test_the_schema_backed_operations_are_exactly_the_nine_that_are_typed() -> None:
    typed = {
        path
        for path in SPEC["paths"]
        if _success(path)[0] == "application/json" and "$ref" in _success(path)[1]
    }
    assert typed == set(TYPED_OPERATIONS)


def test_each_recorded_artifact_round_trips() -> None:
    assert len(RECORDED_ARTIFACTS) >= 6
    for file in RECORDED_ARTIFACTS:
        raw = json.loads(file.read_text(encoding="utf-8"))
        assert Artifact.from_dict(raw).to_dict() == raw, file.name


def test_a_grade_distribution_with_a_d_parses() -> None:
    """The generator wrote `d = d.pop("D")` here until generate_clients.py patched it.

    Both `by-location.json` and every rollup carry a grade distribution with the
    keys A to F. The property `d` shadowed the local dict `d`, so parsing them
    raised `AttributeError: 'int' object has no attribute 'pop'`.
    """
    for path in ("/api/v1/by-location.json", "/data/artifacts/rollups/{rollup_id}.json"):
        parsed = (
            MODULES[path]
            .sync_detailed(client=_client_serving(path, _recorded(path)), **_kwargs(path))
            .parsed
        )
        assert parsed is not None
        assert parsed.to_dict() == json.loads(_recorded(path))


def test_the_async_path_parses_the_same_response() -> None:
    path = "/data/artifacts/{agency_id}/latest.json"
    media_type, _ = _success(path)
    client = make_client(
        BASE_URL, async_transport=httpx.MockTransport(_async_handler(path, media_type))
    )

    async def fetch() -> Any:
        return await MODULES[path].asyncio_detailed(client=client, **_kwargs(path))

    response = asyncio.run(fetch())
    assert response.status_code == 200
    assert response.parsed.to_dict() == json.loads(_recorded(path))


def _async_handler(path: str, media_type: str) -> Callable[[httpx.Request], httpx.Response]:
    body = _recorded(path)

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": media_type})

    return handle


# --- 2. absence is never a number ------------------------------------------------


def _artifact(name_fragment: str) -> tuple[dict[str, Any], Artifact]:
    file = next(f for f in RECORDED_ARTIFACTS if name_fragment in f.name)
    raw = json.loads(file.read_text(encoding="utf-8"))
    return raw, Artifact.from_dict(raw)


def test_an_unmeasured_category_has_no_score_rather_than_a_zero() -> None:
    raw, artifact = _artifact("tper-marconi-express")
    realtime = artifact.categories.realtime

    assert raw["categories"]["realtime"]["status"] == "not_yet_measured"
    assert "score" not in raw["categories"]["realtime"]
    assert realtime.status is ArtifactCategoryStatus.NOT_YET_MEASURED
    assert isinstance(realtime.score, Unset)
    assert realtime.score is UNSET
    assert realtime.score != 0
    # UNSET is falsy exactly as 0 is, which is why the README says not to test truthiness.
    assert not realtime.score
    assert "score" not in realtime.to_dict()
    # The categories the scorecard did measure keep their numbers.
    assert artifact.categories.correctness.score == raw["categories"]["correctness"]["score"]


def test_a_measured_zero_stays_a_zero() -> None:
    """The mirror image: a real 0.0 must not be read as absence.

    Anchorage People Mover's realtime sample found its one feed unhealthy, so
    its catalog row says `realtime: 0.0`, a measurement, not a gap.
    """
    catalog = Catalog.from_dict(
        json.loads((CLIENTS / "fixtures" / "documents" / "catalog-trimmed.json").read_text())
    )
    rows = {row.id: row for row in catalog.agencies}
    measured_zero = rows["anchorage-people-mover"]
    assert measured_zero.realtime == 0.0
    assert not isinstance(measured_zero.realtime, Unset)
    assert measured_zero.realtime is not None


def test_a_null_stays_null_and_is_not_a_zero() -> None:
    catalog = Catalog.from_dict(
        json.loads((CLIENTS / "fixtures" / "documents" / "catalog-trimmed.json").read_text())
    )
    rows = {row.id: row for row in catalog.agencies}
    for agency_id in ("barrie-transit", "london-transit-commission", "10-15-transit"):
        row = rows[agency_id]
        assert row.realtime is None, agency_id
        assert row.national_percentile is None, agency_id
    # A null the row did not say at all is a different thing again.
    assert rows["barrie-transit"].ntd_ready is None


def test_absent_and_null_come_back_as_they_went_in() -> None:
    raw = json.loads((CLIENTS / "fixtures" / "documents" / "catalog-trimmed.json").read_text())
    written = Catalog.from_dict(raw).to_dict()
    for before, after in zip(raw["agencies"], written["agencies"], strict=True):
        assert before.keys() == after.keys(), before["id"]
        assert before.get("realtime", "<absent>") == after.get("realtime", "<absent>")


def test_the_round_trip_check_can_tell_a_zero_from_an_absence() -> None:
    """Negative control: turning the absent score into 0.0 must be visible.

    If this passed, every equality above would be blind to the one mistake this
    client exists to prevent.
    """
    raw, artifact = _artifact("tper-marconi-express")
    artifact.categories.realtime.score = 0.0
    written = artifact.to_dict()
    assert written["categories"]["realtime"]["score"] == 0.0
    assert written != raw


def test_every_unmeasured_realtime_category_in_the_recordings_is_unset() -> None:
    seen = 0
    for file in RECORDED_ARTIFACTS:
        raw = json.loads(file.read_text(encoding="utf-8"))
        realtime = Artifact.from_dict(raw).categories.realtime
        if raw["categories"]["realtime"]["status"] == "not_yet_measured":
            seen += 1
            assert realtime.score is UNSET, file.name
        else:
            assert isinstance(realtime.score, float), file.name
    assert seen >= 3, "the recordings no longer include unmeasured realtime categories"


# --- 3. the schema_version guard ------------------------------------------------


def _unitrans() -> dict[str, Any]:
    return json.loads(_recorded("/data/artifacts/{agency_id}/latest.json"))


def _served(document: dict[str, Any]) -> httpx.MockTransport:
    path = _concrete("/data/artifacts/{agency_id}/latest.json")
    return serve({path: (json.dumps(document).encode(), "application/json")})


def _fetch_latest(client: Any) -> Any:
    return MODULES["/data/artifacts/{agency_id}/latest.json"].sync(
        agency_id="unitrans", client=client
    )


def test_the_supported_major_is_the_one_the_description_names() -> None:
    assert SPEC["info"]["x-artifact-schema-version-major"] == SUPPORTED_SCHEMA_MAJOR


def test_a_major_version_bump_makes_the_guard_fail() -> None:
    bumped = {**_unitrans(), "schema_version": "2.0"}
    with pytest.raises(UnsupportedSchemaVersion) as raised:
        _fetch_latest(make_client(BASE_URL, transport=_served(bumped)))
    assert raised.value.found == "2.0"
    assert "Upgrade the client" in str(raised.value)


def test_a_minor_version_bump_is_tolerated() -> None:
    document = {**_unitrans(), "schema_version": "1.99", "a_future_field": {"added": True}}
    artifact = _fetch_latest(make_client(BASE_URL, transport=_served(document)))
    assert artifact.overall.grade == document["overall"]["grade"]
    assert artifact.schema_version == "1.99"
    # The artifact's schema is closed at the top level, so the generator gives it no
    # place to keep a field it has not heard of. It is tolerated, not preserved:
    # reading it takes a newer client. The README says so.
    assert "a_future_field" not in artifact.to_dict()


def test_the_async_client_is_guarded_too() -> None:
    bumped = {**_unitrans(), "schema_version": "2.0"}
    path = "/data/artifacts/{agency_id}/latest.json"
    client = make_client(
        BASE_URL, async_transport=httpx.MockTransport(_bumped_handler(path, bumped))
    )

    async def fetch() -> Any:
        return await MODULES[path].asyncio(agency_id="unitrans", client=client)

    with pytest.raises(UnsupportedSchemaVersion):
        asyncio.run(fetch())


def _bumped_handler(
    path: str, document: dict[str, Any]
) -> Callable[[httpx.Request], httpx.Response]:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps(document).encode(), headers={"content-type": "application/json"}
        )

    return handle


def test_the_guard_can_be_turned_off() -> None:
    bumped = {**_unitrans(), "schema_version": "2.0"}
    artifact = _fetch_latest(make_client(BASE_URL, guard=False, transport=_served(bumped)))
    assert artifact.schema_version == "2.0"


def test_a_document_versioned_separately_is_guarded_too() -> None:
    """`dataset.json` has its own version series; the guard reads any `schema_version`."""
    path = "/dataset.json"
    document = {**json.loads(_recorded(path)), "schema_version": "2.0"}
    client = make_client(
        BASE_URL, transport=serve({path: (json.dumps(document).encode(), "application/json")})
    )
    with pytest.raises(UnsupportedSchemaVersion):
        MODULES[path].sync(client=client)


def test_a_null_body_and_a_non_json_body_are_not_versioned_documents() -> None:
    for path in ("/api/v1/run-status.json", "/catalog.csv", "/changes/feed.xml"):
        response = MODULES[path].sync_detailed(client=_client_serving(path, _recorded(path)))
        assert response.status_code == 200, path


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"schema_version": "2.0"}, "major version 2"),
        ({"schema_version": 2}, "major version 2"),
        ({"schema_version": None}, "not a version string"),
        ({"schema_version": True}, "not a version string"),
        ({"schema_version": ["1"]}, "not a version string"),
        ({}, "no schema_version"),
        ("3.1", "major version 3"),
    ],
)
def test_the_guard_refuses_what_it_cannot_vouch_for(document: object, message: str) -> None:
    with pytest.raises(UnsupportedSchemaVersion, match=message):
        check_schema_version(document)


def test_the_guard_accepts_a_mapping_a_model_and_a_bare_version() -> None:
    raw = _unitrans()
    check_schema_version(raw)
    check_schema_version(Artifact.from_dict(raw))
    check_schema_version("1.19")
    check_schema_version(1)
    check_schema_version({}, require=False)
    with pytest.raises(UnsupportedSchemaVersion):
        check_schema_version("1.19", supported_major="2")


# --- 4. the rest of the surface -------------------------------------------------


def test_an_undocumented_status_can_raise() -> None:
    path = "/data/artifacts/{agency_id}/latest.json"
    client = make_client(BASE_URL, transport=serve({}), raise_on_unexpected_status=True)
    # 404 is documented for this operation, so it parses to None instead of raising.
    assert MODULES[path].sync_detailed(agency_id="nowhere", client=client).parsed is None
    dated = MODULES["/data/artifacts/{agency_id}/{date}.json"]
    with pytest.raises(errors.UnexpectedStatus):
        dated.sync_detailed(agency_id="nowhere", date="2026-01-01", client=client)


def test_the_readme_example_reads_as_it_says() -> None:
    path = "/data/artifacts/{agency_id}/latest.json"
    artifact = MODULES[path].sync(
        agency_id="unitrans", client=_client_serving(path, _recorded(path))
    )
    assert artifact.overall.grade.value in "ABCDF"
    lines = []
    for name in ("correctness", "freshness", "completeness", "realtime"):
        category = getattr(artifact.categories, name)
        lines.append((name, category.status.value, category.score))
    assert ("realtime", "not_yet_measured", UNSET) in lines


def test_the_package_reexports_its_documented_surface() -> None:
    assert set(package.__all__) == {
        "DEFAULT_BASE_URL",
        "SUPPORTED_SCHEMA_MAJOR",
        "UNSET",
        "Client",
        "UnsupportedSchemaVersion",
        "Unset",
        "check_schema_version",
        "make_client",
    }
    assert package.DEFAULT_BASE_URL == "https://gtfsscorecard.org"
