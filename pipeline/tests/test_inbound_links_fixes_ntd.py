"""Inbound links to the page classes Google has been slow to crawl.

The /agencies/ listing links each indexable clearance log (/agency/<id>/fixes/),
and a state's /program/<state>/ page links that state's /ntd/states/<state>/
page. The links follow the sitemap: a thin (noindex) log and a state without an
NTD page get none. Each check has a negative control that asserts its sabotage
was applied before asserting the check notices it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scorecard_pipeline.render_site import (
    _AGENCY_INDEX_PAGE_SIZE,
    _render_agency_index,
    _render_rollup,
    _write_program_pages,
)

ROOT = Path(__file__).resolve().parents[2]


def _index(count: int) -> dict[str, Any]:
    return {
        "agencies": {
            f"agency-{n:03d}": {
                "name": f"Agency {n:03d}",
                "history": [
                    {"grade": "B", "score": 82.0, "date": "2026-07-28", "days_until_expiry": 30}
                ],
            }
            for n in range(count)
        }
    }


def _linked_logs(pages: list[str]) -> list[str]:
    return [i for html in pages for i in re.findall(r'href="/agency/([^/"]+)/fixes/"', html)]


def _render_pages(index: dict[str, Any], fixlog_ids: frozenset[str]) -> list[str]:
    count = len(index["agencies"])
    return [
        _render_agency_index(index, {}, page=page, page_size=3, fixlog_ids=fixlog_ids)
        for page in range(1, -(-count // 3) + 1)
    ]


WITH_LOGS = frozenset({"agency-001", "agency-004", "agency-006"})


def test_listing_links_exactly_the_agencies_with_an_indexable_log() -> None:
    pages = _render_pages(_index(7), WITH_LOGS)
    assert sorted(_linked_logs(pages)) == sorted(WITH_LOGS)
    assert len(_linked_logs(pages)) == len(WITH_LOGS)  # once each, no duplicates


def test_control_without_the_links_the_check_fails() -> None:
    # Sabotage: render the listing as it was before this change.
    sabotaged = _render_pages(_index(7), frozenset())
    assert not any("/fixes/" in html for html in sabotaged)  # the sabotage applied
    assert sorted(_linked_logs(sabotaged)) != sorted(WITH_LOGS)  # so the check above fails


def test_a_log_link_names_its_agency_for_screen_readers() -> None:
    html = _render_pages(_index(3), frozenset({"agency-001"}))[0]
    assert (
        '<a href="/agency/agency-001/fixes/">Clearance log'
        '<span class="visually-hidden"> for Agency 001</span></a>'
    ) in html


def test_listing_page_with_every_link_stays_inside_its_byte_budget() -> None:
    budgets = json.loads((ROOT / "site-budgets.json").read_text())
    index = _index(_AGENCY_INDEX_PAGE_SIZE)
    html = _render_agency_index(index, {}, page=1, fixlog_ids=frozenset(index["agencies"]))
    assert html.count("/fixes/") == _AGENCY_INDEX_PAGE_SIZE  # worst case: all linked
    limit = budgets["required"]["agencies/index.html"]
    assert len(html.encode()) < limit, (len(html.encode()), limit)


# --- program page -> NTD state page ---------------------------------------


def _rollup(rid: str, name: str) -> dict[str, Any]:
    return {
        "rollup": {"id": rid, "name": name},
        "agency_count": 1,
        "average_score": None,
        "grade_distribution": {},
        "comparison": {"eligible_count": 0},
        "needs_attention": 0,
        "expired": {"lapsed": 0, "stale": 0, "total": 0},
        "shapes_readiness": {
            "ready": 0,
            "at_risk": 0,
            "not_ready": 0,
            "not_measured": 1,
            "total": 1,
        },
        "members": [
            {"id": "m", "name": "M", "grade": "C", "score": 70.0, "snapshot_date": "2026-10-03"}
        ],
        "common_fixes": [],
    }


def test_rollup_page_links_its_states_ntd_page() -> None:
    link = ("Ohio", "/ntd/states/ohio/")
    html = _render_rollup(_rollup("ohio", "Ohio agencies"), None, None, link)
    assert 'href="/ntd/states/ohio/"' in html
    assert "Ohio transit feeds and the NTD shapes.txt requirement" in html
    assert 'href="/ntd/states/' not in _render_rollup(_rollup("ohio", "Ohio agencies"))


def _write_rollups(art: Path, ids: dict[str, str]) -> None:
    (art / "rollups").mkdir(parents=True)
    (art / "rollups" / "index.json").write_text(
        json.dumps({"rollups": [{"id": rid} for rid in ids]})
    )
    for rid, name in ids.items():
        (art / "rollups" / f"{rid}.json").write_text(json.dumps(_rollup(rid, name)))


def _program_pages(art: Path, links: dict[str, str]) -> dict[str, str]:
    written: dict[str, str] = {}

    def write(rel: str, content: str, url: str | None = None, **_: Any) -> None:
        written[rel] = content

    _write_rollups(art, {"ohio": "Ohio agencies", "vermont": "Vermont agencies", "all": "All"})
    _write_program_pages(art, write, [], None, links)
    return written


def test_only_state_rollups_with_an_ntd_page_link_it(tmp_path: Path) -> None:
    pages = _program_pages(tmp_path, {"Ohio": "/ntd/states/ohio/"})
    assert 'href="/ntd/states/ohio/"' in pages["program/ohio/index.html"]
    # Vermont has no NTD page, and "all" is not a state: no link, no dangling target.
    assert "/ntd/states/" not in pages["program/vermont/index.html"]
    assert "/ntd/states/" not in pages["program/all/index.html"]


def test_control_with_no_ntd_pages_no_program_page_links_one(tmp_path: Path) -> None:
    pages = _program_pages(tmp_path, {})
    assert pages["program/ohio/index.html"]  # the page rendered
    assert not any("/ntd/states/" in html for html in pages.values())
