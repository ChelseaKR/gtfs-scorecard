"""Crawl hygiene: truthful agency lastmod, thin clearance logs, complete state hubs."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.render_site import (
    FIXLOG_INDEX_MIN_RECEIPTS,
    _render_fixlog_page,
    _render_rollup,
    feed_change_date,
    fixlog_is_indexable,
    state_hub_outside_members,
)

A = "a" * 64
B = "b" * 64


def _row(date: str, sha: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"date": date, "grade": "C", "score": 70.0}
    if sha is not None:
        row["feed_sha256"] = sha
    return row


# --- feed_change_date -------------------------------------------------------


def test_change_date_is_the_first_day_the_current_file_was_seen() -> None:
    history = [_row("2026-09-01", A), _row("2026-09-02", A), _row("2026-09-05", B)]
    history += [_row("2026-09-06", B), _row("2026-10-03", B)]
    assert feed_change_date(history) == "2026-09-05"


def test_change_date_ignores_input_order() -> None:
    history = [_row("2026-10-03", B), _row("2026-09-01", A), _row("2026-09-05", B)]
    assert feed_change_date(history) == "2026-09-05"


def test_unchanged_since_the_first_record_is_unknown_not_the_first_date() -> None:
    # We never saw a different file, so we cannot say when this one appeared.
    history = [_row("2026-06-16", A), _row("2026-08-01", A), _row("2026-10-03", A)]
    assert feed_change_date(history) is None


def test_missing_or_malformed_sha_never_becomes_a_change() -> None:
    # The record before the run has no readable hash: the change is not observed.
    assert feed_change_date([_row("2026-09-01", None), _row("2026-09-05", B)]) is None
    assert feed_change_date([_row("2026-09-01", "not-a-hash"), _row("2026-09-05", B)]) is None
    # The newest record has no hash: nothing is known about the current file.
    assert feed_change_date([_row("2026-09-01", A), _row("2026-09-05", None)]) is None


def test_empty_or_undated_history_is_unknown() -> None:
    assert feed_change_date(None) is None
    assert feed_change_date([]) is None
    assert feed_change_date([{"feed_sha256": A}, {"date": "yesterday", "feed_sha256": B}]) is None


def test_change_date_is_never_the_latest_run_date_when_the_file_is_unchanged() -> None:
    # Negative control for the old behavior (lastmod = snapshot date): the
    # latest check is 10-03, but the file last changed on 09-05.
    history = [_row("2026-09-01", A), _row("2026-09-05", B), _row("2026-10-03", B)]
    assert feed_change_date(history) != "2026-10-03"


# --- clearance logs ---------------------------------------------------------


def _receipts(n: int) -> list[dict[str, str]]:
    return [
        {
            "code": f"code_{i}",
            "what": f"Finding {i}.",
            "last_seen": f"2026-06-{10 + i:02d}",
            "cleared": f"2026-06-{11 + i:02d}",
        }
        for i in range(n)
    ]


ART = {"agency": {"id": "demo", "name": "Demo Transit"}}


def test_thin_clearance_log_is_noindex_follow() -> None:
    assert FIXLOG_INDEX_MIN_RECEIPTS == 3
    for n in (1, 2):
        assert not fixlog_is_indexable(_receipts(n))
        html = _render_fixlog_page(ART, _receipts(n))
        assert '<meta name="robots" content="noindex,follow">' in html


def test_substantial_clearance_log_stays_indexable() -> None:
    assert fixlog_is_indexable(_receipts(3))
    html = _render_fixlog_page(ART, _receipts(3))
    assert 'name="robots"' not in html
    assert "3 verified finding clearances" in html


# --- state hubs -------------------------------------------------------------


def _rollup(rid: str, name: str, member_ids: list[str]) -> dict[str, Any]:
    return {
        "rollup": {"id": rid, "name": name},
        "agency_count": len(member_ids),
        "average_score": None,
        "grade_distribution": {},
        "comparison": {"eligible_count": 0},
        "needs_attention": 0,
        "expired": {"lapsed": 0, "stale": 0, "total": 0},
        "shapes_readiness": {
            "ready": 0,
            "at_risk": 0,
            "not_ready": 0,
            "not_measured": len(member_ids),
            "total": len(member_ids),
        },
        "members": [
            {"id": m, "name": m.title(), "grade": "C", "score": 70.0, "snapshot_date": "2026-10-03"}
            for m in member_ids
        ],
        "common_fixes": [],
    }


DIRECTORY = [
    {"id": "member-one", "name": "Member One", "country": "US", "subdivision_name": "California"},
    {"id": "ac-transit", "name": "AC Transit", "country": "US", "subdivision_name": "California"},
    {"id": "bart", "name": "BART", "country": "US", "subdivision_name": "California"},
    {"id": "metra", "name": "Metra", "country": "US", "subdivision_name": "Illinois"},
    {"id": "nowhere", "name": "No State", "country": "US", "subdivision_name": ""},
    {"id": "tpg", "name": "TPG", "country": "CH", "subdivision_name": "California"},
]


def test_state_hub_lists_every_state_scorecard_outside_its_members() -> None:
    others = state_hub_outside_members(
        _rollup("california", "California", ["member-one"]), DIRECTORY
    )
    assert others is not None
    state, records = others
    assert state == "California"
    assert [r["id"] for r in records] == ["ac-transit", "bart"]


def test_non_state_rollups_get_no_outside_list() -> None:
    for rid in ("all", "yolo-county", "country-ch"):
        assert state_hub_outside_members(_rollup(rid, rid, []), DIRECTORY) is None


def test_hub_links_outsiders_without_counting_them() -> None:
    rollup = _rollup("california", "California agencies", ["member-one"])
    html = _render_rollup(rollup, state_hub_outside_members(rollup, DIRECTORY))
    assert 'href="/agency/ac-transit/"' in html
    assert 'href="/agency/bart/"' in html
    assert "Other California feed scorecards" in html
    assert "not counted in any figure" in html
    # The rollup's own figures are untouched.
    assert "<strong>1 feed scorecards</strong>" in html
    assert 'href="/agency/metra/"' not in html


def test_hub_without_outsiders_renders_no_section() -> None:
    rollup = _rollup("illinois", "Illinois agencies", ["metra"])
    html = _render_rollup(rollup, state_hub_outside_members(rollup, DIRECTORY))
    assert "Other Illinois feed scorecards" not in html
    assert _render_rollup(rollup) == html
