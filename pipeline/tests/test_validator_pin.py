"""One validator release, one digest, everywhere the jar is used.

The validator jar is run as a program in four places: the pipeline's own
download path (``validate.ensure_validator``, which the daily job and the
reusable Action both go through), the two container images that bake the jar
in, and the canary that tries a candidate release. Each of them checks a
SHA-256 before the jar runs. This file holds them to the same version and the
same digest, so a version bump that updates one and not the others fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scorecard_pipeline import validate

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = ("infra/compute/Dockerfile", "infra/instant-score/Dockerfile")


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_container_image_bakes_the_pinned_version_and_digest(dockerfile: str) -> None:
    text = (ROOT / dockerfile).read_text(encoding="utf-8")
    versions = set(re.findall(r"data/cache/gtfs-validator-(\d+\.\d+\.\d+)-cli\.jar", text))
    digests = set(re.findall(r'^RUN echo "([0-9a-f]{64})  ', text, flags=re.MULTILINE))

    assert versions == {validate.VALIDATOR_VERSION}, dockerfile
    assert digests == {validate.VALIDATOR_JAR_SHA256[validate.VALIDATOR_VERSION]}, dockerfile
    assert "sha256sum -c -" in text, dockerfile


def test_every_pinned_digest_is_a_lowercase_sha256() -> None:
    assert validate.VALIDATOR_VERSION in validate.VALIDATOR_JAR_SHA256
    for version, digest in validate.VALIDATOR_JAR_SHA256.items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
        assert re.fullmatch(r"[0-9a-f]{64}", digest), version


def test_the_download_path_is_the_only_way_a_jar_reaches_java() -> None:
    """``run_validator`` takes its jar from ``ensure_validator`` and nowhere else."""
    source = Path(str(validate.__file__)).read_text(encoding="utf-8")
    assert source.count('"-jar"') == 1
    assert "jar = ensure_validator(version, sha256=jar_sha256)" in source
    # No workflow or the Action fetches the jar itself: they would bypass the check.
    fetchers = [
        str(path.relative_to(ROOT))
        for path in [ROOT / "action.yml", *sorted((ROOT / ".github" / "workflows").glob("*.yml"))]
        if "gtfs-validator/releases/download" in path.read_text(encoding="utf-8")
    ]
    assert fetchers == [".github/workflows/container-scan.yml"]
    container_scan = (ROOT / ".github/workflows/container-scan.yml").read_text(encoding="utf-8")
    assert 'echo "${jar_sha256}  ${jar_rel}" | sha256sum -c -' in container_scan


def test_the_canary_workflow_requires_and_passes_the_candidate_digest() -> None:
    workflow = (ROOT / ".github/workflows/validator-canary.yml").read_text(encoding="utf-8")
    declared = workflow.split("candidate_sha256:", 1)[1].split("sample_size:", 1)[0]
    assert "required: true" in declared
    # Through env, never inline in the run body.
    assert "CANDIDATE_SHA256: ${{ inputs.candidate_sha256 }}" in workflow
    assert '--candidate-sha256 "$CANDIDATE_SHA256"' in workflow
    run_body = workflow.split("run: |", 1)[1]
    assert "${{ inputs." not in run_body.split("- name:", 1)[0]
