"""Tests for CLI helpers that don't require fetching or the Java validator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.cli import _try_gate


def _artifact(grade: str, days: int | None) -> dict:  # type: ignore[type-arg]
    return {
        "overall": {"grade": grade, "score": 0},
        "categories": {"freshness": {"details": {"days_until_expiry": days}}},
    }


def _args(min_grade: str | None = None, min_days: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(min_grade=min_grade, min_days_to_expiry=min_days)


def test_gate_passes_without_thresholds() -> None:
    assert _try_gate(_artifact("F", -5), _args()) == 0


def test_gate_fails_below_min_grade() -> None:
    assert _try_gate(_artifact("C", 90), _args(min_grade="B")) == 1
    assert _try_gate(_artifact("B", 90), _args(min_grade="B")) == 0
    assert _try_gate(_artifact("A", 90), _args(min_grade="B")) == 0


def test_gate_fails_when_expiring_too_soon() -> None:
    assert _try_gate(_artifact("A", 10), _args(min_days=30)) == 1
    assert _try_gate(_artifact("A", 45), _args(min_days=30)) == 0
    assert _try_gate(_artifact("A", None), _args(min_days=30)) == 1  # no expiry date fails


def test_gate_combines_thresholds() -> None:
    # Grade ok but expiring too soon still fails.
    assert _try_gate(_artifact("A", 5), _args(min_grade="B", min_days=30)) == 1


def test_prune_reports_orphans_without_deleting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scorecard_pipeline import cli

    art = tmp_path / "data" / "artifacts"
    (art / "still-here").mkdir(parents=True)
    (art / "long-gone").mkdir()
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "AGENCIES", {"still-here": object()})
    parser = argparse.ArgumentParser()

    args = argparse.Namespace(delete=False)
    assert cli._cmd_prune(args, parser) == 0
    out = capsys.readouterr().out
    assert "orphan\tlong-gone" in out
    assert "Report only" in out
    assert (art / "long-gone").exists()  # never deletes without --delete

    args = argparse.Namespace(delete=True)
    assert cli._cmd_prune(args, parser) == 0
    assert not (art / "long-gone").exists()
    assert (art / "still-here").exists()


def test_prune_never_flags_reserved_dirs_as_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """rollups/, changes/, and run/ (FIX-11's run-health summary) hold published
    aggregates, not agencies, so prune must never report them as orphans."""
    from scorecard_pipeline import cli

    art = tmp_path / "data" / "artifacts"
    (art / "rollups").mkdir(parents=True)
    (art / "changes").mkdir()
    (art / "run").mkdir()
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path))
    monkeypatch.setattr(cli, "AGENCIES", {})
    parser = argparse.ArgumentParser()

    args = argparse.Namespace(delete=False)
    assert cli._cmd_prune(args, parser) == 0
    out = capsys.readouterr().out
    assert "no orphaned artifact directories" in out


def test_run_summary_build_and_merge_end_to_end(tmp_path: Path, isolated_repo_root: Path) -> None:
    """`scorecard run-summary build` turns an outcome log into a shard summary;
    `scorecard run-summary merge` combines shard summaries into the artifact
    /status/ reads."""
    from scorecard_pipeline.cli import main
    from scorecard_pipeline.run_summary import AgencyOutcome, append_outcome

    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )

    outcomes_path = tmp_path / "outcomes.ndjson"
    append_outcome(outcomes_path, AgencyOutcome("unitrans", "scored", cache_hit=True))
    append_outcome(outcomes_path, AgencyOutcome("yolobus", "unreachable"))

    summary_path = tmp_path / "run-summary-0.json"
    exit_code = main(
        [
            "run-summary",
            "build",
            "--shard",
            "0",
            "--outcomes",
            str(outcomes_path),
            "--started",
            "2026-07-08T13:23:00+00:00",
            "--out",
            str(summary_path),
        ]
    )
    assert exit_code == 0
    summary = json.loads(summary_path.read_text())
    assert summary["scored"] == 1
    assert summary["unreachable"] == 1
    assert summary["unreachable_agencies"] == ["yolobus"]

    merged_path = tmp_path / "run" / "latest.json"
    exit_code = main(["run-summary", "merge", "--out", str(merged_path), str(summary_path)])
    assert exit_code == 0
    merged = json.loads(merged_path.read_text())
    assert merged["scored"] == 1
    assert merged["unreachable"] == 1
    assert merged["shard_count"] == 1


def test_run_summary_merge_skips_missing_shard_files(
    tmp_path: Path, isolated_repo_root: Path
) -> None:
    """A shard whose runner crashed before uploading its summary is simply
    absent; merge must not raise, and totals undercount rather than fail."""
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
    )

    merged_path = tmp_path / "run" / "latest.json"
    exit_code = main(
        ["run-summary", "merge", "--out", str(merged_path), str(tmp_path / "missing.json")]
    )
    assert exit_code == 0
    merged = json.loads(merged_path.read_text())
    assert merged["shard_count"] == 0
    assert merged["agency_count"] == 0


def _write_manifest_registry(root: Path) -> tuple[Path, Path]:
    first = root / "registry/a.yaml"
    second = root / "registry/b.yaml"
    first.parent.mkdir(parents=True)
    first.write_text(
        yaml.safe_dump(
            {
                "agencies": [
                    {
                        "id": "first",
                        "name": "First Transit",
                        "static_gtfs_url": "https://old.example/first.zip",
                        "mdb_id": "100",
                    }
                ]
            },
            sort_keys=False,
        )
    )
    second.write_text(
        yaml.safe_dump(
            {
                "agencies": [
                    {
                        "id": "second",
                        "name": "Second Transit",
                        "static_gtfs_url": "https://second.example/gtfs.zip",
                        "state": "Oregon",
                    }
                ]
            },
            sort_keys=False,
        )
    )
    (root / "registry/index.yaml").write_text("shards:\n  - registry/a.yaml\n  - registry/b.yaml\n")
    return first, second


def test_backfill_state_applies_only_to_the_manifest_shard_with_a_match(
    tmp_path: Path, isolated_repo_root: Path
) -> None:
    from scorecard_pipeline.cli import main

    first, second = _write_manifest_registry(isolated_repo_root)
    untouched = second.read_bytes()
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "mdb_source_id,data_type,location.country_code,location.subdivision_name,"
        "provider,name,urls.direct_download\n"
        "100,gtfs,US,California,First Transit,First Transit,"
        "https://new.example/first.zip\n"
    )

    assert main(["backfill-state", "--catalog", str(catalog), "--apply"]) == 0

    assert "state: California" in first.read_text()
    assert second.read_bytes() == untouched


def test_discover_applies_a_replacement_only_to_the_owning_manifest_shard(
    tmp_path: Path, isolated_repo_root: Path
) -> None:
    from scorecard_pipeline.cli import main

    first, second = _write_manifest_registry(isolated_repo_root)
    untouched = second.read_bytes()
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "mdb_source_id,data_type,location.country_code,location.subdivision_name,"
        "provider,name,urls.direct_download\n"
        "100,gtfs,US,California,First Transit,First Transit,"
        "https://new.example/first.zip\n"
    )

    assert main(["discover", "--catalog", str(catalog), "--apply"]) == 0

    assert "static_gtfs_url: https://new.example/first.zip" in first.read_text()
    assert second.read_bytes() == untouched


def test_sync_only_emits_untracked_credential_free_schedule_feeds(
    tmp_path: Path,
    isolated_repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: tracked\n"
        "    name: Tracked Transit\n"
        "    static_gtfs_url: https://tracked.example/feed.zip\n"
        "    mdb_id: tracked-id\n"
    )
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "mdb_source_id,data_type,provider,name,urls.direct_download,"
        "urls.authentication_type\n"
        "tracked-id,gtfs,Renamed Transit,Renamed Transit,https://new.example/feed.zip,0\n"
        "url-copy,gtfs,URL Copy,URL Copy,http://tracked.example/feed.zip/,none\n"
        "gated,gtfs,Gated Transit,Gated Transit,https://gated.example/feed.zip,1\n"
        "fresh,gtfs,Fresh Transit,Fresh Transit,https://fresh.example/feed.zip,0\n"
    )

    assert main(["sync", "--catalog", str(catalog)]) == 0

    output = capsys.readouterr().out
    assert "id: fresh-transit" in output
    assert "tracked-id" not in output
    assert "id: url-copy" not in output
    assert "id: gated-transit" not in output


_SYNC_PROVENANCE_CATALOG = (
    b"id,data_type,entity_type,location.country_code,"
    b"location.subdivision_name,provider,name,urls.direct_download,"
    b"urls.authentication_type,status,is_official,static_reference\n"
    b"mdb-00100,gtfs,,US,California,Tracked Transit,Tracked Transit,"
    b"https://tracked.example/new.zip,0,active,true,\n"
    b"mdb-200,gtfs,,US,California,Fresh Transit,Fresh Transit,"
    b"https://fresh.example/feed.zip,none,active,true,\n"
    b"mdb-300,gtfs,,US,California,Gated Transit,Gated Transit,"
    b"https://gated.example/feed.zip,1,active,true,\n"
    b"mdb-400,gtfs,,US,California,Unofficial Transit,Unofficial Transit,"
    b"https://unofficial.example/feed.zip,0,active,false,\n"
    b"mdb-500,gtfs,,US,California,Inactive Transit,Inactive Transit,"
    b"https://inactive.example/feed.zip,0,inactive,true,\n"
    b"mdb-201,gtfs_rt,tu,US,California,Fresh Transit,Fresh Realtime,"
    b"https://fresh.example/tu.pb,0,active,true,mdb-200\n"
    b"other,gbfs,,US,California,Bikeshare,Bikeshare,"
    b"https://example.org/gbfs.json,0,active,true,\n"
)


def _write_minimal_sync_registry(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: existing\n"
        "    name: Existing Transit\n"
        "    static_gtfs_url: https://existing.example/feed.zip\n"
        "    mdb_id: existing\n"
    )


def test_sync_source_metadata_is_exact_proposal_only_and_leaves_registry_unchanged(
    tmp_path: Path,
    isolated_repo_root: Path,
) -> None:
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True)
    registry = isolated_repo_root / "agencies.yaml"
    registry.write_text(
        "agencies:\n"
        "  - id: tracked\n"
        "    name: Tracked Transit\n"
        "    static_gtfs_url: https://tracked.example/feed.zip\n"
        "    mdb_id: '100'\n"
    )
    registry_before = registry.read_bytes()
    catalog = tmp_path / "feeds_v2.csv"
    catalog.write_bytes(_SYNC_PROVENANCE_CATALOG)
    proposals = tmp_path / "proposals.yaml"
    metadata_path = tmp_path / "source-metadata.json"

    assert (
        main(
            [
                "sync",
                "--catalog",
                str(catalog),
                "--country",
                "US",
                "--state",
                "California",
                "--provider",
                "Fresh Transit",
                "--out",
                str(proposals),
                "--source-metadata-out",
                str(metadata_path),
            ]
        )
        == 0
    )

    assert registry.read_bytes() == registry_before
    assert "id: fresh-transit" in proposals.read_text()
    metadata = json.loads(metadata_path.read_text())
    header = _SYNC_PROVENANCE_CATALOG.splitlines()[0]
    assert metadata["schema_version"] == "1.0"
    assert metadata["source"] == {
        "name": "Mobility Database",
        "url_or_path": "<local>/feeds_v2.csv",
        "location_redacted": True,
        "command_source": "mobilitydb",
        "excluded_sources": [],
        "catalog_schema": "mobilitydatabase-feeds-v2",
    }
    assert metadata["fetched_at"].endswith("Z")
    assert metadata["raw_bytes_sha256"] == hashlib.sha256(_SYNC_PROVENANCE_CATALOG).hexdigest()
    assert metadata["columns"] == header.decode().split(",")
    assert metadata["header_sha256"] == hashlib.sha256(header).hexdigest()
    assert metadata["record_counts"] == {
        "total_records": 7,
        "schedule_records": 5,
        "realtime_records": 1,
        "active_schedule_records": 4,
        "active_keyless_schedule_records": 3,
        "proposal_eligible_schedule_records": 2,
    }
    assert metadata["filters"] == {
        "country": "US",
        "subdivision": "California",
        "providers": ["Fresh Transit"],
    }
    assert metadata["proposal_count"] == 1
    assert metadata["proposal_count_scope"] == "mobilitydatabase_only"
    assert metadata["proposal_output"] == {
        "sha256": hashlib.sha256(proposals.read_bytes()).hexdigest(),
        "bytes": len(proposals.read_bytes()),
        "format": "registry-yaml-fragment; charset=utf-8; line-endings=lf",
        "scope": "mobilitydatabase_only",
    }
    assert metadata["registry_identity"]["agency_id_count"] == 1
    assert metadata["registry_identity"]["normalized_mdb_id_count"] == 1
    assert metadata["registry_identity"]["normalized_feed_url_count"] == 1
    assert len(metadata["registry_identity"]["sha256"]) == 64
    assert metadata["tool"]["package"] == "scorecard-pipeline"
    assert metadata["tool"]["proposal_contract_version"] == "1.0"
    assert len(metadata["tool"]["python_source_tree_sha256"]) == 64
    assert metadata["tool"]["python_source_file_count"] > 0
    assert any(
        "does not grant permission to reuse or republish" in limitation
        for limitation in metadata["limitations"]
    )


def test_sync_source_reference_redacts_credentials_and_sensitive_query_values() -> None:
    from scorecard_pipeline.cli import _sync_source_reference

    source = (
        "https://alice:password@example.org/feeds.csv?"
        "alt=media&api_key=secret-value&token=another-secret&sig=signed-value#private"
    )
    reference = _sync_source_reference(source)

    assert reference["url_or_path"] == (
        "https://example.org/feeds.csv?alt=REDACTED&api_key=REDACTED&token=REDACTED&sig=REDACTED"
    )
    assert reference["location_redacted"] is True


def test_sync_defaults_only_proposals_to_mobility_database_v2(
    isolated_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import mobilitydb
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)
    fetched: list[str] = []

    def fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return _SYNC_PROVENANCE_CATALOG.partition(b"\n")[0] + b"\n"

    monkeypatch.setattr(mobilitydb, "fetch_catalog_bytes", fake_fetch)

    assert main(["sync"]) == 0
    assert fetched == [mobilitydb.DEFAULT_PROPOSAL_CATALOG_URL]
    assert mobilitydb.DEFAULT_PROPOSAL_CATALOG_URL == mobilitydb.MOBILITY_DATABASE_FEEDS_V2_URL
    assert mobilitydb.DEFAULT_CATALOG_URL == mobilitydb.LEGACY_MOBILITY_DATABASE_CATALOG_URL


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>upstream error</body></html>",
        b"mdb_source_id,data_type,urls.direct_download\n",
    ],
)
def test_sync_rejects_an_incompatible_or_legacy_default_catalog_response(
    isolated_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
) -> None:
    from scorecard_pipeline import mobilitydb
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)
    monkeypatch.setattr(
        mobilitydb,
        "fetch_catalog_bytes",
        lambda _url: body,
    )

    with pytest.raises(SystemExit, match="2"):
        main(["sync"])


@pytest.mark.parametrize(
    ("option", "target"),
    [
        ("--out", "catalog"),
        ("--source-metadata-out", "catalog"),
        ("--out", "registry"),
        ("--source-metadata-out", "registry"),
    ],
)
def test_sync_outputs_cannot_overwrite_catalog_or_registry(
    tmp_path: Path,
    isolated_repo_root: Path,
    option: str,
    target: str,
) -> None:
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)
    registry = isolated_repo_root / "agencies.yaml"
    catalog = tmp_path / "feeds_v2.csv"
    catalog.write_bytes(_SYNC_PROVENANCE_CATALOG)
    before_registry = registry.read_bytes()
    before_catalog = catalog.read_bytes()
    target_path = catalog if target == "catalog" else registry

    with pytest.raises(SystemExit, match="2"):
        main(["sync", "--catalog", str(catalog), option, str(target_path)])

    assert registry.read_bytes() == before_registry
    assert catalog.read_bytes() == before_catalog


def test_sync_zero_proposals_replaces_stale_output_and_binds_empty_bytes(
    tmp_path: Path,
    isolated_repo_root: Path,
) -> None:
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)
    catalog = tmp_path / "feeds_v2.csv"
    catalog.write_bytes(_SYNC_PROVENANCE_CATALOG)
    proposals = tmp_path / "proposals.yaml"
    proposals.write_text("stale: proposal\n")
    metadata_path = tmp_path / "source-metadata.json"

    assert (
        main(
            [
                "sync",
                "--catalog",
                str(catalog),
                "--provider",
                "No such provider",
                "--out",
                str(proposals),
                "--source-metadata-out",
                str(metadata_path),
            ]
        )
        == 0
    )

    assert proposals.read_bytes() == b""
    metadata = json.loads(metadata_path.read_text())
    assert metadata["proposal_count"] == 0
    assert metadata["proposal_output"]["bytes"] == 0
    assert metadata["proposal_output"]["sha256"] == hashlib.sha256(b"").hexdigest()


def test_sync_all_sidecar_excludes_transitland_metadata(
    tmp_path: Path,
    isolated_repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import transitland
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)
    catalog = tmp_path / "feeds_v2.csv"
    catalog.write_bytes(_SYNC_PROVENANCE_CATALOG)
    metadata_path = tmp_path / "source-metadata.json"
    monkeypatch.setattr(transitland, "fetch_feeds", lambda: [])

    assert (
        main(
            [
                "sync",
                "--source",
                "all",
                "--catalog",
                str(catalog),
                "--source-metadata-out",
                str(metadata_path),
            ]
        )
        == 0
    )

    metadata = json.loads(metadata_path.read_text())
    assert metadata["source"]["excluded_sources"] == ["Transitland Atlas"]
    assert metadata["proposal_output"]["scope"] == "all_sources"
    assert any(
        "Transitland Atlas source rows and per-source counts" in limitation
        for limitation in metadata["limitations"]
    )


def test_sync_rejects_source_metadata_for_transitland_only(
    tmp_path: Path,
    isolated_repo_root: Path,
) -> None:
    from scorecard_pipeline.cli import main

    _write_minimal_sync_registry(isolated_repo_root)

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "sync",
                "--source",
                "transitland",
                "--source-metadata-out",
                str(tmp_path / "metadata.json"),
            ]
        )


@pytest.mark.parametrize("duplicate_kind", ["mdb_id", "feed_url"])
def test_lint_strict_rejects_each_duplicate_canonical_identity(
    isolated_repo_root: Path,
    duplicate_kind: str,
) -> None:
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True)
    duplicate_mdb = "same" if duplicate_kind == "mdb_id" else "second"
    duplicate_url = (
        "http://first.example/feed.zip/"
        if duplicate_kind == "feed_url"
        else "https://second.example/feed.zip"
    )
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: first\n"
        "    name: First Transit\n"
        "    static_gtfs_url: https://first.example/feed.zip\n"
        "    mdb_id: same\n"
        "  - id: second\n"
        "    name: Second Transit\n"
        f"    static_gtfs_url: {duplicate_url}\n"
        f"    mdb_id: {duplicate_mdb}\n"
    )

    assert main(["lint"]) == 0
    assert main(["lint", "--strict"]) == 1


def test_ntd_crosswalk_applies_only_to_the_owning_manifest_shard(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline import ntd_crosswalk
    from scorecard_pipeline.cli import main

    first, second = _write_manifest_registry(isolated_repo_root)
    untouched = second.read_bytes()
    atlas = {
        "feeds": [
            {
                "id": "f-first",
                "urls": {"static_current": "https://old.example/first.zip"},
            }
        ],
        "operators": [
            {
                "name": "First Transit",
                "onestop_id": "o-9q-first",
                "tags": {"us_ntd_id": "90001"},
                "associated_feeds": [{"feed_onestop_id": "f-first"}],
            }
        ],
    }
    monkeypatch.setattr(ntd_crosswalk, "fetch_atlas", lambda: [atlas])

    assert main(["ntd-crosswalk", "--apply"]) == 0

    assert 'ntd_id: "90001"' in first.read_text()
    assert second.read_bytes() == untouched
