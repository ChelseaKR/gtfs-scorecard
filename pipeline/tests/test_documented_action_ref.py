"""The public `uses:` examples must pin a release, never a floating major.

`README.md` and `docs/ci-action.md` are what a consumer copies into their own
workflow. Until 2026-09-06 both recommended
``uses: ChelseaKR/gtfs-scorecard@v1``. That tag is one mutable pointer: it had
not moved since 2026-07-25 while ``main`` gathered 439 commits, so every
workflow copied from these documents was one release away from a jump across
all of them, made with no commit and no diff on the consumer's side. The
release it points at grades an archive holding no schedule data as
``F (31.3/100)`` with ``passed=true`` -- see ``test_unmeasurable_feed.py``.

Nothing here stops the floating tag from existing. The Marketplace convention
needs it, and the consumers who already copied it can receive a fix only by it
moving (``docs/decisions/0033-branch-protection-ruleset.md``). What this gate
stops is the project recommending it again.

It also replaces an assertion that used to live in ``test_action_v2.py``:

    assert set(re.findall(r"ChelseaKR/gtfs-scorecard@(v\\d+)", docs)) == {f"v{major}"}
    assert f"@v{version}" in docs

The first required a floating major in the documented form. The second required
the documented pin to equal ``pipeline/pyproject.toml``'s version, which is
bumped when the changelog section is written rather than when the tag is cut --
so it forced the docs to advertise ``@v1.5.0``, a tag that has never existed.
The replacements below require the opposite of both: a full release tag, and
one that ``CHANGELOG.md`` records as released rather than unreleased.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

# Everything a consumer copies a workflow snippet out of: the front page, the
# top-level `docs/` pages that describe the service as it stands (the same
# "live-facing" set `scripts/check_doc_stats.py` sweeps), and this repository's
# own workflows. Dated records under `docs/decisions/` and `CHANGELOG.md` are
# excluded: they say what was true when they were written, and `@v1` appears in
# both as history rather than as advice.
CONSUMER_FILES = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / ".github/workflows").glob("*.yml")),
]

# The two documents that must always carry a worked example. Without this, the
# gate below could be satisfied by deleting the snippet instead of pinning it.
REQUIRED_EXAMPLES = ("README.md", "docs/ci-action.md")

# `uses: ChelseaKR/gtfs-scorecard@<ref>` on one line. Same-line only: prose that
# happens to end a line with "uses:" and continue on the next is discussion, not
# a copyable step.
USES_RE = re.compile(r"uses:[ \t]*ChelseaKR/gtfs-scorecard@(\S+)")

# A ref a consumer can rely on: a full release tag, or a full commit SHA.
# `v1`, `v1.4`, `main` and a branch name all fail this.
PINNED_RE = re.compile(r"\A(?:v\d+\.\d+\.\d+|[0-9a-f]{40})\Z")

# A released section heading in the changelog: `## [1.4.0] - 2026-07-25`.
# `## [Unreleased]` deliberately does not match.
RELEASED_RE = re.compile(r"(?m)^##\s*\[(\d+\.\d+\.\d+)\]\s*-\s*\d{4}-\d{2}-\d{2}")

# A worked example carrying the defect this gate exists to catch. The tests use
# it as a negative control so a silently non-matching regex reads as a failure
# rather than as a pass.
FLOATING_MAJOR_SAMPLE = """
jobs:
  gtfs-quality:
    steps:
      - uses: ChelseaKR/gtfs-scorecard@v1
        with:
          feed-url: https://example.org/gtfs/feed.zip
"""


def documented_refs(text: str) -> list[str]:
    """Every ref named by a copyable `uses:` step in ``text``."""
    return USES_RE.findall(text)


def unpinned_refs(text: str) -> list[str]:
    """Refs in ``text`` that are not a full release tag or a full commit SHA."""
    return [ref for ref in documented_refs(text) if not PINNED_RE.match(ref)]


def released_versions() -> set[str]:
    """Versions ``CHANGELOG.md`` records as released, not as unreleased."""
    return set(RELEASED_RE.findall((ROOT / "CHANGELOG.md").read_text()))


def test_the_detector_rejects_a_floating_major() -> None:
    """Negative control: the same code path the gate uses must catch `@v1`."""
    assert documented_refs(FLOATING_MAJOR_SAMPLE) == ["v1"]
    assert unpinned_refs(FLOATING_MAJOR_SAMPLE) == ["v1"]
    assert unpinned_refs(FLOATING_MAJOR_SAMPLE.replace("@v1\n", "@v1.4.0\n")) == []


def test_no_public_example_names_a_floating_major() -> None:
    offenders = {
        str(path.relative_to(ROOT)): bad
        for path in CONSUMER_FILES
        if (bad := unpinned_refs(path.read_text()))
    }
    assert not offenders, (
        f"Documented `uses:` steps name an unpinned ref: {offenders}. "
        "Name a full release tag (v1.4.0) or a commit SHA. The floating major "
        "moves under every consumer who copied it; see "
        "docs/release-checklist.md#tag-namespaces."
    )


def test_the_worked_examples_still_exist() -> None:
    for name in REQUIRED_EXAMPLES:
        refs = documented_refs((ROOT / name).read_text())
        assert refs, f"{name} carries no `uses: ChelseaKR/gtfs-scorecard@...` example"


def test_every_documented_ref_agrees() -> None:
    refs = {ref for path in CONSUMER_FILES for ref in documented_refs(path.read_text())}
    assert len(refs) == 1, f"Public examples disagree on which ref to use: {sorted(refs)}"


def test_the_documented_pin_has_a_changelog_entry() -> None:
    """A pin must name a version the changelog records as released.

    This is necessary and not sufficient. A changelog section is written when
    `pipeline/pyproject.toml` is bumped, which is before -- sometimes long
    before -- the tag is cut: 1.5.0 has a section dated 2026-08-18 and no tag.
    `test_the_documented_pin_is_a_tag_that_exists` is the sufficient half.
    """
    refs = {ref for path in CONSUMER_FILES for ref in documented_refs(path.read_text())}
    released = released_versions()
    assert released, "CHANGELOG.md has no released version heading to check against"
    for ref in refs:
        if ref.startswith("v"):
            assert ref[1:] in released, (
                f"Public examples pin {ref}, which CHANGELOG.md does not record as "
                f"released. Released: {sorted(released)}"
            )


def _git_tags() -> list[str]:
    git = shutil.which("git")
    if git is None:  # pragma: no cover - git is present in CI and in `make verify`
        return []
    result = subprocess.run(  # noqa: S603 - resolved git binary over this checkout
        [git, "tag", "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:  # pragma: no cover - not a git checkout
        return []
    return result.stdout.split()


def test_the_documented_pin_is_a_tag_that_exists() -> None:
    """The ref a consumer copies must be fetchable.

    Until 2026-09-06 `docs/ci-action.md` told readers to pin `@v1.5.0`, and
    `test_action_v2.py` asserted that it did. No such tag has ever been cut,
    so the recommended pin resolved to nothing at all.
    """
    tags = _git_tags()
    if not tags:
        pytest.skip("no tags in this checkout; see test_ci_fetches_tags_for_that_check")
    refs = {ref for path in CONSUMER_FILES for ref in documented_refs(path.read_text())}
    for ref in refs:
        if PINNED_RE.match(ref) and ref.startswith("v"):
            assert ref in tags, (
                f"Public examples pin {ref}, which is not a tag in this repository. "
                f"Release tags present: {sorted(t for t in tags if t.startswith('v'))}"
            )


def test_ci_fetches_tags_for_that_check() -> None:
    """The guard on the guard.

    The check above can only run where tags are present. A default
    `actions/checkout` fetches none, so without this the check would skip in CI
    forever and nothing would say so.
    """
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    checkout = next(
        step
        for step in workflow["jobs"]["pipeline"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-tags"] is True
