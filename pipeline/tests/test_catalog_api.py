"""The weekly catalog update reads the Mobility Database API only (ADR 0070)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline import catalog_api as api
from scorecard_pipeline.agencies import parse_agencies
from scorecard_pipeline.catalog_api import (
    CatalogPausedError,
    catalog_feeds_from_api,
    load_api_catalog,
)
from scorecard_pipeline.mobilitydb import find_supersessions

ROWS: list[dict[str, Any]] = [
    {
        "id": "mdb-10",
        "data_type": "gtfs",
        "status": "deprecated",
        "official": True,
        "provider": "Athens Transit",
        "feed_name": "",
        "source_info": {
            "producer_url": "https://old.example/athens.zip",
            "authentication_type": 0,
            "license_url": "",
        },
        "locations": [{"country_code": "us", "subdivision_name": "Georgia"}],
        "redirects": [{"target_id": "mdb-11", "comment": ""}],
    },
    {
        "id": "mdb-11",
        "data_type": "gtfs",
        "status": "active",
        "official": "true",
        "provider": "Athens Transit",
        "feed_name": "Athens Transit",
        "source_info": {
            "producer_url": "https://athens.example/gtfs.zip",
            "authentication_type": 0,
            "license_url": "https://athens.example/terms",
        },
        "locations": [{"country_code": "US", "subdivision_name": "Georgia"}],
        "redirects": [],
        "latest_dataset": {"hosted_url": "https://files.mobilitydatabase.org/mdb-11/x.zip"},
    },
    {"id": "mdb-12", "data_type": "gtfs_rt", "provider": "RT only"},
]


def test_api_rows_map_onto_catalog_feeds() -> None:
    old, new = catalog_feeds_from_api(ROWS)
    assert (old.mdb_id, old.status, old.redirect_ids, old.is_official) == (
        "mdb-10",
        "deprecated",
        ("mdb-11",),
        True,
    )
    assert old.country == "US"
    assert (new.direct_download, new.license_url, new.authentication_type) == (
        "https://athens.example/gtfs.zip",
        "https://athens.example/terms",
        "0",
    )
    assert new.is_official is True
    assert [f.source_record_number for f in (old, new)] == [1, 2]


def test_api_rows_drive_the_existing_supersession_check() -> None:
    agencies = parse_agencies(
        {
            "agencies": [
                {
                    "id": "athens",
                    "name": "Athens Transit",
                    "static_gtfs_url": "https://old.example/athens.zip",
                    "mdb_id": "10",
                },
                {
                    "id": "athens-11",
                    "name": "Athens Transit",
                    "static_gtfs_url": "https://athens.example/gtfs.zip",
                    "mdb_id": "11",
                },
            ]
        }
    )
    superseded, _ = find_supersessions(catalog_feeds_from_api(ROWS), agencies)
    assert [(s.agency_id, s.successor_agency_id) for s in superseded] == [("athens", "athens-11")]


def test_without_a_token_nothing_is_requested() -> None:
    calls: list[str] = []

    def post(url: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
        calls.append(url)
        return {"access_token": "a"}

    def get(url: str, headers: Mapping[str, str]) -> Any:
        calls.append(url)
        return []

    with pytest.raises(CatalogPausedError, match="paused"):
        load_api_catalog(environ={}, post=post, get=get)
    with pytest.raises(CatalogPausedError):
        load_api_catalog(environ={"MOBILITY_FEED_API_TOKEN": "  "}, post=post, get=get)
    assert calls == []

    # Negative control: the same callables with a token make the two calls.
    load_api_catalog(environ={"MOBILITY_FEED_API_TOKEN": "refresh"}, post=post, get=get)
    assert calls[0].endswith("/v1/tokens")
    assert "/v1/gtfs_feeds?" in calls[1]


def test_token_exchange_and_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "PAGE_SIZE", 2)
    seen: list[tuple[str, dict[str, str]]] = []
    exchanged: list[Mapping[str, Any]] = []

    def post(url: str, payload: Mapping[str, Any], headers: Mapping[str, str]) -> Any:
        exchanged.append(payload)
        assert "Mozilla" not in headers["User-Agent"]
        return {"access_token": "short-lived"}

    pages = [ROWS[:2], ROWS[2:]]

    def get(url: str, headers: Mapping[str, str]) -> Any:
        seen.append((url, dict(headers)))
        return pages[len(seen) - 1]

    feeds = load_api_catalog(environ={"MOBILITY_FEED_API_TOKEN": "refresh"}, post=post, get=get)
    assert exchanged == [{"refresh_token": "refresh"}]
    assert [url.split("?")[1] for url, _ in seen] == ["limit=2&offset=0", "limit=2&offset=2"]
    assert all(h["Authorization"] == "Bearer short-lived" for _, h in seen)
    assert [f.mdb_id for f in feeds] == ["mdb-10", "mdb-11"]


def test_a_missing_access_token_or_a_bad_page_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="no access token"):
        api.access_token("r", post=lambda *a: {})
    with pytest.raises(RuntimeError, match="non-list"):
        api.fetch_gtfs_feeds("t", get=lambda *a: {"error": "x"})


def test_the_weekly_commands_pause_without_a_token(
    tmp_path: Path, isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline.cli import CATALOG_PAUSED_EXIT, main

    monkeypatch.delenv("MOBILITY_FEED_API_TOKEN", raising=False)
    shard = isolated_repo_root / "registry" / "a.yaml"
    shard.parent.mkdir(parents=True)
    shard.write_text(
        yaml.safe_dump(
            {
                "agencies": [
                    {
                        "id": "a",
                        "name": "A",
                        "static_gtfs_url": "https://a.example/g.zip",
                        "mdb_id": "1",
                    }
                ]
            }
        )
    )
    (isolated_repo_root / "registry" / "index.yaml").write_text("shards:\n  - registry/a.yaml\n")
    before = shard.read_bytes()

    def no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("no request may be made while paused")

    monkeypatch.setattr(api, "_default_post", no_network)
    monkeypatch.setattr(api, "_default_get", no_network)

    assert main(["supersessions", "--catalog", "api", "--apply"]) == CATALOG_PAUSED_EXIT
    assert main(["discover", "--catalog", "api", "--apply"]) == CATALOG_PAUSED_EXIT
    assert shard.read_bytes() == before
