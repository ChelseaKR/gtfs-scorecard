"""Regression guard for JavaScript actions that must run on Node.js 24."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ACTION_REFERENCE = re.compile(
    r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@([^\s#]+)(?:\s+#\s*(\S+))?"
)

# Each SHA and runtime was verified from the upstream release and action.yml.
# Updating one of these actions requires updating this reviewed inventory too.
NODE24_PINS = {
    "actions/checkout": (
        "93cb6efe18208431cddfb8368fd83d5badbf9bfd",
        "v5.0.1",
    ),
    "actions/deploy-pages": (
        "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
        "v5.0.0",
    ),
    "actions/download-artifact": (
        "37930b1c2abaa49bbe596cd826c3c89aef350131",
        "v7.0.0",
    ),
    "actions/github-script": (
        "ed597411d8f924073f98dfc5c65a23a2325f34cd",
        "v8.0.0",
    ),
    "actions/setup-java": (
        "dded0888837ed1f317902acf8a20df0ad188d165",
        "v5.0.0",
    ),
    "actions/upload-artifact": (
        "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
        "v6.0.0",
    ),
    "actions/upload-pages-artifact": (
        "fc324d3547104276b827a68afc52ff2a11cc49c9",
        "v5.0.0",
    ),
    "actions/dependency-review-action": (
        "a1d282b36b6f3519aa1f3fc636f609c47dddb294",
        "v5.0.0",
    ),
    "astral-sh/setup-uv": (
        "eb1897b8dc4b5d5bfe39a428a8f2304605e0983c",
        "v7.0.0",
    ),
    "aws-actions/configure-aws-credentials": (
        "d979d5b3a71173a29b74b5b88418bfda9437d885",
        "v6.1.1",
    ),
    "peter-evans/create-pull-request": (
        "5f6978faf089d4d20b00c7766989d076bb2fc7f1",
        "v8.1.1",
    ),
}

# The wrapper itself runs on Node.js 20. The blocking scan now installs the
# checksum-verified upstream CLI directly, so this action must not return.
RETIRED_ACTION_PINS = {
    "gitleaks/gitleaks-action": (
        "ff98106e4c7b2bc287b24eaf42907196329070c7",
        "v2.3.9",
    ),
}


def _action_files() -> list[Path]:
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    custom_action_dir = REPO_ROOT / ".github" / "actions"
    candidates = [
        *workflow_dir.rglob("*.yml"),
        *workflow_dir.rglob("*.yaml"),
        REPO_ROOT / "action.yml",
        REPO_ROOT / "action.yaml",
        *custom_action_dir.rglob("action.yml"),
        *custom_action_dir.rglob("action.yaml"),
    ]
    return sorted({path for path in candidates if path.is_file()})


def test_node24_action_references_match_reviewed_inventory() -> None:
    seen: set[str] = set()
    mismatches: list[str] = []
    retired: list[str] = []

    for path in _action_files():
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            match = ACTION_REFERENCE.search(line)
            if match is None:
                continue
            action, ref, version = match.groups()
            if action in RETIRED_ACTION_PINS:
                retired.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {action}@{ref}")
                continue
            expected = NODE24_PINS.get(action)
            if expected is None:
                continue
            seen.add(action)
            if (ref, version) != expected:
                mismatches.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: {action}@{ref} # {version}; "
                    f"expected {action}@{expected[0]} # {expected[1]}"
                )

    assert not mismatches, "Node.js 24 action inventory mismatch:\n" + "\n".join(mismatches)
    assert not retired, "Retired Node.js 20 action reference:\n" + "\n".join(retired)
    assert seen == NODE24_PINS.keys(), (
        "Inventory contains actions not referenced by this repository"
    )


def test_inventory_parser_does_not_require_a_sha_to_find_an_action() -> None:
    match = ACTION_REFERENCE.search("uses: actions/checkout@v5")

    assert match is not None
    assert match.groups() == ("actions/checkout", "v5", None)
