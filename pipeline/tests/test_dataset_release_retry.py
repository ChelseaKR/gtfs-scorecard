"""A monthly job gets one attempt a year at each month, and 2026-09 spent it.

Run 33553673342 (2026-09-01) failed in "Assemble the release bundle" —
`expected-latest-ids` and `actual-latest-ids` differed at line 294, the
index/latest straddle `pages.yml` now re-reads through — and `dataset-2026-09`
does not exist. Nothing retried it and nothing noticed: this workflow is not
read by any page and has no cadence to go stale against, so a failed cut is
invisible until somebody opens the Actions tab a month later.

Day 1 is now followed by two retry fires, and a `decide` job keeps a healthy
month at exactly one run. These tests hold the parts of that which are easy to
lose: the retries themselves, the guard that makes them free, and the two ways
the guard could quietly stop guarding — reading the tag instead of the run, and
turning an unanswerable question into a pass.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
