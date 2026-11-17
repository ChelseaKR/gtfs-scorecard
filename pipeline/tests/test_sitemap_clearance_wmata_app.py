"""ADR 0080: clearance logs in the sitemap, the two WMATA feeds, and /app/'s canonical.

* The sitemap lists a clearance log only when it is indexable and earned a
  search impression. A log left out stays indexable: this is never a noindex.
* The two WMATA records are WMATA's bus feed and its rail feed, not one feed
  twice, so neither is retired. Their titles say which is which.
* /app/ names itself as canonical, which is what Google already chose.
"""

from __future__ import annotations

import importlib.util
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    CLEARANCE_SITEMAP_LIST,
    fixlog_in_sitemap,
    load_clearance_sitemap_ids,
)

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "pipeline" / "scripts" / "clearance_log_sitemap_list.py"
_WMATA_BUS = "washington-metropolitan-area-transit-authority-wmata"
_WMATA_RAIL = "washington-metropolitan-area-transit-authority-wmata-1847"


def _receipts(n: int) -> list[dict[str, str]]:
    return [
        {"code": f"c{i}", "what": "x", "last_seen": "2026-06-10", "cleared": "2026-06-11"}
        for i in range(n)
    ]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("clearance_log_sitemap_list", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- which clearance logs the sitemap lists --------------------------------


def test_only_an_indexable_log_with_an_impression_is_listed() -> None:
    listed = frozenset({"seen"})
    assert fixlog_in_sitemap("seen", _receipts(3), listed)
    assert not fixlog_in_sitemap("unseen", _receipts(3), listed)
    # A thin log is noindex, so an impression never lists it.
    assert not fixlog_in_sitemap("seen", _receipts(2), listed)


def test_without_a_list_every_indexable_log_is_listed_as_before() -> None:
    assert fixlog_in_sitemap("any", _receipts(3), None)
    assert not fixlog_in_sitemap("any", _receipts(1), None)


def test_list_loading_fails_open_to_the_old_rule(tmp_path: Path) -> None:
    assert load_clearance_sitemap_ids(tmp_path) is None  # no file
    path = tmp_path / CLEARANCE_SITEMAP_LIST
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert load_clearance_sitemap_ids(tmp_path) is None
    path.write_text(json.dumps({"agency_ids": "metra"}))
    assert load_clearance_sitemap_ids(tmp_path) is None
    path.write_text(json.dumps({"agency_ids": ["metra", "caltrain"]}))
    assert load_clearance_sitemap_ids(tmp_path) == frozenset({"metra", "caltrain"})


def test_the_committed_list_is_the_search_console_export() -> None:
    data = json.loads((_REPO / CLEARANCE_SITEMAP_LIST).read_text())
    ids = data["agency_ids"]
    assert data["window_start"] == "2026-08-18" and data["window_end"] == "2026-11-15"
    assert ids == sorted(set(ids))
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9-]*", i) for i in ids)
    # 384 logs had an impression in the 90 days; about 359 of them are in
    # today's sitemap, the rest have since gone thin or been retired.
    assert len(ids) == 384


def test_the_list_script_counts_only_clean_log_urls_with_impressions() -> None:
    export = {
        "start": "2026-08-18",
        "end": "2026-11-15",
        "rows": [
            {"keys": ["https://gtfsscorecard.org/agency/metra/fixes/"], "impressions": 4},
            {"keys": ["https://gtfsscorecard.org/agency/metra/"], "impressions": 90},
            {"keys": ["https://gtfsscorecard.org/agency/go/fixes/?finding=x"], "impressions": 2},
            {"keys": ["https://gtfsscorecard.org/agency/zero/fixes/"], "impressions": 0},
            {"keys": ["https://gtfsscorecard.org/agency/amtrak/fixes/"], "impressions": 1},
            {"keys": []},
        ],
    }
    script = _script()
    assert script.clearance_log_ids(export) == ["amtrak", "metra"]
    payload = script.build(export, "2026-11-17")
    assert payload["agency_ids"] == ["amtrak", "metra"]
    with pytest.raises(ValueError, match="pulled"):
        script.build(export, "yesterday")


# --- WMATA ------------------------------------------------------------------


def _registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from scorecard_pipeline.agencies import read_agencies

    monkeypatch.setenv("SCORECARD_ROOT", str(_REPO))
    return {agency.id: agency for agency in read_agencies()}


def test_the_two_wmata_records_are_two_feeds_told_apart_by_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(monkeypatch)
    bus, rail = registry[_WMATA_BUS], registry[_WMATA_RAIL]
    # Not a duplicate: different feed files and different Mobility Database
    # feeds, so retiring one would drop a real scorecard.
    assert bus.static_gtfs_url != rail.static_gtfs_url
    assert bus.mdb_id != rail.mdb_id
    assert (bus.feed_variant, rail.feed_variant) == ("Bus", "Rail")
    removed = (_REPO / "removed-duplicate-ids.yaml").read_text()
    assert _WMATA_BUS not in removed and _WMATA_RAIL not in removed


def test_wmata_titles_say_bus_and_rail(monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline.render_site import _plan_agency_seo_metadata

    registry = _registry(monkeypatch)
    records = [
        {
            "id": agency_id,
            "name": registry[agency_id].name,
            "subdivision_name": "District of Columbia",
            "country": "US",
        }
        for agency_id in (_WMATA_BUS, _WMATA_RAIL)
    ]
    artifacts = {
        r["id"]: {
            "overall": {"grade": "D", "score": 68.0},
            "snapshot_date": "2026-08-07",
            "categories": {"realtime": {"status": "not_yet_measured"}},
        }
        for r in records
    }
    planned = _plan_agency_seo_metadata(records, artifacts, registry)
    assert "[Bus]" in planned[_WMATA_BUS].title
    assert "[Rail]" in planned[_WMATA_RAIL].title
    assert "MDB" not in planned[_WMATA_BUS].title + planned[_WMATA_RAIL].title


# --- /app/ ------------------------------------------------------------------


class _AppShell(HTMLParser):
    """The app shell's canonical, og:url and h1s, and which h1s sit in <noscript>."""

    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.og_urls: list[str] = []
        self.h1_in_noscript: list[bool] = []
        self.noscript_links: list[str] = []
        self._noscript = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "noscript":
            self._noscript += 1
        elif tag == "link" and attr.get("rel") == "canonical":
            self.canonicals.append(str(attr.get("href")))
        elif tag == "meta" and attr.get("property") == "og:url":
            self.og_urls.append(str(attr.get("content")))
        elif tag == "h1":
            self.h1_in_noscript.append(self._noscript > 0)
        elif tag == "a" and self._noscript:
            self.noscript_links.append(str(attr.get("href")))

    def handle_endtag(self, tag: str) -> None:
        if tag == "noscript":
            self._noscript -= 1


def test_app_names_itself_as_canonical() -> None:
    shell = _AppShell()
    shell.feed((_REPO / "web" / "app" / "index.html").read_text())
    assert shell.canonicals == ["https://gtfsscorecard.org/app/"]
    assert shell.og_urls == ["https://gtfsscorecard.org/app/"]
    # An indexable page needs one h1. It sits in <noscript>, beside the link
    # to the static directory: with JavaScript the app renders its own, and
    # the e2e tests wait on "#main h1" to know the app has rendered, so a
    # static one outside <noscript> would end those waits early.
    assert shell.h1_in_noscript == [True]
    assert "/agencies/" in shell.noscript_links
    config = json.loads((_REPO / "site-seo.json").read_text())
    assert "/app/" not in config["canonical_aliases"]
