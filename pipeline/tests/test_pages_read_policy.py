"""The Pages deploy role can read every S3 key the deploy asks for.

PR #522 added ``rescored-history.json`` to the deploy's artifact sync without
adding it to the read-only role's policy, so every deploy from 2026-10-13 failed
with AccessDenied and the live data went stale. Terraform's policy lists the
readable keys explicitly (infra/artifacts/github_oidc.tf,
``pages_read_s3``). This test reads both files and fails when a key the
workflow syncs or copies is not covered by a resource pattern, so the next new
artifact fails here instead of in production.

IAM patterns are matched the way IAM matches them: ``*`` is any run of
characters (including ``/``) and ``?`` is exactly one character.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
TERRAFORM = ROOT / "infra" / "artifacts" / "github_oidc.tf"
BUCKET_ARN = "${aws_s3_bucket.artifacts.arn}"
POLICY_BLOCK = 'data "aws_iam_policy_document" "pages_read_s3"'
# Days the workflow's shell variables stand for. The policy matches any date.
SAMPLE_DAY = "2026-10-15"
SAMPLE_SEGMENT = "sample-agency"
RESCORED = "data/artifacts/rescored-history.json"


def iam_match(pattern: str, value: str) -> bool:
    """IAM string wildcard matching: ``*`` is any characters, ``?`` is one."""
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(regex, value) is not None


def _policy_text(terraform: str | None = None) -> str:
    text = TERRAFORM.read_text() if terraform is None else terraform
    block = text.split(POLICY_BLOCK, 1)[1]
    return block.split("\nresource ", 1)[0]


def get_object_patterns(policy: str) -> list[str]:
    """The ``s3:GetObject`` resource patterns, with the bucket ARN removed."""
    statement = re.search(
        r'actions\s*=\s*\["s3:GetObject"\]\s*resources\s*=\s*\[(.*?)\]', policy, re.S
    )
    assert statement is not None, "pages_read_s3 has no s3:GetObject statement"
    arns = re.findall(r'"([^"]+)"', statement.group(1))
    assert arns, "pages_read_s3 s3:GetObject lists no resources"
    patterns = []
    for arn in arns:
        assert arn.startswith(BUCKET_ARN + "/"), f"unexpected resource {arn!r}"
        patterns.append(arn.removeprefix(BUCKET_ARN + "/"))
    return patterns


def list_prefixes(policy: str) -> list[str]:
    """The ``s3:prefix`` values the ListBucket statement allows."""
    statement = re.search(r"values\s*=\s*\[(.*?)\]", policy, re.S)
    assert statement is not None, "pages_read_s3 ListBucket has no s3:prefix values"
    return re.findall(r'"([^"]+)"', statement.group(1))


def _shell_commands(workflow: str) -> list[str]:
    """Each ``aws s3 sync|cp`` command, with line continuations joined."""
    joined = re.sub(r"\\\n\s*", " ", workflow)
    # An Actions expression such as ${{ vars.ARTIFACTS_BUCKET }} holds spaces.
    joined = re.sub(r"\$\{\{.*?\}\}", "BUCKET", joined)
    return [
        line.strip()
        for line in joined.splitlines()
        if not line.lstrip().startswith("#") and re.search(r"\baws s3 (sync|cp)\b", line)
    ]


def _unquote(value: str) -> str:
    return value.strip().strip("\"'")


def _normalize(text: str) -> str:
    text = re.sub(r"\$\{today\}|\$today\b", SAMPLE_DAY, text)
    return re.sub(r"\$\{yesterday\}|\$yesterday\b", SAMPLE_DAY, text)


def requested_reads(workflow: str) -> list[tuple[str | None, str]]:
    """``(prefix listed or None, key pattern read)`` for each S3 read in the workflow.

    ``aws s3 sync s3://B/prefix dest --exclude "*" --include P`` reads
    ``prefix/P``; with no ``--exclude "*"`` it reads everything under the
    prefix. ``aws s3 cp s3://B/key dest`` reads ``key``.
    """
    reads: list[tuple[str | None, str]] = []
    for command in _shell_commands(workflow):
        words = _normalize(command).split()
        uris = [w for w in map(_unquote, words) if w.startswith("s3://")]
        if not uris:
            continue
        key = re.sub(r"^s3://[^/]+/?", "", uris[0])
        if "aws s3 cp" in command:
            # A single-object copy is a GetObject, not a ListBucket.
            reads.append((None, key))
            continue
        includes = [_unquote(words[i + 1]) for i, w in enumerate(words[:-1]) if w == "--include"]
        excludes_all = any(
            words[i] == "--exclude" and _unquote(words[i + 1]) == "*" for i in range(len(words) - 1)
        )
        patterns = includes if excludes_all else ["*"]
        reads.extend((key, f"{key.rstrip('/')}/{pattern}") for pattern in patterns)
    return reads


def sample_keys(pattern: str) -> list[str]:
    """Concrete keys a read pattern can name: ``*`` as one segment and as a path."""
    return sorted({pattern.replace("*", SAMPLE_SEGMENT), pattern.replace("*", "a/b")})


def uncovered(workflow: str, policy: str) -> list[str]:
    """Keys the workflow reads that no GetObject resource pattern covers."""
    patterns = get_object_patterns(policy)
    missing = []
    for _prefix, read in requested_reads(workflow):
        for key in sample_keys(read):
            if not any(iam_match(p, key) for p in patterns):
                missing.append(read)
                break
    return sorted(set(missing))


def uncovered_prefixes(workflow: str, policy: str) -> list[str]:
    allowed = list_prefixes(policy)
    missing = []
    for prefix, _read in requested_reads(workflow):
        if prefix is None:
            continue
        listed = prefix.rstrip("/") + "/"
        if not any(iam_match(p, listed) or p == prefix.rstrip("/") for p in allowed):
            missing.append(prefix)
    return sorted(set(missing))


def test_iam_wildcards_match_the_way_iam_does() -> None:
    assert iam_match("a/*/latest.json", "a/x/latest.json")
    assert iam_match("a/*/latest.json", "a/x/y/latest.json")  # * crosses "/"
    assert not iam_match("a/*/latest.json", "a/latest.json")
    assert iam_match("a/*/????-??-??.json", "a/x/2026-10-15.json")
    assert not iam_match("a/*/????-??-??.json", "a/x/2026-1-15.json")  # ? is one char
    assert not iam_match("a/b.json", "a/bxjson")  # "." is literal
    assert iam_match("a/b+c.json", "a/b+c.json")


def test_the_workflow_reads_are_parsed_as_expected() -> None:
    reads = dict(requested_reads(WORKFLOW.read_text()))
    keys = set(reads.values()) | {key for _p, key in requested_reads(WORKFLOW.read_text())}
    assert RESCORED in keys
    assert "data/artifacts/*/latest.json" in keys
    assert f"data/artifacts/*/{SAMPLE_DAY}.json" in keys
    assert "data/artifacts/*/geometry.geojson" in keys
    assert "data/liveness.json" in keys
    assert "cache/fixlog/*" in keys


def test_every_key_the_pages_deploy_reads_is_covered_by_the_role_policy() -> None:
    missing = uncovered(WORKFLOW.read_text(), _policy_text())
    assert missing == [], (
        "pages.yml reads S3 keys the read-only deploy role cannot GetObject; add them "
        f"to pages_read_s3 in infra/artifacts/github_oidc.tf: {missing}"
    )


def test_every_prefix_the_pages_deploy_lists_is_allowed_to_the_role() -> None:
    assert uncovered_prefixes(WORKFLOW.read_text(), _policy_text()) == []


def test_negative_control_removing_rescored_history_from_the_policy_fails_the_guard() -> None:
    """The October 13 outage, replayed: the guard must name the missing key."""
    terraform = TERRAFORM.read_text()
    needle = f'      "{BUCKET_ARN}/{RESCORED}",\n'
    assert needle in terraform  # the fix is present
    assert uncovered(WORKFLOW.read_text(), _policy_text(terraform)) == []

    sabotaged = terraform.replace(needle, "")
    assert sabotaged != terraform  # the sabotage landed
    assert RESCORED not in get_object_patterns(_policy_text(sabotaged))
    assert uncovered(WORKFLOW.read_text(), _policy_text(sabotaged)) == [RESCORED]


def test_negative_control_a_new_synced_file_the_policy_lacks_is_caught() -> None:
    workflow = WORKFLOW.read_text()
    added = workflow.replace(
        '--include "scoring.json"', '--include "scoring.json" --include "brand-new.json"', 1
    )
    assert added != workflow  # the sabotage landed
    assert uncovered(added, _policy_text()) == ["data/artifacts/brand-new.json"]


def test_negative_control_a_prefix_the_role_may_not_list_is_caught() -> None:
    workflow = WORKFLOW.read_text()
    added = workflow.replace(
        's3://${ARTIFACTS_BUCKET}/data/artifacts" data/artifacts',
        's3://${ARTIFACTS_BUCKET}/data/private" data/artifacts',
        1,
    )
    assert added != workflow  # the sabotage landed
    assert uncovered_prefixes(workflow, _policy_text()) == []
    assert uncovered_prefixes(added, _policy_text()) == ["data/private"]
