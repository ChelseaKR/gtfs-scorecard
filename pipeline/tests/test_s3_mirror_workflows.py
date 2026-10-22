"""The workflows that read the artifacts bucket keep a cached mirror, safely.

Intraday refresh and Deploy site each pulled the same bounded set (every
agency's latest.json plus today's and yesterday's dated snapshots) from S3 on
every run, eight cycles a day. They now sync into a mirror restored from the
Actions cache. The shape that keeps that correct and private is asserted here
from the parsed workflow, not from a regular expression over its text:

- the sync into the mirror uses ``--exact-timestamps`` (the default download
  rule skips a same-size object whose local copy is older) and ``--delete``;
- the mirror holds public data only: nothing under the private cache/ prefix;
- the cache is saved once per UTC day, never per run, and only on a miss;
- the overlay script runs after the sync and before anything reads the tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

# (workflow file, job id, key family, name of the step that hydrates)
CASES = [
    ("refresh.yml", "refresh", "refresh", "Hydrate current artifacts from S3"),
    ("pages.yml", "lighthouse", "pages", "Sync published artifacts from S3"),
]
PRIVATE_PREFIXES = ("cache/", "fixlog", "structure", "validator-cache")


def _steps(workflow: str, job: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    return list(data["jobs"][job]["steps"])


def _step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}"
    return matches[0]


def _joined(run: str) -> str:
    return re.sub(r"\\\n\s*", " ", run)


def _mirror_sync(run: str) -> str:
    """The one `aws s3 sync` command that writes into the mirror."""
    commands = [
        line
        for line in _joined(run).splitlines()
        if "aws s3 sync" in line and '"$mirror"' in line and not line.lstrip().startswith("#")
    ]
    assert len(commands) == 1, "exactly one sync writes into the mirror"
    return commands[0]


def _violations(command: str) -> list[str]:
    """What is wrong with a mirror sync command; empty when it is safe."""
    problems = []
    for needed in (
        "--exact-timestamps",
        "--delete",
        '--exclude "*"',
        "s3://${{ vars.ARTIFACTS_BUCKET }}/data/artifacts",
        '--include "*/latest.json"',
        '--include "*/${today}.json"',
        '--include "*/${yesterday}.json"',
    ):
        if needed not in command:
            problems.append(f"missing {needed}")
    for private in PRIVATE_PREFIXES:
        if private in command:
            problems.append(f"the mirror must not hold {private!r}")
    # The commit pointer changes every cycle; it is copied, not cached.
    if '--include "index.json"' in command:
        problems.append("index.json must be copied, not mirrored")
    return problems


@pytest.mark.parametrize(("workflow", "job", "family", "hydrate"), CASES)
def test_mirror_sync_is_exact_deleting_and_public_only(
    workflow: str, job: str, family: str, hydrate: str
) -> None:
    command = _mirror_sync(_step(_steps(workflow, job), hydrate)["run"])

    assert _violations(command) == []


@pytest.mark.parametrize(("workflow", "job", "family", "hydrate"), CASES)
def test_negative_control_each_unsafe_edit_is_caught(
    workflow: str, job: str, family: str, hydrate: str
) -> None:
    """Sabotage the real command and show the check notices; assert each edit applied."""
    command = _mirror_sync(_step(_steps(workflow, job), hydrate)["run"])
    edits = {
        "drops exact timestamps": command.replace("--exact-timestamps", ""),
        "drops delete": command.replace("--delete", ""),
        "mirrors the fix-log cache": command + " --include 'cache/fixlog/*'",
        "mirrors the pointer": command + ' --include "index.json"',
        "syncs the whole prefix": command.replace('--exclude "*"', ""),
    }
    for label, edited in edits.items():
        assert edited != command, f"the sabotage that {label} did not apply"
        assert _violations(edited), f"nothing noticed the edit that {label}"


@pytest.mark.parametrize(("workflow", "job", "family", "hydrate"), CASES)
def test_overlay_runs_after_the_sync_and_the_pointer_is_copied(
    workflow: str, job: str, family: str, hydrate: str
) -> None:
    run = _joined(_step(_steps(workflow, job), hydrate)["run"])

    assert run.index("aws s3 sync") < run.index("scripts/overlay-s3-mirror.sh")
    assert 'scripts/overlay-s3-mirror.sh "$mirror" data/artifacts "$today" "$yesterday"' in run
    assert "aws s3 cp" in run and "data/artifacts/index.json" in run


def test_pages_reads_the_pointer_before_any_agency_file() -> None:
    """Reading index.json first keeps the generation order the pages guard expects."""
    run = _joined(
        _step(_steps("pages.yml", "lighthouse"), "Sync published artifacts from S3")["run"]
    )

    pointer = run.index("data/artifacts/index.json")
    assert pointer < run.index("aws s3 sync")


@pytest.mark.parametrize(("workflow", "job", "family", "hydrate"), CASES)
def test_cache_is_restored_by_day_and_saved_once_a_day_on_a_miss(
    workflow: str, job: str, family: str, hydrate: str
) -> None:
    steps = _steps(workflow, job)
    restore = next(s for s in steps if str(s.get("uses", "")).startswith("actions/cache/restore"))
    save = next(s for s in steps if str(s.get("uses", "")).startswith("actions/cache/save"))
    prefix = f"public-artifact-mirror-v1-{family}-"
    key = f"{prefix}${{{{ steps.mirror-day.outputs.today }}}}"

    assert restore["with"]["key"] == key
    assert restore["with"]["restore-keys"].strip() == prefix
    assert save["with"]["key"] == key
    assert save["with"]["path"] == restore["with"]["path"]
    # Never per run: a run id in the key would write a ~400 MB entry every cycle.
    assert "run_id" not in key and "run_attempt" not in key
    assert f"steps.{restore['id']}.outputs.cache-hit != 'true'" in save["if"]
    names = [s.get("name") for s in steps]
    assert names.index(restore["name"]) < names.index(hydrate) < names.index(save["name"])


def test_pages_keeps_its_route_geometry_mirror_separate() -> None:
    """The geometry mirror is keyed per run on purpose; the new one must not share it."""
    steps = _steps("pages.yml", "lighthouse")
    keys = [
        s["with"]["key"] for s in steps if str(s.get("uses", "")).startswith("actions/cache/save")
    ]
    assert len(keys) == 2
    assert len(set(keys)) == 2
    assert any(key.startswith("route-geometry-v1-") for key in keys)
