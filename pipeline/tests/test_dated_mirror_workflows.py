"""The dated-artifact mirror: a re-run of a history job must not re-read the store.

``history-export.yml`` and ``trend-history-repair.yml`` used to download every
dated record (~300,000 objects, ~10 GB on 2026-10-22) on each run, so each manual
re-run of a month cost another ~10 GB of S3 egress. They now sync into a mirror
restored from the Actions cache, with ``--exact-timestamps --delete``.

These tests run the workflow steps themselves, the real ``run:`` text, under a
stand-in ``aws`` whose bucket is a directory. The stand-in implements the sync
rules that matter (size or timestamp decide a download, ``--delete`` removes what
the bucket no longer has) and counts every byte it hands out. The cache is the
mirror directory carried from one run to the next.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CACHE_ACTION = "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
SAVE_ACTION = "actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"

FAKE_AWS = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import fnmatch, json, os, shutil, sys
    from pathlib import Path

    store = Path(os.environ["FAKE_BUCKET_DIR"])
    log = Path(os.environ["FAKE_AWS_LOG"])
    args = sys.argv[1:]

    def record(**entry):
        with log.open("a") as handle:
            handle.write(json.dumps(entry) + "\\n")

    if args[:1] == ["configure"]:
        sys.exit(0)

    if args[:2] == ["s3", "cp"]:
        key = args[2].split("/", 3)[3]
        shutil.copyfile(store / key, args[3])
        record(op="get", key=key, bytes=(store / key).stat().st_size)
        sys.exit(0)

    assert args[:2] == ["s3", "sync"], args
    src, dst = args[2], Path(args[3])
    prefix = src.split("/", 3)[3].rstrip("/")
    rules, exact, delete, i = [], False, False, 4
    while i < len(args):
        if args[i] in ("--exclude", "--include"):
            rules.append((args[i][2:], args[i + 1]))
            i += 2
            continue
        exact = exact or args[i] == "--exact-timestamps"
        delete = delete or args[i] == "--delete"
        i += 1

    def selected(rel):
        verdict = True
        for kind, pattern in rules:
            if fnmatch.fnmatchcase(rel, pattern):
                verdict = kind == "include"
        return verdict

    remote = {}
    for path in (store / prefix).rglob("*"):
        if path.is_file():
            rel = path.relative_to(store / prefix).as_posix()
            if selected(rel):
                remote[rel] = path
    dst.mkdir(parents=True, exist_ok=True)
    moved = 0
    for rel, path in sorted(remote.items()):
        local = dst / rel
        s3 = path.stat()
        if local.exists():
            have = local.stat()
            if exact:
                stale = have.st_size != s3.st_size or int(have.st_mtime) != int(s3.st_mtime)
            else:
                stale = have.st_size != s3.st_size or have.st_mtime < s3.st_mtime
            if not stale:
                continue
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, local)
        moved += s3.st_size
        print(f"download: s3://{src}/{rel} to {local}")
    removed = 0
    if delete:
        for path in sorted(dst.rglob("*")):
            if path.is_file():
                rel = path.relative_to(dst).as_posix()
                if selected(rel) and rel not in remote:
                    path.unlink()
                    removed += 1
                    print(f"delete: {path}")
    record(op="sync", bytes=moved, deleted=removed)
    """
)


def _step(workflow: str, name: str) -> dict[str, Any]:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text())
    for job in document["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == name:
                return dict(step)
    raise AssertionError(f"{workflow} has no step named {name!r}")


CASES = [
    pytest.param(
        "history-export.yml",
        "Hydrate the dated artifacts from S3",
        "pipeline",
        "../data/artifacts",
        id="history-export",
    ),
    pytest.param(
        "trend-history-repair.yml",
        "Mirror the dated records and the current index",
        ".",
        "dated-artifact-mirror",
        id="trend-history-repair",
    ),
]


def _dated(rel: str) -> bool:
    return rel.rsplit("/", 1)[-1][:4].isdigit()


class World:
    """One bucket, one runner temp dir (the cache lives in it), many job runs."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.bucket = tmp_path / "bucket"
        (self.bucket / "data" / "artifacts").mkdir(parents=True)
        self.cache = tmp_path / "cache"  # what the Actions cache holds between runs
        self.log = tmp_path / "aws.log"
        self.log.write_text("")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "aws").write_text(FAKE_AWS)
        (bin_dir / "aws").chmod(0o755)
        self.bin = bin_dir
        self.clock = 1_700_000_000

    def put(self, rel: str, data: bytes, *, mtime: int | None = None) -> None:
        path = self.bucket / "data" / "artifacts" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.clock += 10
        stamp = self.clock if mtime is None else mtime
        os.utime(path, (stamp, stamp))

    def drop(self, rel: str) -> None:
        (self.bucket / "data" / "artifacts" / rel).unlink()

    def expected_dated(self) -> dict[str, bytes]:
        base = self.bucket / "data" / "artifacts"
        return {
            p.relative_to(base).as_posix(): p.read_bytes()
            for p in sorted(base.rglob("*.json"))
            if _dated(p.relative_to(base).as_posix())
        }

    def run(
        self,
        workflow: str,
        step_name: str,
        cwd: str,
        tree: str,
        *,
        warm: bool,
        edit: Any = None,
    ) -> dict[str, Any]:
        """Run one job's hydrate step; `warm` restores the cache first."""
        runner = self.root / f"runner-{len(list(self.root.glob('runner-*')))}"
        work = runner / "work"
        (work / "pipeline").mkdir(parents=True)
        (work / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "s3-index.sh", work / "scripts" / "s3-index.sh")
        temp = runner / "tmp"
        temp.mkdir()
        mirror = temp / "dated-artifact-mirror"
        if warm and self.cache.exists():
            shutil.copytree(self.cache, mirror, copy_function=shutil.copy2)
        script = str(_step(workflow, step_name)["run"])
        script = script.replace("-lt 1000", "-lt 1")  # the fixture is not 1,000 records
        if edit is not None:
            edited = edit(script)
            assert edited != script, "the sabotage did not apply"
            script = edited
        output = runner / "output.txt"
        output.write_text("")
        before = len(self.log.read_text().splitlines())
        done = subprocess.run(  # noqa: S603 - fixed shell and a repository-owned workflow step
            ["/bin/bash", "-c", script],
            cwd=work / cwd,
            env={
                **os.environ,
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "FAKE_BUCKET_DIR": str(self.bucket),
                "FAKE_AWS_LOG": str(self.log),
                "ARTIFACTS_BUCKET": "bucket",
                "RUNNER_TEMP": str(temp),
                "GITHUB_OUTPUT": str(output),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        if self.cache.exists():
            shutil.rmtree(self.cache)
        shutil.copytree(mirror, self.cache, copy_function=shutil.copy2)
        entries = [json.loads(x) for x in self.log.read_text().splitlines()[before:]]
        outputs = dict(
            line.split("=", 1) for line in output.read_text().splitlines() if "=" in line
        )
        dated_root = (work / "data" / "artifacts") if tree.startswith("..") else mirror
        return {
            "sync_bytes": sum(e["bytes"] for e in entries if e["op"] == "sync"),
            "index_bytes": sum(e["bytes"] for e in entries if e["op"] == "get"),
            "outputs": outputs,
            "tree": {
                p.relative_to(dated_root).as_posix(): p.read_bytes()
                for p in sorted(dated_root.rglob("*.json"))
                if _dated(p.relative_to(dated_root).as_posix())
            },
        }


@pytest.fixture
def world(tmp_path: Path) -> World:
    w = World(tmp_path)
    for agency in range(40):
        for day in range(1, 6):
            w.put(f"agency-{agency:02d}/2026-10-{day:02d}.json", (f"{agency}:{day}" * 200).encode())
        w.put(f"agency-{agency:02d}/latest.json", b'{"latest": true}')
        w.put(f"agency-{agency:02d}/geometry.geojson", b"G" * 5000)
    w.put("index.json", b'{"agencies": {}}\n')
    return w


@pytest.mark.parametrize(("workflow", "step", "cwd", "tree"), CASES)
def test_a_warm_rerun_reads_nothing_and_builds_the_same_tree(
    world: World, workflow: str, step: str, cwd: str, tree: str
) -> None:
    cold = world.run(workflow, step, cwd, tree, warm=False)
    expected = world.expected_dated()
    total = sum(len(v) for v in expected.values())
    assert cold["tree"] == expected
    assert cold["sync_bytes"] == total > 0
    # Not the geometry or latest files: only the dated records are mirrored.
    assert not any(name.endswith(("latest.json", "geometry.geojson")) for name in cold["tree"])

    warm = world.run(workflow, step, cwd, tree, warm=True)

    assert warm["tree"] == cold["tree"] == expected
    assert warm["sync_bytes"] == 0
    assert warm["outputs"]["downloads"] == "0"
    print(f"{workflow}: cold {cold['sync_bytes']} bytes, warm re-run {warm['sync_bytes']} bytes")


@pytest.mark.parametrize(("workflow", "step", "cwd", "tree"), CASES)
def test_a_warm_run_fetches_only_what_the_store_changed_and_drops_what_expired(
    world: World, workflow: str, step: str, cwd: str, tree: str
) -> None:
    world.run(workflow, step, cwd, tree, warm=False)
    added = {f"agency-{n:02d}/2026-10-06.json": f"new {n}".encode() * 50 for n in range(7)}
    for rel, data in added.items():
        world.put(rel, data)
    # Same size, OLDER timestamp: the case only `--exact-timestamps` re-reads.
    victim = "agency-03/2026-10-02.json"
    original = (world.bucket / "data" / "artifacts" / victim).read_bytes()
    replaced = bytes(reversed(original))
    assert replaced != original and len(replaced) == len(original)
    world.put(victim, replaced, mtime=1_000_000_000)
    world.drop("agency-05/2026-10-01.json")  # expired by the lifecycle rule

    warm = world.run(workflow, step, cwd, tree, warm=True)

    assert warm["tree"] == world.expected_dated()
    assert warm["tree"][victim] == replaced
    assert "agency-05/2026-10-01.json" not in warm["tree"]
    assert warm["sync_bytes"] == sum(len(v) for v in added.values()) + len(replaced)
    assert warm["outputs"]["downloads"] == str(len(added) + 1)
    assert warm["outputs"]["removed"] == "1"


@pytest.mark.parametrize(("workflow", "step", "cwd", "tree"), CASES)
def test_negative_controls_each_sabotage_applies_and_the_tree_goes_wrong(
    world: World, workflow: str, step: str, cwd: str, tree: str
) -> None:
    world.run(workflow, step, cwd, tree, warm=False)
    victim = "agency-03/2026-10-02.json"
    original = (world.bucket / "data" / "artifacts" / victim).read_bytes()
    world.put(victim, bytes(reversed(original)), mtime=1_000_000_000)
    world.drop("agency-05/2026-10-01.json")
    expected = world.expected_dated()

    sabotages = {
        "drops exact timestamps": lambda s: s.replace("--exact-timestamps", ""),
        "drops delete": lambda s: s.replace("--delete", ""),
    }
    pristine = world.root / "cache-before-sabotage"
    shutil.copytree(world.cache, pristine, copy_function=shutil.copy2)
    for label, edit in sabotages.items():
        # Every sabotage starts from the same restored cache.
        shutil.rmtree(world.cache)
        shutil.copytree(pristine, world.cache, copy_function=shutil.copy2)
        broken = world.run(workflow, step, cwd, tree, warm=True, edit=edit)
        assert broken["tree"] != expected, f"nothing noticed the sabotage that {label}"

    # And the intact step on the same starting cache is right.
    shutil.rmtree(world.cache)
    shutil.copytree(pristine, world.cache, copy_function=shutil.copy2)
    assert world.run(workflow, step, cwd, tree, warm=True)["tree"] == expected


@pytest.mark.parametrize(("workflow", "step", "cwd", "tree"), CASES)
def test_negative_control_without_the_cache_every_run_reads_everything(
    world: World, workflow: str, step: str, cwd: str, tree: str
) -> None:
    """The saving belongs to the restored mirror, not to the fixture."""
    first = world.run(workflow, step, cwd, tree, warm=False)
    second = world.run(workflow, step, cwd, tree, warm=False)
    assert second["sync_bytes"] == first["sync_bytes"] > 0


def test_history_export_still_refuses_a_corpus_too_small_to_sell(world: World) -> None:
    step = _step("history-export.yml", "Hydrate the dated artifacts from S3")["run"]
    assert "-lt 1000" in str(step)


def test_history_export_reads_the_index_through_the_script_after_the_mirror(
    world: World,
) -> None:
    run = str(_step("history-export.yml", "Hydrate the dated artifacts from S3")["run"])
    assert run.index("aws s3 sync") < run.index("cp -a") < run.index("s3-index.sh get")
    assert '--include "index.json"' not in run


# --- the cache steps ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("workflow", "hydrate_id"),
    [("history-export.yml", "hydrate"), ("trend-history-repair.yml", "mirror")],
)
def test_cache_is_shared_pinned_and_saved_only_when_the_mirror_moved(
    workflow: str, hydrate_id: str
) -> None:
    document = yaml.safe_load((WORKFLOWS / workflow).read_text())
    steps = [s for job in document["jobs"].values() for s in job["steps"]]
    restore = next(s for s in steps if str(s.get("uses", "")).startswith(CACHE_ACTION))
    save = next(s for s in steps if str(s.get("uses", "")).startswith(SAVE_ACTION))

    shared_path = "${{ runner.temp }}/dated-artifact-mirror"
    assert restore["with"]["path"] == save["with"]["path"] == shared_path
    assert restore["with"]["key"] == save["with"]["key"]
    assert restore["with"]["key"].startswith("dated-artifact-mirror-v1-")
    assert restore["with"]["restore-keys"].strip() == "dated-artifact-mirror-v1-"
    condition = str(save["if"])
    assert f"steps.{hydrate_id}.outputs.downloads != '0'" in condition
    assert f"steps.{hydrate_id}.outputs.removed != '0'" in condition
    assert "cache-matched-key == ''" in condition
    # Restore before the sync, save after it.
    names = [s.get("name") for s in steps]
    assert names.index(restore["name"]) < names.index(save["name"])
    hydrate = next(s for s in steps if s.get("id") == hydrate_id)
    assert names.index(restore["name"]) < steps.index(hydrate) < names.index(save["name"])


def test_both_workflows_use_the_same_object_filter_so_the_shared_mirror_agrees() -> None:
    patterns = set()
    for workflow, name in (
        ("history-export.yml", "Hydrate the dated artifacts from S3"),
        ("trend-history-repair.yml", "Mirror the dated records and the current index"),
    ):
        run = str(_step(workflow, name)["run"])
        for line in run.splitlines():
            if "--include" in line and "[0-9]" in line:
                patterns.add(line.strip().split("--include", 1)[1].split("\\")[0].strip())
    assert patterns == {'"*/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"'}


def test_the_mirror_holds_public_dated_records_only() -> None:
    """Nothing private is cached: the filter is the dated-record glob, nothing else."""
    for workflow, name in (
        ("history-export.yml", "Hydrate the dated artifacts from S3"),
        ("trend-history-repair.yml", "Mirror the dated records and the current index"),
    ):
        run = str(_step(workflow, name)["run"])
        assert '--exclude "*"' in run
        assert "cache/" not in run.replace("# ", "")
        assert "fixlog" not in run and "structure" not in run
