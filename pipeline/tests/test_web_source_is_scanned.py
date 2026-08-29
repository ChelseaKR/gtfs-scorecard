"""web/src/ is hand-written source and stays in scope for the scanners.

Roughly 6,600 lines of browser JavaScript, including 24 innerHTML assignment
sites in app.js, were excluded from Semgrep (.semgrepignore) and gitleaks
(.gitleaks.toml) and never analysed by CodeQL, which is configured for python
and actions only. Each exclusion was individually defensible -- both were
written for the public GTFS feed-URL keys that appear in generated data under
web/ -- and together they meant the only hand-written code that runs in a
member of the public's browser had no SAST and no secret scanning at all.

The .semgrepignore comment asserted the opposite in the same file, four lines
above the rule: "Hand-written source stays in scope." Nothing checked.

This is that check. It holds the boundary, not the tools: an exclusion may name
a generated tree under web/, and may not swallow web/src/ with it.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMGREPIGNORE = REPO_ROOT / ".semgrepignore"
GITLEAKS = REPO_ROOT / ".gitleaks.toml"
SECURITY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security.yml"

# The hand-written browser sources. Not a sample: every non-generated file
# under web/src/ that either ships to a browser or styles what does.
HAND_WRITTEN = ("web/src/app.js", "web/src/styles.css")


def _semgrep_patterns() -> list[str]:
    lines = []
    for raw in SEMGREPIGNORE.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith(("#", ":")):
            lines.append(line)
    return lines


def _semgrep_ignores(path: str) -> bool:
    """Whether a .semgrepignore pattern list excludes ``path``.

    gitignore semantics, restricted to the shapes this file actually uses:
    a trailing-slash directory prefix, or a glob. `!` negation is deliberately
    treated as non-excluding here and is separately asserted to be unused,
    because semgrep does not honour it -- verified by adding `!web/src/` under
    `web/` and watching semgrep scan zero files.
    """
    for pattern in _semgrep_patterns():
        if pattern.startswith("!"):
            continue
        if pattern.endswith("/") and path.startswith(pattern):
            return True
        if pattern == path:
            return True
        if "*" in pattern:
            regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
            if re.fullmatch(regex, path):
                return True
    return False


def _gitleaks_allowlisted(path: str) -> bool:
    config = tomllib.loads(GITLEAKS.read_text())
    return any(re.search(pattern, path) for pattern in config["allowlist"]["paths"])


@pytest.mark.parametrize("path", HAND_WRITTEN)
def test_semgrep_scans_the_hand_written_browser_source(path: str) -> None:
    assert not _semgrep_ignores(path), (
        f"{path} is hand-written source and .semgrepignore excludes it. The file's own "
        "comment says hand-written source stays in scope; exclude the generated tree, "
        "not web/src/."
    )


@pytest.mark.parametrize("path", HAND_WRITTEN)
def test_gitleaks_scans_the_hand_written_browser_source(path: str) -> None:
    assert not _gitleaks_allowlisted(path), (
        f"{path} is hand-written source and .gitleaks.toml allowlists it. A credential "
        "committed there would ship to every visitor and never be scanned."
    )


def test_semgrepignore_uses_no_negation_lines() -> None:
    """`!pattern` reads as an un-ignore and is not one.

    Semgrep skips the file regardless, so a `web/` + `!web/src/` pair looks
    like coverage and delivers none.
    """
    negations = [p for p in _semgrep_patterns() if p.startswith("!")]
    assert not negations, (
        "semgrep does not honour gitignore-style negation; name the generated "
        f"trees instead. Found: {negations}"
    )


def test_semgrep_runs_a_javascript_ruleset_now_that_javascript_is_in_scope() -> None:
    """Coverage of a directory means nothing without rules for its language."""
    workflow = SECURITY_WORKFLOW.read_text()
    assert "--config p/javascript" in workflow, (
        "web/src/ is in Semgrep's scope but the scan runs only p/default and "
        "p/python, so the browser code is scanned by almost no rules."
    )


# The waiver's own review clock, written in the file it governs.
_EXPIRES = re.compile(r"exclusion list expires (\d{4}-\d{2}-\d{2})")
_REVIEWED = re.compile(r"Last reviewed: (\d{4}-\d{2}-\d{2})")


def test_the_semgrep_exclusion_waiver_has_not_lapsed() -> None:
    """`.semgrepignore` sets its own review deadline and says "A lapsed date
    here is itself a review finding". Nothing found it. The equivalent clock on
    the container CVE waivers is enforced (test_security_vex.py asserts
    `min(expiries) > today`); this one was prose, so the exclusion list could
    outlive its review indefinitely with every gate green.

    The paths it excludes are the reason to care: a stale exclusion is how
    hand-written source drifts back out of the SAST scan, which is the failure
    the rest of this file exists to prevent.
    """
    text = SEMGREPIGNORE.read_text()
    expires_match = _EXPIRES.search(text)
    reviewed_match = _REVIEWED.search(text)

    assert expires_match, (
        ".semgrepignore no longer states an expiry date. The waiver has to carry "
        "its own review clock, or nothing can tell whether it lapsed."
    )
    assert reviewed_match, ".semgrepignore no longer states a 'Last reviewed:' date."

    expires = dt.date.fromisoformat(expires_match.group(1))
    reviewed = dt.date.fromisoformat(reviewed_match.group(1))
    today = dt.date.today()

    assert expires > today, (
        f"the .semgrepignore exclusion list expired on {expires}. Re-run semgrep over "
        "the excluded paths, drop any entry that no longer flags, and renew both dates "
        "in the file. Do not just move the date."
    )
    assert reviewed <= today, f"'Last reviewed: {reviewed}' is in the future"
    assert expires - reviewed <= dt.timedelta(days=92), (
        f"the file says the list is reviewed quarterly, but {reviewed} to {expires} is "
        f"{(expires - reviewed).days} days"
    )
