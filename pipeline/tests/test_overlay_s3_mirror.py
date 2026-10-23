"""The S3 mirror overlay must leave the working tree exactly as the direct sync did.

The Intraday refresh and the Deploy site build used to run
``aws s3 sync s3://bucket/data/artifacts data/artifacts --include ...`` on every
run. They now sync into a cached mirror and lay the mirror over the tree with
``scripts/overlay-s3-mirror.sh``. The product's output depends on that tree, so
the property under test is byte equality: for the same bucket contents, the tree
the new flow builds equals the tree the old flow built, including the cases a
cache can get wrong (a dated snapshot left over from an earlier day, a
date-named aggregate file, a committed file the sync never touched).

Nothing here needs AWS. The bucket is a dictionary; the old flow is "copy every
object the include list names over the checkout", which is what the direct
sync did to a fresh checkout whose files are all newer than their objects.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "overlay-s3-mirror.sh"

TODAY = "2026-10-21"
YESTERDAY = "2026-10-20"
OLDER = "2026-10-19"
OLDEST = "2026-10-18"

# What the bucket holds. Keys are relative to data/artifacts/.
BUCKET: dict[str, bytes] = {
    "a/latest.json": b"a latest from s3",
    f"a/{TODAY}.json": b"a today",
    f"a/{YESTERDAY}.json": b"a yesterday",
    f"a/{OLDER}.json": b"a older, not in the bounded set",
    "b/latest.json": b"b latest from s3",
    f"b/{TODAY}.json": b"b today",
    f"b/{YESTERDAY}.json": b"b yesterday",
    "b/badge.svg": b"<svg>b</svg>",
    "changes/2026-08-06.json": b"changes dated, aggregate",
    "changes/latest.json": b"changes latest",
    f"changes/{OLDER}.json": b"changes dated, older than yesterday",
    "rollups/alabama.json": b"rollup",
    "run/2026-09-01.json": b"run dated, aggregate",
    "directory.json": b"directory",
}


def _included(key: str) -> bool:
    """The include list the workflows pass: what the direct sync copied."""
    if key.startswith(("changes/", "rollups/", "run/")) or key == "directory.json":
        return True
    name = key.rsplit("/", 1)[-1]
    return name in {"latest.json", "badge.svg", f"{TODAY}.json", f"{YESTERDAY}.json"}


def _write(root: Path, files: dict[str, bytes]) -> None:
    for key, body in files.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


def _read(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


# A fresh checkout: committed files, none of which the bucket is obliged to match.
CHECKOUT: dict[str, bytes] = {
    "index.json": b"committed index",
    "a/latest.json": b"committed a latest",
    f"a/{OLDER}.json": b"committed a older",
    f"a/{OLDEST}.json": b"committed a oldest",
    "z/latest.json": b"committed z, retired from the bucket",
}

# What a restored mirror holds before the overlay: yesterday's mirror, synced
# to the current bucket. `--delete` has already removed objects the bucket
# lost, but the dated files from days outside the include list match neither
# the filters nor the delete, so they survive the sync.
STALE_IN_MIRROR: dict[str, bytes] = {
    f"a/{OLDER}.json": b"stale mirror copy of a older",
    f"b/{OLDEST}.json": b"stale mirror copy of b oldest",
}


def _old_flow(dest: Path) -> None:
    """The direct sync: every included object overwrites the checkout."""
    _write(dest, CHECKOUT)
    _write(dest, {key: body for key, body in BUCKET.items() if _included(key)})


def _mirror_before_overlay(mirror: Path) -> None:
    _write(mirror, {key: body for key, body in BUCKET.items() if _included(key)})
    _write(mirror, STALE_IN_MIRROR)


def _run(
    script: Path, mirror: Path, dest: Path, today: str = TODAY
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(script), str(mirror), str(dest), today, YESTERDAY],
        capture_output=True,
        text=True,
        check=False,
    )


def test_overlay_builds_the_same_tree_as_the_direct_sync(tmp_path: Path) -> None:
    expected = tmp_path / "old"
    _old_flow(expected)

    mirror = tmp_path / "mirror"
    _mirror_before_overlay(mirror)
    actual = tmp_path / "new"
    _write(actual, CHECKOUT)
    result = _run(SCRIPT, mirror, actual)

    assert result.returncode == 0, result.stderr
    assert _read(actual) == _read(expected)
    # The cases the equality above is guarding, stated so a future edit that
    # weakens the fixture is visible.
    tree = _read(actual)
    assert tree["a/latest.json"] == b"a latest from s3", "S3 wins over the committed copy"
    assert tree[f"a/{OLDER}.json"] == b"committed a older", "a committed file is not touched"
    assert f"b/{OLDEST}.json" not in tree, "a stale mirror-only dated file is not carried over"
    assert tree["changes/2026-08-06.json"] == b"changes dated, aggregate"
    assert tree["run/2026-09-01.json"] == b"run dated, aggregate"
    assert tree["z/latest.json"] == b"committed z, retired from the bucket"


def test_overlay_prunes_the_mirror_so_the_saved_cache_stays_bounded(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    _mirror_before_overlay(mirror)
    dest = tmp_path / "dest"

    assert _run(SCRIPT, mirror, dest).returncode == 0

    kept = _read(mirror)
    assert f"b/{OLDEST}.json" not in kept
    assert f"a/{OLDER}.json" not in kept
    assert f"a/{TODAY}.json" in kept and f"a/{YESTERDAY}.json" in kept
    assert f"changes/{OLDER}.json" in kept, "aggregate directories are never pruned"


def test_negative_control_without_the_prune_a_stale_dated_file_reaches_the_tree(
    tmp_path: Path,
) -> None:
    """A control that asserts its sabotage applied, then shows the prune matters."""
    original = SCRIPT.read_text(encoding="utf-8")
    sabotaged = re.sub(r"^find .*?-delete\n", "", original, count=1, flags=re.S | re.M)
    assert sabotaged != original, "the sabotage did not remove the prune"
    assert re.search(r"^\s+-delete$", original, re.M), "the control targets the real prune"
    assert not re.search(r"^\s+-delete$", sabotaged, re.M)

    broken = tmp_path / "overlay-without-prune.sh"
    broken.write_text(sabotaged, encoding="utf-8")

    expected = tmp_path / "old"
    _old_flow(expected)
    mirror = tmp_path / "mirror"
    _mirror_before_overlay(mirror)
    actual = tmp_path / "new"
    _write(actual, CHECKOUT)

    assert _run(broken, mirror, actual).returncode == 0
    assert _read(actual) != _read(expected)
    assert f"b/{OLDEST}.json" in _read(actual)


@pytest.mark.parametrize("bad_today", ["", "yesterday", "2026-10-2", "2026-10-21.json", "*"])
def test_overlay_refuses_anything_that_is_not_a_date(tmp_path: Path, bad_today: str) -> None:
    mirror = tmp_path / "mirror"
    _mirror_before_overlay(mirror)
    before = _read(mirror)
    dest = tmp_path / "dest"

    result = _run(SCRIPT, mirror, dest, today=bad_today)

    assert result.returncode == 2
    assert _read(mirror) == before, "nothing is pruned when the dates are not trusted"
    assert not dest.exists()


def test_overlay_refuses_a_missing_mirror(tmp_path: Path) -> None:
    result = _run(SCRIPT, tmp_path / "absent", tmp_path / "dest")

    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_overlay_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & 0o111, "scripts/overlay-s3-mirror.sh must be executable"
    assert shutil.which("bash")
