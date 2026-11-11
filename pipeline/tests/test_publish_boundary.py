"""The published JSON copies are compact and the index history is bounded.

``publish_boundary.py`` runs at the deployment boundary after the public
artifact assembly copied the documented filenames (see
``test_artifacts_cdn_privacy.py`` for the assembled-site checks). These tests
pin the module's own rules: same object, fewer bytes; the newest 120 points;
two unread fields gone from index points and nowhere else.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scorecard_pipeline.mcp_server import MAX_HISTORY_POINTS
from scorecard_pipeline.publish_boundary import (
    PUBLISHED_HISTORY_POINTS,
    UNPUBLISHED_INDEX_POINT_FIELDS,
    compact_json_text,
    main,
    slim_index,
    slim_tree,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "pipeline" / "src" / "scorecard_pipeline" / "publish_boundary.py"


def _point(date: str, **extra: Any) -> dict[str, Any]:
    point = {
        "categories": {"freshness": 100.0},
        "date": date,
        "days_until_expiry": 40,
        "feed_sha256": "ab" * 32,
        "grade": "B",
        "score": 80.0,
        "service_horizon_status": "within_review_threshold",
    }
    point.update(extra)
    return point


def _dates(count: int) -> list[str]:
    return [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(count)]


def _index(points: int) -> dict[str, Any]:
    return {
        "agencies": {
            "demo": {"name": "Demo", "history": [_point(d) for d in _dates(points)]},
            "few": {"name": "Few", "history": [_point(d) for d in _dates(3)]},
        }
    }


def _is_compact(text: str) -> bool:
    return text == json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=text.isascii())


def test_compact_json_text_keeps_the_object_key_order_and_escaping() -> None:
    pretty = json.dumps({"z": [1, 2.5, None], "a": {"é": "ü"}}, indent=2, sort_keys=True) + "\n"
    compact = compact_json_text(pretty)
    assert json.loads(compact) == json.loads(pretty)
    assert list(json.loads(compact)) == ["a", "z"], "key order is the file's, not re-sorted"
    assert compact == '{"a":{"\\u00e9":"\\u00fc"},"z":[1,2.5,null]}'
    assert _is_compact(compact)
    assert not _is_compact(pretty), "the compactness check can fail"

    raw = '{\n  "name": "Café"\n}\n'
    assert compact_json_text(raw) == '{"name":"Café"}', "raw UTF-8 stays raw"


def test_slim_index_caps_at_the_newest_points_and_drops_the_two_fields() -> None:
    index = _index(PUBLISHED_HISTORY_POINTS + 10)
    oldest = index["agencies"]["demo"]["history"][0]["date"]
    newest = index["agencies"]["demo"]["history"][-1]["date"]

    assert slim_index(index) == (10, 2 * (PUBLISHED_HISTORY_POINTS + 3))

    demo = index["agencies"]["demo"]["history"]
    assert len(demo) == PUBLISHED_HISTORY_POINTS
    assert demo[-1]["date"] == newest and demo[0]["date"] != oldest
    assert [p["date"] for p in demo] == sorted(p["date"] for p in demo)
    assert len(index["agencies"]["few"]["history"]) == 3, "a short history is untouched"
    for entry in index["agencies"].values():
        for point in entry["history"]:
            assert not set(UNPUBLISHED_INDEX_POINT_FIELDS) & set(point)
            assert {"date", "grade", "score", "categories", "days_until_expiry"} <= set(point)


def test_slim_index_publishes_oldest_to_newest_even_from_an_unordered_history() -> None:
    index = {"agencies": {"x": {"history": [_point("2026-03-01"), _point("2026-01-01")]}}}
    slim_index(index)
    assert [p["date"] for p in index["agencies"]["x"]["history"]] == ["2026-01-01", "2026-03-01"]


def test_slim_index_leaves_anything_that_is_not_an_agency_index_alone() -> None:
    rollup_index = {"rollups": [{"id": "california", "feed_sha256": "x"}]}
    assert slim_index(rollup_index) == (0, 0)
    assert rollup_index == {"rollups": [{"id": "california", "feed_sha256": "x"}]}
    odd = {"agencies": {"a": "not an object", "b": {"history": "not a list"}, "c": {}}}
    assert slim_index(odd) == (0, 0)
    assert slim_index(["not", "a", "dict"]) == (0, 0)
    mixed = {"agencies": {"m": {"history": ["junk", _point("2026-01-01")]}}}
    assert slim_index(mixed) == (0, 2)


def test_the_published_cap_is_the_mcp_ceiling() -> None:
    """One number: a point the site publishes is a point the MCP can return."""
    assert PUBLISHED_HISTORY_POINTS == MAX_HISTORY_POINTS == 120


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "site"
    (root / "demo").mkdir(parents=True)
    (root / "rollups").mkdir()
    (root / "index.json").write_text(json.dumps(_index(130), indent=2, sort_keys=True) + "\n")
    latest = {
        "agency": {"id": "demo"},
        "categories": {"freshness": {"details": {"service_horizon_status": "unknown"}}},
        "feed": {"sha256": "ab" * 32},
    }
    for name in ("latest.json", "2026-11-10.json"):
        (root / "demo" / name).write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n")
    (root / "rollups" / "index.json").write_text(
        json.dumps({"agencies": {"r": {"history": [_point("2026-01-01")]}}}, indent=2) + "\n"
    )
    (root / "demo" / "geometry.geojson").write_text('{"type": "FeatureCollection"}\n')
    (root / "demo" / "badge.json").write_text("not json\n")  # left alone, counted
    return root


def test_slim_tree_measures_without_writing_and_rewrites_with_write(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    before = {p: p.read_text() for p in root.rglob("*") if p.is_file()}

    measured = slim_tree(root, write=False)
    assert measured.files == 4
    assert measured.bytes_after < measured.bytes_before
    assert measured.points_dropped == 10
    assert measured.fields_dropped == 2 * (120 + 3)
    assert measured.skipped == 1
    assert {p: p.read_text() for p in root.rglob("*") if p.is_file()} == before

    written = slim_tree(root, write=True)
    assert written == measured
    for path in root.rglob("*.json"):
        if path.name == "badge.json":
            continue
        assert _is_compact(path.read_text()), path
        assert json.loads(path.read_text()) is not None
    assert (
        root.joinpath("demo", "geometry.geojson").read_text() == '{"type": "FeatureCollection"}\n'
    )
    assert root.joinpath("demo", "badge.json").read_text() == "not json\n"

    index = json.loads((root / "index.json").read_text())
    assert len(index["agencies"]["demo"]["history"]) == 120
    assert "feed_sha256" not in index["agencies"]["demo"]["history"][-1]
    latest = json.loads((root / "demo" / "latest.json").read_text())
    assert latest["feed"]["sha256"] == "ab" * 32
    assert latest["categories"]["freshness"]["details"]["service_horizon_status"] == "unknown"
    assert latest == json.loads(before[root / "demo" / "latest.json"])
    rollups = json.loads((root / "rollups" / "index.json").read_text())
    assert "feed_sha256" in rollups["agencies"]["r"]["history"][0], "only the root index is slimmed"
    assert slim_tree(root, write=True).bytes_saved == 0, "a second pass changes nothing"


def test_cli_prints_counts_and_refuses_a_missing_root(tmp_path: Path, capsys: Any) -> None:
    root = _tree(tmp_path)
    assert main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "would rewrite 4 JSON file(s)" in out
    assert "10 point(s) beyond the newest 120" in out
    assert "1 file(s) not JSON, left as they were" in out
    assert "ab" * 32 not in out
    assert not _is_compact((root / "index.json").read_text())

    assert main([str(root), "--write"]) == 0
    assert "rewrote 4 JSON file(s)" in capsys.readouterr().out
    assert _is_compact((root / "index.json").read_text())

    assert main([str(tmp_path / "missing")]) == 2


def test_the_module_runs_as_a_standalone_script(tmp_path: Path) -> None:
    """The assembly script runs it with ``python3 -I`` and no pipeline env."""
    root = _tree(tmp_path)
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test-owned paths
        [sys.executable, "-I", str(MODULE), str(root), "--write"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "rewrote 4 JSON file(s)" in result.stdout
    assert _is_compact((root / "index.json").read_text())
