"""A commit on `main` must not lose its CI verdict to a concurrency group.

Ten workflows were keyed `<name>-${{ github.ref }}` with `cancel-in-progress: true`.
On a pull request `github.ref` is `refs/pull/N/merge`, so that cancels superseded runs
of the same pull request -- the intent, and the saving. On a push it is
`refs/heads/main` for every commit, so two pushes to main shared one group and the
second cancelled the first outright.

Setting `cancel-in-progress: false` does not fix it and is the trap worth naming: a
second run then queues, and a third **evicts the queued one from the pending slot**.
Either way a commit reaches main whose only check-run is `cancelled`.

That matters more than a missing green tick, because a cancelled run is *no signal*.
It is not a pass and not a failure, `gh run list` renders it beside real conclusions,
and the drain brief for this portfolio has to warn in writing that "`cancelled` = NO
SIGNAL, not a failure. Never reconstruct history from cancelled runs." Two commits on
this repository lost their verdict this way on 2026-09-06.

The fix these tests pin: on a push, group by `github.sha`, so one commit gets one
group and cancels nothing.

The rule is deliberately narrow. It applies only to a workflow that a `push` can
trigger, and it says nothing about a fixed-name group like `artifacts-publish` or
`pages`, where serialising is the whole point and a queue is the intended behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"

#: YAML 1.1 parses a bare `on:` key as the boolean True, not the string "on", so a
#: workflow's trigger block is not reachable by the name it is written under.
_ON: Any = True


def _workflows() -> list[Path]:
    paths = sorted(WORKFLOWS.glob("*.yml"))
    assert paths, "no workflows were read; this guard is not running"
    return paths


def _load(path: Path) -> dict[Any, Any]:
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict), f"{path.name} is not a mapping"
    return doc


def _triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    on = doc.get(_ON, doc.get("on"))
    if isinstance(on, dict):
        return on
    if isinstance(on, list):
        return dict.fromkeys(on)
    return {str(on): None} if on else {}


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_a_push_triggered_workflow_never_cancels_a_run_on_a_shared_ref(path: Path) -> None:
    doc = _load(path)
    concurrency = doc.get("concurrency")
    if not isinstance(concurrency, dict):
        return
    if "push" not in _triggers(doc):
        return

    group = str(concurrency.get("group", ""))
    cancel = concurrency.get("cancel-in-progress", False)

    # An unconditional `true` cancels the previous commit's run on every push to main.
    assert cancel is not True, (
        f"{path.name}: cancel-in-progress is unconditionally true on a workflow a push "
        f"can trigger. Two commits on main share one `github.ref`, so the second "
        f"cancels the first and that commit gets no verdict. Make it conditional on "
        f"the event: cancel-in-progress: ${{{{ github.event_name == 'pull_request' }}}}"
    )

    # A group keyed only on the ref puts every commit on main in one group, which is
    # the eviction case even when nothing is cancelled outright.
    if "github.ref" in group and "github.sha" not in group:
        pytest.fail(
            f"{path.name}: the concurrency group is keyed on github.ref alone "
            f"({group!r}). Every push to main lands in one group, so a queued run is "
            f"evicted from the pending slot by the next push. Key a push by its own "
            f"sha: ${{{{ github.event_name == 'pull_request' && github.ref || github.sha }}}}"
        )


def test_the_ten_workflows_that_carried_the_defect_are_all_fixed() -> None:
    """A named inventory, so a fix cannot be lost to a later copy-paste.

    Listed rather than derived: the parametrised guard above would pass just as
    happily if one of these workflows lost its `push` trigger or its `concurrency`
    block, and that is not the same repository.
    """
    expected = {
        "a11y.yml",
        "ci.yml",
        "codeql.yml",
        "container-scan.yml",
        "e2e.yml",
        "iac.yml",
        "links.yml",
        "openssf-scorecard.yml",
        "security.yml",
        "standards-pin.yml",
    }
    for name in sorted(expected):
        path = WORKFLOWS / name
        assert path.is_file(), f"{name} is gone; this inventory needs updating deliberately"
        concurrency = _load(path).get("concurrency")
        assert isinstance(concurrency, dict), f"{name} lost its concurrency block"
        assert "github.sha" in str(concurrency["group"]), (
            f"{name}: a push must be grouped by its own sha, or the commit before it "
            f"loses its verdict"
        )
        assert "github.event_name" in str(concurrency["cancel-in-progress"]), (
            f"{name}: cancellation must be conditional on the event, not unconditional"
        )


def test_codeql_is_covered_even_though_only_pull_requests_trigger_it() -> None:
    """The one in the inventory the parametrised guard skips, and why it is still fixed.

    `codeql.yml` runs on `pull_request` and `schedule` only -- the `push: main`
    trigger was removed deliberately (CICD §11e). So the guard above returns early for
    it, and it would have kept the defective key silently if the trigger ever came
    back. Two scheduled runs also share `refs/heads/main`, and cancelling the older of
    those loses a code-scanning baseline refresh rather than a merge verdict.
    """
    doc = _load(WORKFLOWS / "codeql.yml")
    assert "push" not in _triggers(doc), "codeql regained a push trigger; re-read CICD §11e"
    assert "github.sha" in str(doc["concurrency"]["group"])
