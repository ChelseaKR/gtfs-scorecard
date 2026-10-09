"""What the repository says about PyPI and the MCP registry must match what exists.

`gtfs-scorecard` has never been uploaded to PyPI, and `server.json` has never
been submitted to the MCP registry. A 2026-07-05 revision of `server.json`
declared `registryType: pypi` while nothing was on PyPI, and was rolled back for
that reason. This file holds the second attempt to the same bar. The
distribution was named `scorecard-pipeline` until 1.5.1: the v1.5.0 run of the
publish workflow reached the upload and PyPI refused that name as too similar
to the unrelated project `scorecardpipeline`, so nothing was uploaded under it.

Two states, one committed field: `server.json`
`_meta["dev.chelseakr/distribution"].pypi_first_upload` is `null` until the first
upload is confirmed on pypi.org, then the version that was uploaded.

* While it is `null`, any document that shows a PyPI install line
  (`uvx gtfs-scorecard`, `uvx --from gtfs-scorecard scorecard`,
  `pip install gtfs-scorecard`) must also carry the hedge "Once gtfs-scorecard
  is on PyPI", and the source-tree install that works today must still be there.
* Once it is set, the hedge must be gone and the PyPI install line present.

Both directions are checked against synthetic documents as well as the real
ones, so the test passes before the upload and after the follow-up change that
records it. Flipping the field is a documentation change made after the upload;
no release tag has to move for it, which is what keeps this out of the
first-release deadlock where the commit you tag was written for the other world.

The `packages[]` entry is present in both states. It describes the upload the
publish workflow makes for the release tag, and the MCP registry itself refuses
a submission whose package is not on PyPI, so the entry is never served before
it is true.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "pipeline"

CLAIM_FILES = ("README.md", "docs/api.md", "docs/mcp.md", "pipeline/README.md")
DISTRIBUTION = "gtfs-scorecard"
HEDGE = f"once {DISTRIBUTION} is on pypi"
PYPI_INSTALL = re.compile(
    rf"uvx {DISTRIBUTION}\b"
    rf"|uvx --from {DISTRIBUTION}\b"
    rf"|pip install {DISTRIBUTION}\b"
    rf"|\"args\": \[\"{DISTRIBUTION}\"\]"
)
SOURCE_INSTALL = "git+https://github.com/ChelseaKR/gtfs-scorecard#subdirectory=pipeline"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "pypi-publish.yml"


def _server() -> dict[str, Any]:
    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((PIPELINE / "pyproject.toml").read_text(encoding="utf-8"))


def _first_upload() -> str | None:
    state = _server()["_meta"]["dev.chelseakr/distribution"]
    value = state["pypi_first_upload"]
    assert value is None or isinstance(value, str)
    return value


def claim_problems(first_upload: str | None, texts: dict[str, str]) -> list[str]:
    """Every way the install wording disagrees with the recorded PyPI state."""
    problems: list[str] = []
    for name, text in texts.items():
        lowered = text.lower()
        shows_pypi = PYPI_INSTALL.search(text) is not None
        hedged = HEDGE in lowered
        if first_upload is None:
            if shows_pypi and not hedged:
                problems.append(
                    f"{name} shows a PyPI install line, nothing is on PyPI yet, and it "
                    f"does not say {HEDGE!r}"
                )
            if SOURCE_INSTALL not in text:
                problems.append(
                    f"{name} lost the source-tree install, the only install that works "
                    "until the first upload"
                )
        else:
            if hedged:
                problems.append(
                    f"{name} still says {HEDGE!r}, but {first_upload} is recorded as uploaded"
                )
            if not shows_pypi:
                problems.append(f"{name} does not show the PyPI install line")
    return problems


def _texts() -> dict[str, str]:
    return {name: (ROOT / name).read_text(encoding="utf-8") for name in CLAIM_FILES}


def test_install_wording_matches_the_recorded_pypi_state() -> None:
    assert claim_problems(_first_upload(), _texts()) == []


HEDGED = (
    f"Once {DISTRIBUTION} is on PyPI, `uvx {DISTRIBUTION}` works.\n"
    f"Until then: uvx --from {SOURCE_INSTALL} scorecard-mcp\n"
)
PLAIN = f"Install with `uvx {DISTRIBUTION}`.\n"
PLAIN_CLI = f"Install with `uvx --from {DISTRIBUTION} scorecard`.\n"


@pytest.mark.parametrize(
    ("first_upload", "text", "expected"),
    [
        (None, HEDGED, 0),
        (None, PLAIN + SOURCE_INSTALL, 1),  # an unhedged claim before the upload
        (None, PLAIN_CLI + SOURCE_INSTALL, 1),  # the CLI form is a PyPI claim too
        (None, f"Once {DISTRIBUTION} is on PyPI, `uvx {DISTRIBUTION}`.", 1),
        ("1.5.1", PLAIN, 0),
        ("1.5.1", PLAIN_CLI, 0),
        ("1.5.1", HEDGED, 1),  # a hedge left behind after the upload
        ("1.5.1", "Install from a checkout.", 1),  # the PyPI line never added
    ],
)
def test_claim_rule_holds_in_both_states(
    first_upload: str | None, text: str, expected: int
) -> None:
    assert len(claim_problems(first_upload, {"doc": text})) == expected


def test_recorded_first_upload_is_not_newer_than_the_declared_version() -> None:
    first = _first_upload()
    if first is None:
        return
    declared = _pyproject()["project"]["version"]

    def key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in v.split("."))

    assert key(first) <= key(declared), (first, declared)


def test_server_json_names_the_package_the_publish_workflow_uploads() -> None:
    server = _server()
    project = _pyproject()["project"]
    packages = server["packages"]
    assert len(packages) == 1, packages
    package = packages[0]
    assert package["registryType"] == "pypi"
    assert package["registryBaseUrl"] == "https://pypi.org"
    assert package["identifier"] == project["name"] == DISTRIBUTION
    assert package["version"] == project["version"] == server["version"]
    assert package["transport"] == {"type": "stdio"}
    assert package.get("runtimeHint") == "uvx"


def test_server_name_casing_matches_the_github_owner() -> None:
    """The registry grants `io.github.<login>/*` with GitHub's own casing and
    matches it case-sensitively (modelcontextprotocol/registry#689), so a
    lowercase `chelseakr` namespace is refused for the `ChelseaKR` login. The
    name is also baked into the PyPI description, which cannot be edited after
    upload, so it has to be right before the first one."""
    server = _server()
    owner = server["repository"]["url"].removeprefix("https://github.com/").split("/")[0]
    assert owner == "ChelseaKR"
    assert server["name"] == f"io.github.{owner}/gtfs-scorecard"


def test_server_description_fits_the_registry_limit() -> None:
    # The registry's validate endpoint rejected the previous 186-character text
    # with "expected length <= 100" (checked 2026-10-05 with mcp-publisher 1.8.1).
    assert len(_server()["description"]) <= 100


def test_package_readme_carries_the_registry_ownership_marker() -> None:
    project = _pyproject()["project"]
    assert project["readme"] == "README.md"
    readme = (PIPELINE / "README.md").read_text(encoding="utf-8")
    marker = f"<!-- mcp-name: {_server()['name']} -->"
    assert marker in readme.splitlines(), (
        "the MCP registry verifies PyPI ownership by finding this marker, followed by "
        "a boundary, in the package description"
    )


def test_uvx_with_the_package_name_starts_the_mcp_server() -> None:
    """`uvx <distribution>` runs the executable named after the distribution, so
    the MCP registry's install line only works while a script carries exactly
    the project name. The CLI keeps its own name and needs `--from`."""
    project = _pyproject()["project"]
    scripts = project["scripts"]
    assert scripts[project["name"]] == "scorecard_pipeline.mcp_server:main"
    assert scripts["scorecard-mcp"] == "scorecard_pipeline.mcp_server:main"
    assert scripts["scorecard"] == "scorecard_pipeline.cli:main"
    assert "scorecard-pipeline" not in scripts, "the old distribution name is not an alias"


def test_packaged_schema_is_a_byte_copy_of_the_published_one() -> None:
    name = "sync-source-metadata-1.2.schema.json"
    packaged = PIPELINE / "src" / "scorecard_pipeline" / "data" / "schemas" / name
    assert packaged.read_bytes() == (ROOT / "web" / "schemas" / name).read_bytes()


def test_no_build_input_lives_outside_the_project_directory() -> None:
    """A wheel built from the sdist cannot see `../anything`. That broke the
    first `uv build` attempt (2026-10-05), which is the build PyPI publishing does."""
    hatch = _pyproject()["tool"]["hatch"]["build"]["targets"]
    for target in hatch.values():
        for source in target.get("force-include", {}):
            assert not str(source).startswith(".."), source


def test_action_archive_keeps_the_package_readme() -> None:
    # The Action runs `uv run --project pipeline`, which builds the project, and
    # hatchling refuses to build when the declared readme is missing.
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "/pipeline/README.md -export-ignore" in attributes


def _publish_workflow() -> dict[Any, Any]:
    doc = yaml.safe_load(PUBLISH_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def test_only_the_reviewed_environment_can_upload() -> None:
    doc = _publish_workflow()
    assert doc["permissions"] == {}
    jobs = doc["jobs"]
    minting = [name for name, job in jobs.items() if job.get("permissions", {}).get("id-token")]
    assert minting == ["publish"]
    assert jobs["publish"]["environment"]["name"] == "pypi"
    assert jobs["publish"]["needs"] == "build"
    steps = jobs["build"]["steps"]
    names = [step.get("name", "") for step in steps]
    assert "Verify the signed release tag" in names
    assert "Refuse to continue without a reviewed pypi environment" in names
    check = next(s for s in steps if s.get("name", "").startswith("Refuse to continue"))
    assert 'select(.type == "required_reviewers")' in check["run"]


def test_docs_give_the_pending_publisher_values_the_workflow_uses() -> None:
    mcp = (ROOT / "docs" / "mcp.md").read_text(encoding="utf-8")
    for value in (DISTRIBUTION, "ChelseaKR", "gtfs-scorecard", PUBLISH_WORKFLOW.name):
        assert value in mcp
    assert "`pypi`" in mcp


def test_the_workflow_and_the_ci_build_name_the_distribution() -> None:
    """The wheel and sdist are named after the distribution (`gtfs_scorecard-...`),
    and both workflows glob for them by that name. A rename that missed either
    would fail only at the tag."""
    publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    normalized = DISTRIBUTION.replace("-", "_")
    assert f"dist/{normalized}-" in publish
    assert f"dist/{normalized}-" in ci
    assert f'.identifier == "{DISTRIBUTION}"' in publish
    assert f"https://pypi.org/project/{DISTRIBUTION}/" in publish
    assert f"https://pypi.org/pypi/{DISTRIBUTION}/" in publish
    for old in ("scorecard_pipeline-", "pypi.org/project/scorecard-pipeline"):
        assert old not in publish, old
        assert old not in ci, old
