"""Redirects for the scorecard URLs the 2026-07-11 registry dedupe removed.

Search Console listed 401 agency URLs with impressions that answer 404 today;
336 of them are pages of records the dedupe (#69) dropped as http/https twins
of a kept record. These tests hold the file that records those pairs and the
renderer's resolution of each one to a live scorecard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline.config import Agency
from scorecard_pipeline.removed_twins import (
    REMOVED_TWINS_FILENAME,
    RemovedTwin,
    read_removed_twins,
)
from scorecard_pipeline.render_site import _removed_twin_redirects

_REPO = Path(__file__).resolve().parents[2]


def _agency(agency_id: str, alias_of: str = "") -> Agency:
    return Agency(
        agency_id, agency_id.title(), f"https://example.test/{agency_id}.zip", alias_of=alias_of
    )


def test_committed_file_lists_the_dedupes_320_twins() -> None:
    twins = read_removed_twins(_REPO)
    assert len(twins) == 320
    by_id = {twin.id: twin.kept for twin in twins}
    # The page with the most impressions among the 404s Search Console reported.
    assert by_id["metro-ride-830"] == "metro-ride"
    assert by_id["capital-area-transit-goraleigh-471"] == "capital-area-transit-goraleigh"


def test_twin_redirects_to_its_published_kept_record() -> None:
    registry = {"metro-ride": _agency("metro-ride")}
    redirects = _removed_twin_redirects(
        registry, {"metro-ride"}, [RemovedTwin("metro-ride-830", "metro-ride")]
    )
    assert redirects == {"metro-ride-830": "metro-ride"}


def test_twin_follows_the_kept_records_later_alias() -> None:
    # The kept record was itself later retired in favor of an MDB-suffixed id.
    registry = {
        "goraleigh": _agency("goraleigh", alias_of="goraleigh-2074"),
        "goraleigh-2074": _agency("goraleigh-2074"),
    }
    redirects = _removed_twin_redirects(
        registry, {"goraleigh-2074"}, [RemovedTwin("goraleigh-471", "goraleigh")]
    )
    assert redirects == {"goraleigh-471": "goraleigh-2074"}


def test_no_redirect_when_the_successor_is_not_published() -> None:
    # Negative control: the same twin, with its successor delisted, must not
    # redirect at all. A redirect to a page that is gone only moves the 404.
    registry = {"metro-ride": _agency("metro-ride")}
    twins = [RemovedTwin("metro-ride-830", "metro-ride")]
    assert _removed_twin_redirects(registry, set(), twins) == {}
    assert _removed_twin_redirects(registry, {"metro-ride"}, twins) != {}


def test_an_id_back_in_the_registry_keeps_its_own_url() -> None:
    registry = {
        "metro-ride": _agency("metro-ride"),
        "metro-ride-830": _agency("metro-ride-830"),
    }
    redirects = _removed_twin_redirects(
        registry, {"metro-ride", "metro-ride-830"}, [RemovedTwin("metro-ride-830", "metro-ride")]
    )
    assert redirects == {}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("twins: []\n", "schema_version"),
        ("schema_version: 1\ntwins: {}\n", "must be a list"),
        ("schema_version: 1\ntwins:\n  - {id: a-1}\n", "exactly 'id' and 'kept'"),
        ("schema_version: 1\ntwins:\n  - {id: a, kept: a}\n", "cannot name itself"),
        ("schema_version: 1\ntwins:\n  - {id: A_1, kept: a}\n", "lowercase slugs"),
        (
            "schema_version: 1\ntwins:\n  - {id: a-1, kept: a}\n  - {id: a-1, kept: b}\n",
            "repeats id",
        ),
    ],
)
def test_malformed_file_fails_loudly(tmp_path: Path, body: str, message: str) -> None:
    (tmp_path / REMOVED_TWINS_FILENAME).write_text(body)
    with pytest.raises(ValueError, match=message):
        read_removed_twins(tmp_path)


def test_missing_file_means_nothing_to_redirect(tmp_path: Path) -> None:
    assert read_removed_twins(tmp_path) == []


def test_render_writes_the_redirect_and_lists_it_but_not_in_the_sitemap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime as dt
    import json
    import shutil

    fixture = Path(__file__).parent / "fixtures" / "golden_site"
    root = tmp_path / "golden_site"
    shutil.copytree(fixture, root)
    (root / REMOVED_TWINS_FILENAME).write_text(
        "schema_version: 1\n"
        "twins:\n"
        "  - {id: unitrans-351, kept: unitrans}\n"
        "  - {id: gone-999, kept: no-such-record}\n"
    )
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    from scorecard_pipeline.render_site import render_site

    render_site(now=dt.datetime(2026, 7, 3, tzinfo=dt.UTC))
    web = root / "web"

    stub = (web / "agency" / "unitrans-351" / "index.html").read_text()
    assert 'http-equiv="refresh" content="0; url=/agency/unitrans/"' in stub
    assert '<link rel="canonical" href="https://gtfsscorecard.org/agency/unitrans/">' in stub
    redirects = json.loads((web / "_meta" / "retained-agency-redirects.json").read_text())
    assert redirects["redirects"]["/agency/unitrans-351/"] == "/agency/unitrans/"
    # No successor, no page: a removed id with nothing to point at stays gone.
    assert not (web / "agency" / "gone-999").exists()
    assert "/agency/gone-999/" not in redirects["redirects"]
    sitemap = (web / "sitemap.xml").read_text()
    assert "/agency/unitrans-351/" not in sitemap
    assert "<loc>https://gtfsscorecard.org/agency/unitrans/</loc>" in sitemap
