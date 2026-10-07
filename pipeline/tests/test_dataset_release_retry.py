"""A monthly job gets one attempt a year at each month, and 2026-09 spent it.

Run 33553673342 (2026-09-01) failed in "Assemble the release bundle" —
`expected-latest-ids` and `actual-latest-ids` differed at line 294 — and
`dataset-2026-09` does not exist. (The cause was the site-wide
`changes/latest.json` counted as an agency; test_dataset_release.py holds the
fix.) Nothing retried it and nothing noticed: this workflow is not
read by any page and has no cadence to go stale against, so a failed cut is
invisible until somebody opens the Actions tab a month later.

Day 1 is now followed by two retry fires, and a `decide` job keeps a healthy
month at exactly one run. These tests hold the parts of that which are easy to
lose: the retries themselves, the guard that makes them free, and the two ways
the guard could quietly stop guarding — reading the tag instead of the run, and
turning an unanswerable question into a pass.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / ".github" / "workflows" / "dataset-release.yml"
TEXT = PATH.read_text(encoding="utf-8")
# PyYAML reads the bare `on:` key as the boolean True, so the mapping is not
# keyed by str alone.
WORKFLOW: dict[Any, Any] = yaml.safe_load(TEXT)
TRIGGERS: dict[str, Any] = WORKFLOW[True]


def test_the_monthly_cut_is_attempted_more_than_once() -> None:
    crons = [entry["cron"] for entry in TRIGGERS["schedule"]]
    assert crons == ["47 17 1 * *", "47 17 2 * *", "47 17 3 * *"], (
        "the cut fires on day 1 and retries on days 2 and 3; one fire a month is "
        "one attempt a year at each month"
    )
    # Same time of day on every fire: the retries consume the same day's Daily
    # scorecard artifact, which is only published after the 13:23 UTC window.
    assert len({cron.split()[0:2] and " ".join(cron.split()[0:2]) for cron in crons}) == 1


def test_the_retries_are_free_when_the_month_is_already_cut() -> None:
    release = WORKFLOW["jobs"]["release"]
    assert release.get("needs") == "decide"
    assert release.get("if") == "${{ needs.decide.outputs.cut == 'true' }}", (
        "a retry fire must skip the release job outright, not start it and short-circuit inside it"
    )
    assert WORKFLOW["jobs"]["decide"]["outputs"]["cut"] == "${{ steps.decide.outputs.cut }}"


def _decide_block() -> str:
    """The `decide` job exactly as the runner reads it, not a YAML round-trip."""
    start = TEXT.index("\n  decide:\n")
    return TEXT[start : TEXT.index("\n  release:\n", start)]


def test_the_guard_reads_a_successful_run_not_the_tag() -> None:
    """The tag is written two thirds of the way through the job.

    A run that tagged and then failed to stage its release draft leaves a tag
    and no release. A guard keyed on the tag reads that as done and never
    retries it, which is the same month-shaped hole one step later.
    """
    decide = _decide_block()
    assert "actions/workflows/dataset-release.yml/runs?status=success" in decide
    assert '.conclusion == "success"' in decide
    assert 'startswith($month + "-")' in decide
    assert "ls-remote" not in decide and "refs/tags" not in decide


def test_an_unreadable_run_history_is_not_a_pass() -> None:
    decide = _decide_block()
    assert "Could not read this workflow's run history" in decide
    assert "|| echo '[]'" not in decide and "|| true" not in decide, (
        "turning 'I could not ask' into an empty answer makes this guard decide "
        "the month's fate from an API error"
    )


def test_the_scheduled_cut_still_refuses_a_day_it_was_not_scheduled_for() -> None:
    release = TEXT[TEXT.index("\n  release:\n") :]
    assert "????-??-0[123]" in release
    assert "day 1, 2 or 3 UTC" in release
    # The retry window and the day check are two copies of the same fact.
    days = sorted(entry["cron"].split()[2] for entry in TRIGGERS["schedule"])
    assert days == ["1", "2", "3"], (
        "the cron days and the day check must move together; a fire the source "
        "resolution refuses is a guaranteed red run"
    )


def test_the_decide_job_cannot_write_anything() -> None:
    assert WORKFLOW["jobs"]["decide"]["permissions"] == {"actions": "read"}, (
        "the deciding job reads run history and nothing else"
    )
    assert re.search(r"^  decide:\n(?:.*\n)*?    timeout-minutes: \d+$", TEXT, re.MULTILINE), (
        "an unbounded guard job can hold the release behind it for six hours"
    )


def test_the_write_scope_belongs_to_the_job_that_tags() -> None:
    """A second job is a second holder of whatever the file grants.

    `contents: write` here is the token that can create a release tag. Left at
    the workflow level it would be handed to the guard job too, which only ever
    reads run history (zizmor `excessive-permissions`, high).
    """
    assert WORKFLOW["permissions"] == {"contents": "read"}
    assert WORKFLOW["jobs"]["release"]["permissions"] == {
        "contents": "write",
        "actions": "read",
    }


# ---------------------------------------------------------------------------
# Retrying after the tag exists (2026-10-07).
#
# The signed tag is written two thirds of the way through the release job.
# Runs 37547342002 and 37559300763 both wrote dataset-2026-10 and died one step
# later, in "Stage and verify the release draft", and main kept moving (the
# `chore(rt)` observation commits land several times a day). Every retry then
# failed "Verify the trusted hosted dataset tag", whose commit must equal the
# source, and the release-tags-immutable ruleset stops anyone deleting the
# stale tag. The source step now adopts a tag that already exists for the
# month, after verifying it the same way the later step does. The tests below
# run that step's real script against a bare origin and an ephemeral signer.
# ---------------------------------------------------------------------------


def _executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} is not installed")
    return path


def _step_script(name: str) -> str:
    for step in WORKFLOW["jobs"]["release"]["steps"]:
        if step.get("name") == name:
            return str(step["run"])
    raise AssertionError(f"no step named {name!r}")


def _source_block() -> str:
    """The source step's script exactly as the runner executes it."""
    return _step_script("Resolve the release source")


def test_every_run_block_is_valid_bash() -> None:
    for job in ("decide", "release"):
        for step in WORKFLOW["jobs"][job]["steps"]:
            if "run" not in step:
                continue
            check = subprocess.run(  # noqa: S603 - bash over the workflow's own script text
                [_executable("bash"), "-n"],
                input=str(step["run"]),
                capture_output=True,
                text=True,
                check=False,
            )
            assert check.returncode == 0, f"{job}/{step.get('name')}: {check.stderr}"


def test_an_existing_tag_is_verified_then_adopted_and_never_written_here() -> None:
    source = _source_block()
    assert "git tag -s" not in source and "git push" not in source, (
        "the source step reads an existing tag; writing one stays after the bundle is proven"
    )
    signers = source.index('"$GITHUB_WORKSPACE/.github/dataset-signers"')
    verify = source.index('git verify-tag -- "$release_tag"')
    ancestor = source.index('git merge-base --is-ancestor "$tag_commit" "$origin_main"')
    mode = source.index('if [ "$tag_mode" != "$expected_mode" ]')
    adopt = source.index('head_sha="$tag_commit"')
    assert signers < verify < ancestor < mode < adopt, (
        "signature, ancestry and mode are established before the tag's commit becomes the source"
    )
    assert 'if [ "$(git cat-file -t "refs/tags/${release_tag}")" != tag ]' in source
    assert "SOURCE_TAG_ADOPTED=$tag_exists" in source


def test_only_a_new_manual_tag_must_pin_current_origin_main() -> None:
    manual = _source_block()
    manual = manual[manual.index("source_mode=manual-latest") :]
    adopt = manual.index('head_sha="$tag_commit"')
    fresh = manual.index('head_sha="$GITHUB_SHA"')
    equality = manual.index('if [ "$head_sha" != "$origin_main" ]')
    assert manual.index('if [ "$tag_exists" = true ]') < adopt < fresh < equality, (
        "the origin/main equality check belongs to the branch that will create a tag"
    )


def _hermetic_git_env(tmp_path: Path) -> dict[str, str]:
    """git with no user, system or signing configuration from this machine."""
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = test\n\temail = test@example.invalid\n"
        "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n"
        "[init]\n\tdefaultBranch = main\n",
        encoding="utf-8",
    )
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "LANG": "C",
    }


def _git(env: dict[str, str], cwd: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603 - git over test-owned repositories
        [_executable("git"), *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _ssh_key(env: dict[str, str], tmp_path: Path, name: str) -> tuple[Path, str]:
    ssh_keygen = _executable("ssh-keygen")
    key = tmp_path / name
    subprocess.run(  # noqa: S603 - resolved ssh-keygen over test-owned paths
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)],
        env=env,
        check=True,
    )
    public = (tmp_path / f"{name}.pub").read_text(encoding="utf-8").split(" ")
    return key, f"{public[0]} {public[1]}"


class _Scenario:
    """A bare origin whose main is at B, with commit A behind it (and the
    signer file in both), plus a fresh workspace clone of main."""

    def __init__(self, tmp_path: Path) -> None:
        self.env = _hermetic_git_env(tmp_path)
        self.trusted_key, trusted_public = _ssh_key(self.env, tmp_path, "trusted")
        self.other_key, _ = _ssh_key(self.env, tmp_path, "other")
        self.origin = tmp_path / "origin.git"
        _git(self.env, tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.work = tmp_path / "work"
        _git(self.env, tmp_path, "clone", "-q", str(self.origin), str(self.work))
        signers = self.work / ".github" / "dataset-signers"
        signers.parent.mkdir()
        signers.write_text(f'trusted namespaces="git" {trusted_public}\n', encoding="utf-8")
        _git(self.env, self.work, "add", ".github/dataset-signers")
        _git(self.env, self.work, "commit", "-q", "-m", "A")
        self.commit_a = _git(self.env, self.work, "rev-parse", "HEAD")
        (self.work / "later").write_text("B\n", encoding="utf-8")
        _git(self.env, self.work, "add", "later")
        _git(self.env, self.work, "commit", "-q", "-m", "B")
        self.commit_b = _git(self.env, self.work, "rev-parse", "HEAD")
        _git(self.env, self.work, "push", "-q", "origin", "main")
        self.tag = f"dataset-{datetime.now(UTC):%Y-%m}"
        self.tmp_path = tmp_path

    def tag_at(
        self,
        commit: str,
        *,
        key: Path | None = None,
        mode: str = "manual-latest",
        run_id: int = 0,
        attempt: int = 0,
        annotated: bool = True,
    ) -> None:
        if annotated:
            _git(
                self.env,
                self.work,
                "-c",
                "gpg.format=ssh",
                "-c",
                f"user.signingkey={key or self.trusted_key}",
                "tag",
                "-s",
                self.tag,
                commit,
                "-m",
                self.tag,
                "-m",
                f"Source {mode}; run {run_id}, attempt {attempt}.",
            )
        else:
            _git(self.env, self.work, "tag", self.tag, commit)
        _git(self.env, self.work, "push", "-q", "origin", f"refs/tags/{self.tag}")

    def side_commit(self) -> str:
        """A commit pushed to origin on a branch that main does not contain."""
        _git(self.env, self.work, "checkout", "-q", "-b", "side", self.commit_a)
        (self.work / "side").write_text("side\n", encoding="utf-8")
        _git(self.env, self.work, "add", "side")
        _git(self.env, self.work, "commit", "-q", "-m", "side")
        sha = _git(self.env, self.work, "rev-parse", "HEAD")
        _git(self.env, self.work, "push", "-q", "origin", "side")
        _git(self.env, self.work, "checkout", "-q", "main")
        return sha

    def resolve(
        self, *, event: str = "workflow_dispatch", github_sha: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, str], str]:
        """Run the real "Resolve the release source" script in a fresh clone."""
        workspace = self.tmp_path / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        _git(self.env, self.tmp_path, "clone", "-q", str(self.origin), str(workspace))
        runner_temp = self.tmp_path / "runner-temp"
        runner_temp.mkdir(exist_ok=True)
        files = {
            name: self.tmp_path / f"{name.lower()}.txt"
            for name in ("GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY")
        }
        for path in files.values():
            path.write_text("", encoding="utf-8")
        script = self.tmp_path / "resolve.sh"
        script.write_text(_step_script("Resolve the release source"), encoding="utf-8")
        env = {
            **self.env,
            **{name: str(path) for name, path in files.items()},
            "EVENT_NAME": event,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": github_sha or self.commit_b,
            "GITHUB_WORKSPACE": str(workspace),
            "GITHUB_REPOSITORY": "example/repo",
            "RUNNER_TEMP": str(runner_temp),
            "GH_TOKEN": "unused",
        }
        done = subprocess.run(  # noqa: S603 - bash over the workflow's own script text
            [_executable("bash"), "-e", str(script)],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        exported = dict(
            line.split("=", 1)
            for line in files["GITHUB_ENV"].read_text(encoding="utf-8").splitlines()
        )
        return done, exported, files["GITHUB_STEP_SUMMARY"].read_text(encoding="utf-8")


def test_a_fresh_manual_cut_still_requires_current_origin_main(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)

    done, exported, _ = scenario.resolve(github_sha=scenario.commit_b)
    assert done.returncode == 0, done.stderr
    assert exported["SOURCE_HEAD_SHA"] == scenario.commit_b
    assert exported["SOURCE_TAG_ADOPTED"] == "false"
    assert exported["SOURCE_MODE"] == "manual-latest"

    stale, _, _ = scenario.resolve(github_sha=scenario.commit_a)
    assert stale.returncode != 0
    assert "require the current origin/main commit" in stale.stdout + stale.stderr


def test_a_trusted_tag_on_main_is_adopted_as_the_source(tmp_path: Path) -> None:
    """The October state: dataset-2026-10 signed at 9ef07b53, main since moved on."""
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.commit_a)

    done, exported, summary = scenario.resolve(github_sha=scenario.commit_b)

    assert done.returncode == 0, done.stderr
    assert exported["SOURCE_HEAD_SHA"] == scenario.commit_a
    assert exported["SOURCE_TAG_ADOPTED"] == "true"
    assert exported["SOURCE_MODE"] == "manual-latest"
    assert exported["SOURCE_RUN_ID"] == "0"
    assert exported["SOURCE_RUN_ATTEMPT"] == "0"
    assert exported["SOURCE_MONTH"] == scenario.tag.removeprefix("dataset-")
    assert f"Adopted the existing {scenario.tag} at {scenario.commit_a}" in summary


def test_a_tag_signed_by_an_untrusted_key_is_refused(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.commit_a, key=scenario.other_key)

    done, exported, _ = scenario.resolve()

    assert done.returncode != 0
    assert "not signed by the trusted dataset signer" in done.stdout + done.stderr
    assert "SOURCE_HEAD_SHA" not in exported


def test_a_tag_whose_commit_is_not_on_main_is_refused(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.side_commit())

    done, exported, _ = scenario.resolve()

    assert done.returncode != 0
    assert "not reachable from origin/main" in done.stdout + done.stderr
    assert "SOURCE_HEAD_SHA" not in exported


def test_a_tag_cut_as_the_other_source_mode_is_refused(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.commit_a, mode="manual-latest")

    done, exported, _ = scenario.resolve(event="schedule")

    assert done.returncode != 0
    assert "this scheduled-daily run cannot adopt it" in done.stdout + done.stderr
    assert "SOURCE_HEAD_SHA" not in exported


def test_a_manual_tag_that_names_a_run_is_refused(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.commit_a, run_id=7, attempt=1)

    done, exported, _ = scenario.resolve()

    assert done.returncode != 0
    assert "a manual-latest tag names run 0" in done.stdout + done.stderr
    assert "SOURCE_HEAD_SHA" not in exported


def test_a_lightweight_tag_is_refused(tmp_path: Path) -> None:
    scenario = _Scenario(tmp_path)
    scenario.tag_at(scenario.commit_a, annotated=False)

    done, exported, _ = scenario.resolve()

    assert done.returncode != 0
    assert "not an annotated tag" in done.stdout + done.stderr
    assert "SOURCE_HEAD_SHA" not in exported
