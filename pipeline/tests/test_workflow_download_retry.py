"""A download that feeds a CI check must survive a connection reset.

``curl --retry N`` retries only what curl calls transient: a timeout, an FTP
4xx, or HTTP 408, 429, 500, 502, 503 or 504. A TLS connection reset (curl exit
35) is none of those, so the step fails on its first attempt. That is how
``Secret scan (gitleaks)``, a required check on ``main``, went red on PR #395
on 2026-09-11 before scanning anything: the step died fetching the gitleaks
release with ``curl: (35) Recv failure: Connection reset by peer``.
``--retry-all-errors`` makes every error retryable, which is what "retry 3" was
written to mean.

The scan reads commands, not prose. Comment lines are dropped first, because a
comment that mentions ``--retry-all-errors`` would otherwise satisfy the check
for a command that lacks it, and a command continued with a trailing backslash
is joined back into one line before it is read.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_CURL = re.compile(r"(?<![\w-])curl(?![\w-])")


def _commands(text: str) -> list[str]:
    """Logical shell lines: comments dropped, backslash continuations joined."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    joined: list[str] = []
    pending = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        joined.append(pending + stripped)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def _retrying_curls(text: str) -> list[str]:
    return [cmd for cmd in _commands(text) if _CURL.search(cmd) and "--retry " in cmd]


def _missing_retry_all_errors(text: str) -> list[str]:
    return [cmd.strip() for cmd in _retrying_curls(text) if "--retry-all-errors" not in cmd]


def test_every_retrying_curl_in_a_workflow_also_retries_a_connection_reset() -> None:
    examined: dict[str, int] = {}
    missing: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text()
        examined[workflow.name] = len(_retrying_curls(text))
        missing.extend(f"{workflow.name}: {cmd}" for cmd in _missing_retry_all_errors(text))
    # Floor: the two downloads that feed required checks must be in the
    # universe, or a scanner that stopped matching would report agreement.
    assert examined.get("security.yml", 0) >= 1, examined
    assert examined.get("container-scan.yml", 0) >= 1, examined
    assert sum(examined.values()) >= 3, examined
    assert not missing, "curl --retry without --retry-all-errors:\n" + "\n".join(missing)


def test_the_scan_flags_a_bare_retry_and_accepts_retry_all_errors() -> None:
    bare = 'run: |\n  curl -fsSL --retry 3 -o out.jar \\\n    "https://example.test/x.jar"\n'
    fixed = bare.replace("--retry 3", "--retry 3 --retry-all-errors")
    flagged = _missing_retry_all_errors(bare)
    assert len(flagged) == 1
    # The continuation line was joined in, so the check read the whole command.
    assert flagged[0].startswith("curl -fsSL --retry 3 -o out.jar")
    assert flagged[0].endswith('"https://example.test/x.jar"')
    assert _missing_retry_all_errors(fixed) == []


def test_a_comment_cannot_satisfy_the_check() -> None:
    text = "# always pass --retry-all-errors here\ncurl --retry 3 https://example.test/x\n"
    assert len(_missing_retry_all_errors(text)) == 1


def test_a_curl_without_retry_is_outside_the_rule() -> None:
    assert _retrying_curls("curl -fsSL https://example.test/x -o x\n") == []
    assert _retrying_curls("echo curl-like --retry 3\n") == []
