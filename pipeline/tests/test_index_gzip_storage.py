"""The aggregate index is stored gzip-compressed and every reader decodes it.

``data/artifacts/index.json`` carries every agency's full history (151 MB on
2026-10-22) and each refresh, deploy, collect and report run read all of it. The
same bytes gzip to about 5 MB. ``scripts/s3-index.sh`` is the one place the
workflows read and write it, so a reader cannot be left behind.

Nothing here needs AWS. ``aws`` is a stand-in on PATH whose bucket is a
directory; it records every byte it moves, which is what the egress claims are
measured from.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline.activation import decode_index_bytes

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "s3-index.sh"
WORKFLOWS = ROOT / ".github" / "workflows"
KEY = "data/artifacts/index.json"
BUCKET = "artifacts-test"

FAKE_AWS = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    """Just enough of `aws s3 cp` and `aws s3api put-object` for s3-index.sh."""
    import hashlib, json, os, shutil, sys
    from pathlib import Path

    store = Path(os.environ["FAKE_BUCKET_DIR"])
    log = Path(os.environ["FAKE_AWS_LOG"])
    args = sys.argv[1:]

    def etag(path):
        return '"' + hashlib.md5(path.read_bytes()).hexdigest() + '"'

    def record(**entry):
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\\n")

    def flags(rest):
        out, i = {}, 0
        while i < len(rest):
            if rest[i].startswith("--"):
                name = rest[i][2:]
                if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                    out[name] = rest[i + 1]
                    i += 2
                    continue
                out[name] = True
            i += 1
        return out

    def meta_path(obj):
        return obj.with_name(obj.name + ".meta")

    def put(obj, src, opts):
        obj.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, obj)
        meta_path(obj).write_text(json.dumps({
            "content_encoding": opts.get("content-encoding"),
            "content_type": opts.get("content-type"),
            "cache_control": opts.get("cache-control"),
        }))
        record(op="put", key=obj.relative_to(store).as_posix(),
               bytes=Path(src).stat().st_size, **{k.replace("-", "_"): v
               for k, v in opts.items() if k in ("content-encoding", "if-match")})

    if args[:2] == ["s3", "cp"]:
        src, dst, opts = args[2], args[3], flags(args[4:])
        if src.startswith("s3://"):
            key = src.split("/", 3)[3]
            obj = store / key
            if not obj.exists():
                sys.stderr.write("fatal error: An error occurred (404) when calling HeadObject\\n")
                sys.exit(1)
            shutil.copyfile(obj, dst)
            record(op="get", key=key, bytes=obj.stat().st_size)
        else:
            put(store / dst.split("/", 3)[3], src, opts)
    elif args[:2] == ["s3api", "put-object"]:
        opts = flags(args[2:])
        obj = store / opts["key"]
        match = opts.get("if-match")
        if match is not None and (not obj.exists() or etag(obj) != match):
            record(op="put-refused", key=opts["key"], if_match=match)
            sys.stderr.write("An error occurred (PreconditionFailed) when calling PutObject\\n")
            sys.exit(1)
        put(obj, opts["body"], opts)
    else:
        sys.stderr.write("fake aws: unsupported " + " ".join(args) + "\\n")
        sys.exit(2)
    '''
)


def _index_fixture(agencies: int = 400, rows: int = 60) -> bytes:
    """An index shaped like the real one: per-agency history of dated score rows."""
    document: dict[str, Any] = {"schema_version": "1.8", "agencies": {}}
    for number in range(agencies):
        document["agencies"][f"agency-{number:04d}"] = {
            "name": f"Agency {number}",
            "history": [
                {
                    "date": f"2026-{1 + day // 28:02d}-{1 + day % 28:02d}",
                    "score": 50 + (number * 7 + day * 3) % 50,
                    "grade": "ABCD"[(number + day) % 4],
                    "feed_sha256": hashlib.sha256(f"{number}:{day // 15}".encode()).hexdigest(),
                    "categories": {"static": 80 + day % 20, "realtime": 60 + number % 30},
                }
                for day in range(rows)
            ],
        }
    return (json.dumps(document, sort_keys=True, indent=1) + "\n").encode()


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.bucket = tmp_path / "bucket"
        self.bucket.mkdir()
        self.log = tmp_path / "aws.log"
        self.log.write_text("")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        self.bin = bin_dir
        fake = bin_dir / "aws"
        fake.write_text(FAKE_AWS)
        fake.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_BUCKET_DIR": str(self.bucket),
            "FAKE_AWS_LOG": str(self.log),
        }
        self.env.pop("INDEX_GZIP", None)

    def run(self, *args: str, gzip_on: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if gzip_on:
            env["INDEX_GZIP"] = "1"
        return subprocess.run(  # noqa: S603 - a repository-owned script and a stand-in aws
            [str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
        )

    def stored(self) -> bytes:
        return (self.bucket / KEY).read_bytes()

    def meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = json.loads((self.bucket / (KEY + ".meta")).read_text())
        return meta

    def seed(self, data: bytes) -> None:
        (self.bucket / KEY).parent.mkdir(parents=True, exist_ok=True)
        (self.bucket / KEY).write_bytes(data)

    def calls(self, op: str) -> list[dict[str, Any]]:
        lines = [json.loads(line) for line in self.log.read_text().splitlines() if line]
        return [line for line in lines if line["op"] == op]

    def etag(self) -> str:
        return '"' + hashlib.md5(self.stored(), usedforsecurity=False).hexdigest() + '"'


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_script_is_executable_and_names_one_key() -> None:
    assert SCRIPT.stat().st_mode & 0o111
    assert 'KEY="data/artifacts/index.json"' in SCRIPT.read_text()


def test_get_returns_identical_bytes_whether_stored_plain_or_gzip(
    harness: Harness, tmp_path: Path
) -> None:
    plain = _index_fixture()
    outputs: list[bytes] = []
    for stored in (plain, gzip.compress(plain, 6)):
        harness.seed(stored)
        dest = tmp_path / f"out-{len(outputs)}" / "index.json"
        result = harness.run("get", BUCKET, str(dest))
        assert result.returncode == 0, result.stderr
        outputs.append(dest.read_bytes())
    assert outputs[0] == outputs[1] == plain


def test_get_of_gzip_moves_a_fraction_of_the_bytes_and_reports_them(
    harness: Harness, tmp_path: Path
) -> None:
    """Measured on the fixture: bytes read from the bucket, plain versus gzip."""
    plain = _index_fixture()
    harness.seed(plain)
    harness.run("get", BUCKET, str(tmp_path / "a.json"))
    harness.seed(gzip.compress(plain, 6))
    harness.run("get", BUCKET, str(tmp_path / "b.json"))
    before, after = (call["bytes"] for call in harness.calls("get"))

    assert before == len(plain)
    assert after < before / 10
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    print(f"index fixture: {before} bytes plain, {after} bytes gzip ({before / after:.1f}x)")


def test_negative_control_a_reader_that_does_not_decode_is_caught(
    harness: Harness, tmp_path: Path
) -> None:
    """A plain `aws s3 cp` of the gzip object leaves bytes no JSON reader accepts."""
    plain = _index_fixture(agencies=5, rows=5)
    harness.seed(gzip.compress(plain, 6))
    naive = tmp_path / "naive.json"
    subprocess.run(  # noqa: S603 - the stand-in aws
        [str(harness.bin / "aws"), "s3", "cp", f"s3://{BUCKET}/{KEY}", str(naive)],
        env=harness.env,
        check=True,
        capture_output=True,
    )
    assert naive.read_bytes()[:2] == b"\x1f\x8b", "the sabotage did not apply"
    with pytest.raises(ValueError):
        json.loads(naive.read_bytes())
    # The Python reader would have the same problem without decode_index_bytes.
    assert decode_index_bytes(naive.read_bytes()) == plain


@pytest.mark.parametrize(
    "stored", [b"\x1f\x8b\x08\x00not-a-gzip-stream", b"<html>error</html>", b""]
)
def test_get_refuses_a_body_that_is_not_a_json_object_and_keeps_dest(
    harness: Harness, tmp_path: Path, stored: bytes
) -> None:
    harness.seed(stored)
    dest = tmp_path / "index.json"
    dest.write_bytes(b'{"previous": true}')
    result = harness.run("get", BUCKET, str(dest))
    assert result.returncode != 0
    assert dest.read_bytes() == b'{"previous": true}'
    assert not list(tmp_path.glob("index.json.tmp.*"))


def test_get_of_a_missing_index_fails_and_writes_nothing(harness: Harness, tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "index.json"
    assert harness.run("get", BUCKET, str(dest)).returncode != 0
    assert not dest.exists()


def test_put_without_the_switch_uploads_the_file_unchanged(
    harness: Harness, tmp_path: Path
) -> None:
    plain = _index_fixture()
    src = tmp_path / "index.json"
    src.write_bytes(plain)
    assert harness.run("put", BUCKET, str(src)).returncode == 0
    assert harness.stored() == plain
    assert harness.meta()["content_encoding"] is None
    assert harness.meta()["cache_control"] == "max-age=300"


def test_put_with_the_switch_uploads_gzip_that_decodes_to_the_same_bytes(
    harness: Harness, tmp_path: Path
) -> None:
    plain = _index_fixture()
    src = tmp_path / "index.json"
    src.write_bytes(plain)
    assert harness.run("put", BUCKET, str(src), gzip_on=True).returncode == 0
    assert harness.stored()[:2] == b"\x1f\x8b"
    assert gzip.decompress(harness.stored()) == plain
    assert harness.meta()["content_encoding"] == "gzip"
    assert harness.meta()["content_type"] == "application/json"
    assert len(harness.stored()) < len(plain) / 10
    # Same JSON, same bytes: the header carries no name or timestamp.
    first = harness.stored()
    harness.run("put", BUCKET, str(src), gzip_on=True)
    assert harness.stored() == first


def test_round_trip_through_put_then_get_is_byte_identical(
    harness: Harness, tmp_path: Path
) -> None:
    plain = _index_fixture()
    src = tmp_path / "index.json"
    src.write_bytes(plain)
    for switch in (False, True):
        harness.run("put", BUCKET, str(src), gzip_on=switch)
        dest = tmp_path / f"back-{switch}.json"
        assert harness.run("get", BUCKET, str(dest)).returncode == 0
        assert dest.read_bytes() == plain


def test_a_deploy_never_reads_a_stale_index_across_the_format_switch(
    harness: Harness, tmp_path: Path
) -> None:
    """One key: the reader after any write sees that write, in either format."""
    versions = []
    for generation, switch in enumerate([False, True, True, False, True]):
        document = json.loads(_index_fixture(agencies=3, rows=3))
        document["generation"] = generation
        body = (json.dumps(document, sort_keys=True) + "\n").encode()
        versions.append(body)
        src = tmp_path / "src.json"
        src.write_bytes(body)
        assert harness.run("put", BUCKET, str(src), gzip_on=switch).returncode == 0
        dest = tmp_path / f"read-{generation}.json"
        assert harness.run("get", BUCKET, str(dest)).returncode == 0
        assert dest.read_bytes() == body
    # Negative control: a reader that kept an earlier copy would be wrong, and
    # the generations really do differ.
    assert len(set(versions)) == len(versions)
    assert (tmp_path / "read-0.json").read_bytes() != versions[-1]


def test_conditional_put_keeps_the_if_match_guard_in_both_formats(
    harness: Harness, tmp_path: Path
) -> None:
    plain = _index_fixture(agencies=3, rows=3)
    newer = plain.replace(b"Agency 0", b"Agency Z")
    assert newer != plain, "the edit did not apply"
    src = tmp_path / "index.json"
    src.write_bytes(newer)
    for switch in (False, True):
        harness.seed(gzip.compress(plain, 6) if switch else plain)
        stale = '"deadbeef"'
        refused = harness.run("put", BUCKET, str(src), stale, gzip_on=switch)
        assert refused.returncode != 0
        assert decode_index_bytes(harness.stored()) == plain
        accepted = harness.run("put", BUCKET, str(src), harness.etag(), gzip_on=switch)
        assert accepted.returncode == 0, accepted.stderr
        assert decode_index_bytes(harness.stored()) == newer
        assert (harness.stored()[:2] == b"\x1f\x8b") is switch


def test_python_and_shell_decode_agree(harness: Harness, tmp_path: Path) -> None:
    plain = _index_fixture(agencies=10, rows=10)
    for stored in (plain, gzip.compress(plain, 1), gzip.compress(plain, 9)):
        harness.seed(stored)
        dest = tmp_path / "agree.json"
        assert harness.run("get", BUCKET, str(dest)).returncode == 0
        assert dest.read_bytes() == decode_index_bytes(stored) == plain


# --- every reader and writer of the index goes through the script -------------------


def _run_text(step: dict[str, Any]) -> str:
    return str(step.get("run") or "")


def _all_steps() -> list[tuple[str, dict[str, Any]]]:
    found = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(workflow.read_text())
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    found.append((workflow.name, step))
    return found


def _commands(text: str) -> list[str]:
    joined, pending = [], ""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        joined.append(pending + stripped)
        pending = ""
    return joined


# A command that moves the index object by itself, bypassing the script.
_DIRECT_INDEX_IO = re.compile(
    r"aws\s+s3(?:api)?\s+(?:cp|put-object|get-object)\b.*(?:artifacts/index\.json|"
    r"index\.json\")"
)
_SYNC_THAT_PULLS_THE_INDEX = re.compile(r"aws\s+s3\s+sync\b.*--include\s+[\"']index\.json[\"']")


def _violations(commands: list[str]) -> list[str]:
    return [
        command
        for command in commands
        if _DIRECT_INDEX_IO.search(command) or _SYNC_THAT_PULLS_THE_INDEX.search(command)
    ]


def test_no_workflow_step_moves_the_index_without_the_script() -> None:
    offenders = []
    for name, step in _all_steps():
        for command in _violations(_commands(_run_text(step))):
            offenders.append((name, command.strip()))
    assert offenders == []


def test_the_scan_sees_every_reader_and_writer_it_was_written_for() -> None:
    """Coverage floor: a scanner that stopped matching would report agreement."""
    uses: dict[str, list[str]] = {}
    for name, step in _all_steps():
        for command in _commands(_run_text(step)):
            match = re.search(r"s3-index\.sh\s+(get|put)\b", command)
            if match:
                uses.setdefault(name, []).append(match.group(1))
    assert {k: sorted(v) for k, v in uses.items()} == {
        "history-export.yml": ["get"],
        "pages.yml": ["get", "get"],
        "refresh.yml": ["get", "put"],
        "report-bundle.yml": ["get"],
        "scorecard.yml": ["get", "put"],
        "targeted-score.yml": ["put"],
        "trend-history-repair.yml": ["get", "put"],
    }
    # targeted-score reads the index through activation-hydrate, which decodes.
    targeted = (WORKFLOWS / "targeted-score.yml").read_text()
    assert "activation-hydrate" in targeted


def test_negative_control_the_scanner_catches_each_bypass() -> None:
    bypasses = {
        "plain cp read": 'aws s3 cp "s3://b/data/artifacts/index.json" data/artifacts/index.json',
        "plain cp write": 'aws s3 cp data/artifacts/index.json "${artifact_uri}/index.json"',
        "put-object write": "aws s3api put-object --key data/artifacts/index.json --body x",
        "sync include": 'aws s3 sync s3://b/data/artifacts d --exclude "*" --include "index.json"',
    }
    for label, command in bypasses.items():
        assert _violations([command]), f"the scanner missed: {label}"
    assert not _violations(["scripts/s3-index.sh get b data/artifacts/index.json"])


def test_every_writer_passes_the_switch_and_only_writers_do() -> None:
    for name, step in _all_steps():
        text = _run_text(step)
        puts = "s3-index.sh put" in text
        env = step.get("env") or {}
        assert puts == ("INDEX_GZIP" in env), (name, step.get("name"))
        if puts:
            assert env["INDEX_GZIP"] == "${{ vars.INDEX_GZIP }}"


def test_the_switch_defaults_to_the_old_behavior() -> None:
    """Merging changes no stored byte until the owner sets INDEX_GZIP=1."""
    assert 'if [ "${INDEX_GZIP:-}" = "1" ]' in SCRIPT.read_text()


def test_the_iam_policies_still_name_the_same_index_key() -> None:
    """Same key, so no policy change: the read and write grants already cover it."""
    for relative in ("infra/artifacts/main.tf", "infra/artifacts/github_oidc.tf"):
        assert "/data/artifacts/index.json" in (ROOT / relative).read_text()
    assert "index.json.gz" not in " ".join(path.read_text() for path in WORKFLOWS.glob("*.yml"))
