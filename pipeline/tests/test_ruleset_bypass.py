"""Every committed ruleset must leave the repository owner a way in.

`.github/rulesets/tags.json` shipped with `"bypass_actors": []` while
`.github/rulesets/main.json`, in the same directory, carried the repository-admin
bypass. Two files, one convention, and only one of them followed it.

An empty list is not a stricter version of the rule; it is a different rule. It means
**nobody** can move or delete a tag matching `refs/tags/v*.*.*` — the owner included,
with an admin token, from the web UI. If a release tag is ever cut at the wrong commit
the only remedies left are burning the version number or opening a support ticket. That
is not hypothetical here: `v1.4.0` matches the pattern, and it points at a 2026-07-25
commit that `main` has since left hundreds of commits behind.

The counter-argument — "an admin bypass means the rule enforces nothing against the only
account that can push" — is coherent, has been made, and was decided against. The
ruleset's job is to stop an *accidental* force-push or deletion, including by automation
holding the owner's token. It is not there to bind the owner against herself. An empty
bypass list once locked her out of a repository and the recovery ran across eighteen of
them, so this is a standing instruction rather than a preference.

Committing the corrected file does not change GitHub. A ruleset lives in repository
settings and the JSON here is the reviewed source for it, exactly as
`test_required_status_checks.py` says of `main.json`: applying it still needs
`gh api repos/ChelseaKR/gtfs-scorecard/rulesets/{id} -X PUT --input <file>`, and that is
the owner's action.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

RULESETS = Path(__file__).parents[2] / ".github" / "rulesets"

#: The repository-admin role. `bypass_mode: always` applies to pull requests too, not
#: only to direct pushes.
ADMIN_BYPASS = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}


def _rulesets() -> list[Path]:
    paths = sorted(RULESETS.glob("*.json"))
    assert paths, "no rulesets were read; this guard is not running"
    return paths


@pytest.mark.parametrize("path", _rulesets(), ids=lambda p: p.name)
def test_a_ruleset_never_ships_an_empty_bypass_list(path: Path) -> None:
    ruleset: dict[str, Any] = json.loads(path.read_text())
    actors = ruleset.get("bypass_actors")

    assert actors, (
        f"{path.name} has no bypass actors. Applied, that locks every account out of the "
        f"rule, the repository owner included: a mistagged release could not be moved or "
        f"deleted by anyone. Include the repository-admin bypass: {ADMIN_BYPASS}"
    )
    assert ADMIN_BYPASS in actors, (
        f"{path.name} does not grant the repository-admin role an always-bypass. "
        f"{path.name} must leave the owner a way in; see this module's docstring."
    )


def test_both_rulesets_agree_on_the_bypass_convention() -> None:
    """The defect was an inconsistency between two files, so the check is a comparison.

    A per-file assertion alone would pass a future ruleset that invented its own bypass
    shape. What went wrong here was that `tags.json` did not do what `main.json` does.
    """
    bypasses = {p.name: json.loads(p.read_text()).get("bypass_actors") for p in _rulesets()}

    assert set(bypasses) >= {"main.json", "tags.json"}, (
        "a ruleset this guard was written for is gone; update the inventory deliberately"
    )
    assert bypasses["tags.json"] == bypasses["main.json"], (
        "the tag ruleset and the branch ruleset disagree about who may bypass. "
        f"main.json: {bypasses['main.json']}; tags.json: {bypasses['tags.json']}"
    )
