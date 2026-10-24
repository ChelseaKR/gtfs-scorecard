"""The reporter counts reach /ntd/, in reporter units, or not at all.

#278. `/ntd/` answers "45.0% of 1,125 tracked feeds look ready to certify", and
says so plainly: the denominator is this project's registry. The question an FTA
reviewer or a Caltrans district liaison asks first is the other one, which
reporters obligated to publish GTFS have nothing discoverable at all, and that
population was unreachable from a feed-outward join.

`ntd_coverage.py` and the committed RY2024 snapshot answered it on 2026-08-15,
and `data/ntd/PROVENANCE.md` then said in as many words that nothing read them:
"Neither is read by the pipeline, the site, or the public API." These tests pin
the publication and the three guardrails the issue attaches to it.

The reconciliation guard is the load-bearing one. Reporter counts and feed-record
counts are different units, so a snapshot that does not declare its unit, or
whose tiers do not sum to its own denominator, publishes nothing at all rather
than a number a reader would take for the real denominator.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.ntd_coverage import (
    ABSENCE_CAVEAT,
    FTA_LINK_CAVEAT,
    NO_LINK_NO_MATCH_LABEL,
    RANGE_CAVEAT,
    REPORTER_UNIT,
    SNAPSHOT_NAME,
    TIER_ORDER,
    WEBLINK_TIER,
    published_reporter_coverage,
    rebase_snapshot,
    snapshot_path,
    weblink_ntd_ids,
)
from scorecard_pipeline.render_site import _render_ntd_page

# The committed snapshot, by repository path. The autouse `isolated_repo_root`
# fixture points SCORECARD_ROOT at a throwaway directory, which is what
# `snapshot_path()` reads, so these tests name the real file explicitly.
COMMITTED = Path(__file__).resolve().parents[2] / "data" / "ntd" / SNAPSHOT_NAME


def _snapshot() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(COMMITTED.read_text(encoding="utf-8"))
    return payload


def _coverage() -> dict[str, Any] | None:
    return published_reporter_coverage(COMMITTED)


def test_snapshot_path_points_at_the_committed_file() -> None:
    """The default the renderer uses resolves to the file these tests read."""
    assert snapshot_path().parts[-3:] == ("data", "ntd", SNAPSHOT_NAME)


def _written(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_committed_snapshot_reconciles_and_publishes() -> None:
    coverage = _coverage()
    assert coverage is not None
    assert coverage["unit"] == REPORTER_UNIT
    assert coverage["obligated_reporters"] == 1253
    assert coverage["tracked_by_registry"] == 573
    assert coverage["discoverable_elsewhere"] == 39
    # With FTA's GTFS-link table read: 593 reporters tell FTA where their feed is.
    assert coverage["fta_links_read"] is True
    assert coverage["fta_link_reported"] == 593
    assert coverage["no_discoverable_feed_low"] == 35
    assert coverage["no_discoverable_feed_high"] == 48
    assert coverage["needs_human_review"] == 13


def test_the_tiers_sum_to_the_stated_population() -> None:
    coverage = _coverage()
    assert coverage is not None
    assert sum(coverage["by_tier"].values()) == coverage["obligated_reporters"]


def test_a_snapshot_that_does_not_declare_reporter_units_publishes_nothing(
    tmp_path: Path,
) -> None:
    """A feed-record count must never render under a reporter label."""
    payload = {**_snapshot(), "unit": "feed_records"}
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_a_snapshot_whose_tiers_do_not_reconcile_publishes_nothing(tmp_path: Path) -> None:
    payload = _snapshot()
    payload["by_tier"] = {
        **payload["by_tier"],
        "no_candidate": payload["by_tier"]["no_candidate"] + 1,
    }
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


@pytest.mark.parametrize("dropped", TIER_ORDER)
def test_a_snapshot_missing_a_tier_publishes_nothing(tmp_path: Path, dropped: str) -> None:
    """The tier-set guard, isolated so that only it can produce the verdict.

    The first version of this dropped `atlas_ntd_id` and left the denominator
    alone. That count is 33, so the sum stopped reconciling and the *next*
    guard returned None first: deleting the tier-set comparison outright left
    this test green. It was asserting the reconciliation guard twice and the
    tier-set guard never.

    Each case here subtracts the dropped tier's own count from
    `obligated_reporters`, so the remaining tiers sum to their denominator by
    construction and the reconciliation guard cannot fire. Every tier is
    covered rather than one named by hand, so this does not quietly weaken
    again if the tier it happened to name changes count. Without the tier-set
    guard, a dropped zero-count tier reaches the tier lookups below it and
    raises `KeyError` out of `_render_ntd_page`, which is a site render that
    dies instead of a page that says nothing.
    """
    payload = _snapshot()
    removed = payload["by_tier"][dropped]
    payload["by_tier"] = {k: v for k, v in payload["by_tier"].items() if k != dropped}
    payload["obligated_reporters"] -= removed
    assert sum(payload["by_tier"].values()) == payload["obligated_reporters"]
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(obligated_reporters="1,253"),
        lambda p: p.update(obligated_reporters=True),
        lambda p: p.update(by_tier=["not", "a", "mapping"]),
        lambda p: p["by_tier"].update(no_candidate="many"),
    ],
)
def test_a_malformed_snapshot_publishes_nothing(tmp_path: Path, mutate: Any) -> None:
    payload = _snapshot()
    mutate(payload)
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_an_absent_or_unreadable_snapshot_publishes_nothing(tmp_path: Path) -> None:
    assert published_reporter_coverage(tmp_path / "nothing.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert published_reporter_coverage(broken) is None


def _page(coverage: dict[str, Any] | None) -> str:
    payload: dict[str, Any] = {
        "total": 1125,
        "ready": 506,
        "at_risk": 140,
        "not_ready": 479,
        "pct_ready": 45.0,
        "by_state": {},
        "one_fix_from_ready": [],
        "one_fix_total": 0,
    }
    if coverage is not None:
        payload["reporter_coverage"] = coverage
    return _render_ntd_page(payload)


def test_the_page_states_all_three_reporter_counts_with_their_denominator() -> None:
    html = _page(_coverage())
    assert 'id="reporters"' in html
    assert "1,253 NTD reporters" in html
    assert "between <strong>35 and\n      48</strong>" in html.replace("\r", "")
    for count in ("573", "39", "593", "13"):
        assert f"<td>{count}</td>" in html


def test_the_page_keeps_the_tracked_feed_measurement_unchanged() -> None:
    """The existing 45.0%-of-1,125 line is a different, honest measurement."""
    html = _page(_coverage())
    assert "45.0% of 1125 tracked feeds" in html


def test_the_page_says_the_two_denominators_are_different_units() -> None:
    html = _page(_coverage())
    assert "These are counts of NTD reporters." in html
    assert "is a different denominator from the tracked-feed" in html
    assert "The two are never\n      added." in html.replace("\r", "")


def test_a_reporter_with_no_feed_is_a_measurement_limit_not_a_finding() -> None:
    """The neutral-treatment rule, with more force: the fix may not be theirs."""
    html = _page(_coverage())
    flat = " ".join(html.split())
    assert f"{ABSENCE_CAVEAT}, and the fix may belong to FTA's own crosswalk" in flat


def test_the_page_publishes_nothing_about_reporters_without_a_snapshot() -> None:
    html = _page(None)
    assert 'id="reporters"' not in html
    assert "Reporters, not feeds" not in html
    assert "These are counts of NTD reporters." not in html
    # And the feed-side page is otherwise unchanged.
    assert "45.0% of 1125 tracked feeds" in html


# --- the section dates its own denominator, or it does not render ------------


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("report_year"), id="no report year"),
        pytest.param(lambda p: p.update(report_year=""), id="blank report year"),
        pytest.param(lambda p: p.update(report_year="   "), id="whitespace report year"),
        pytest.param(lambda p: p.pop("retrieved_utc"), id="no retrieval date"),
        pytest.param(lambda p: p.update(retrieved_utc=""), id="blank retrieval date"),
        pytest.param(lambda p: p.update(retrieved_utc="2026"), id="truncated retrieval date"),
    ],
)
def test_a_snapshot_that_cannot_date_itself_publishes_nothing(tmp_path: Path, mutate: Any) -> None:
    """A reconciling tier set is not enough to publish.

    The section's own fine print reads "Report Year {year}, retrieved {date}",
    and that sentence is how a reader judges whether the 1,253 is current. With
    the field missing it rendered "Report Year , retrieved " -- a provenance
    claim with nothing behind it, printed beside counts that are real. The
    counts would still reconcile, which is exactly why this needs its own guard.
    """
    payload = _snapshot()
    mutate(payload)
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_the_committed_snapshot_dates_itself() -> None:
    """The guard above is only safe if the real snapshot clears it."""
    coverage = _coverage()
    assert coverage is not None
    assert coverage["report_year"] == "2024"
    assert coverage["retrieved_utc"].startswith("2026-08-15")


# --- FTA's NTD GTFS weblinks table, the fifth source --------------------------

WEBLINKS = COMMITTED.parent / "ntd-gtfs-weblinks-2026-10-23.csv"
COMMITTED_CSV = COMMITTED.with_suffix(".csv")

# The tier counts the three catalogs gave on the 2026-08-15 snapshot, before the
# FTA link table was read. Held as literals so reading a new source cannot move
# any of them without this test saying so.
BEFORE = {
    "registry_ntd_id": 63,
    "registry_name_exact": 423,
    "registry_domain": 50,
    "registry_name_fuzzy": 37,
    "atlas_ntd_id": 33,
    "catalog_name_exact": 5,
    "catalog_domain": 1,
    "catalog_name_fuzzy": 0,
    "weak_shared_token": 168,
    "no_candidate": 473,
}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def test_the_link_tier_is_last_among_strong_tiers_and_new() -> None:
    assert WEBLINK_TIER == "ntd_weblink_ntd_id"
    order = list(TIER_ORDER)
    assert order[-3:] == [WEBLINK_TIER, "weak_shared_token", "no_candidate"]
    assert order.index(WEBLINK_TIER) == order.index("catalog_name_fuzzy") + 1


def test_reading_the_link_table_moves_no_existing_tier_count() -> None:
    """Golden before and after: only the two unmatched tiers drain."""
    by_tier = _snapshot()["by_tier"]
    for tier, before in BEFORE.items():
        if tier not in ("weak_shared_token", "no_candidate"):
            assert by_tier[tier] == before, tier
    assert by_tier[WEBLINK_TIER] == 593
    drained = (BEFORE["weak_shared_token"] - by_tier["weak_shared_token"]) + (
        BEFORE["no_candidate"] - by_tier["no_candidate"]
    )
    assert drained == 593 == 438 + 155
    assert by_tier["no_candidate"] == 35
    assert by_tier["weak_shared_token"] == 13


def test_the_new_tier_yields_593_from_the_committed_table_itself() -> None:
    """Recomputed from the committed table, not read back from the snapshot."""
    rows = _csv_rows(COMMITTED_CSV)
    rebased, snap = rebase_snapshot(rows, _snapshot(), _csv_rows(WEBLINKS))
    assert sum(1 for r in rebased if r["match_tier"] == WEBLINK_TIER) == 593
    assert snap["by_tier"] == _snapshot()["by_tier"]


def test_the_stored_table_matches_its_recorded_sha256_and_counts() -> None:
    meta = _snapshot()["fta_weblinks"]
    assert hashlib.sha256(WEBLINKS.read_bytes()).hexdigest() == meta["sha256"]
    table = _csv_rows(WEBLINKS)
    assert (meta["rows"], meta["distinct_ntd_ids"], meta["ntd_ids_with_a_link"]) == (
        len(table),
        1209,
        1193,
    )
    assert len(weblink_ntd_ids(table)) == 1193


def test_without_the_table_the_range_is_the_old_one_and_the_page_says_so() -> None:
    """Negative control: the sabotage must visibly apply.

    Withdrawing the table has to change the numbers (so the control cannot pass
    vacuously), put every tier back to the pre-link golden, and make the page
    say the source was not read instead of silently printing the old range.
    """
    with_table = _coverage()
    assert with_table is not None and with_table["no_discoverable_feed_low"] == 35
    rows = _csv_rows(COMMITTED_CSV)
    _, snap = rebase_snapshot(rows, _snapshot(), None)
    assert snap["fta_weblinks"] == {"read": False}
    assert snap["by_tier"] == {**BEFORE, WEBLINK_TIER: 0}
    assert not any(s["name"].startswith("FTA NTD GTFS weblinks") for s in snap["sources"])
    # And it must round-trip through the publisher and the renderer.
    without = published_reporter_coverage(_write(snap))
    assert without is not None
    assert without["fta_links_read"] is False
    assert (without["no_discoverable_feed_low"], without["no_discoverable_feed_high"]) == (473, 641)
    html = " ".join(_page(without).split())
    assert "between <strong>473 and 641</strong>" in html
    assert "were not read for this snapshot" in html
    assert FTA_LINK_CAVEAT not in html
    assert "GTFS link reported to FTA, not matched to a catalog" not in html
    assert "No candidate in the three catalogs read" in html


def _write(payload: dict[str, Any]) -> Path:
    import tempfile

    path = Path(tempfile.mkdtemp()) / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_snapshot_counting_link_reporters_without_the_table_publishes_nothing(
    tmp_path: Path,
) -> None:
    payload = _snapshot()
    payload["fta_weblinks"] = {"read": False}
    assert published_reporter_coverage(_written(tmp_path, payload)) is None


def test_the_waived_row_rule_counts_a_waived_row_that_carries_a_link() -> None:
    table = [
        {"NTD ID": "00001", "Weblink": "https://example.test/a.zip", "Waived": "true"},
        {"NTD ID": "00002", "Weblink": "", "Weblink Justification": "none", "Waived": "true"},
        {"NTD ID": "00003", "Weblink": "  ", "Waived": ""},
        {"NTD ID": "00004", "Weblink": "https://example.test/page", "Certification Flag": ""},
    ]
    assert weblink_ntd_ids(table) == frozenset({"00001", "00004"})
    # On the real table exactly two linked reporters rest only on Waived rows,
    # and they are counted: the strict alternative would make the low end 37.
    assert _snapshot()["fta_weblinks"]["edge_cases_in_link_tier"] == {
        "linked_only_on_waived_rows": 2,
        "linked_only_on_uncertified_rows": 3,
        "linked_only_to_a_page": 11,
    }


def test_the_table_row_and_lede_read_the_corrected_numbers() -> None:
    flat = " ".join(_page(_coverage()).split())
    assert "GTFS link reported to FTA, not matched to a catalog</td><td>593</td>" in flat
    assert "No GTFS link reported and no candidate in the catalogs read</td><td>35</td>" in flat
    assert "<td>168</td>" not in flat and "<td>473</td>" not in flat
    assert (
        "between <strong>35 and 48</strong> have no GTFS link reported to FTA and no feed found "
        "in the three open catalogs this site reads" in flat
    )


def test_the_self_reported_caveat_and_range_caveat_are_on_the_page() -> None:
    flat = " ".join(_page(_coverage()).split())
    assert FTA_LINK_CAVEAT == (
        "A GTFS link in FTA's NTD data is self-reported by the agency and is not fetched "
        "or validated by this project."
    )
    assert FTA_LINK_CAVEAT in flat
    assert RANGE_CAVEAT in flat
    assert "not that the feed is current or valid" in flat
    assert "has no feed" not in flat
    assert "retrieved 2026-10-23" in flat


def test_the_home_page_label_matches_the_shared_constant() -> None:
    """The label the home lead must print; /ntd/ prints the same words in its lede."""
    assert NO_LINK_NO_MATCH_LABEL == (
        "NTD reporters with no GTFS link reported to FTA and no feed found in an open catalog"
    )
