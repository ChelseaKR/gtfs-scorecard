"""Rider-trips and need joined at render time (issue #367, shape 1).

The artifact carries reach and states ridership and need as ``not_joined_here``.
The agency page, call brief, board one-pager, and evidence packet join both when
they are built. Every joined number names its source and snapshot date. When the
join cannot happen, the page says why in plain language, and never shows a zero
or a blank in its place.

The four cases the issue names are rendered through all four surfaces: a US feed
whose NTD reporter matches, a Canadian feed, two records sharing one NTD
reporter, and a missing ridership snapshot. Each negative control asserts that
its sabotage actually landed before trusting the outcome it checks.
"""

from __future__ import annotations

import datetime as dt
import html
import importlib.util
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.config import Agency
from scorecard_pipeline.consequence import (
    DUPLICATE_NTD_REPORTER,
    NO_RIDERSHIP_DATA,
    NO_SERVED_AREA_DATA,
    NOT_JOINED_HERE,
    OUTSIDE_RIDERSHIP_SCOPE,
    UNDATED_SNAPSHOT,
    UNKNOWN_TIER,
    US_STATE_NEED_SCALE,
    NeedOverlay,
    RenderSources,
    RidershipSnapshot,
    SourceStamp,
    join_feed_context,
)
from scorecard_pipeline.consequence_sources import (
    CIMD_SOURCE,
    load_ca_need,
    load_render_sources,
    load_ridership_snapshot,
    load_us_need,
    ridership_meta,
)
from scorecard_pipeline.evidence_packet import (
    build_evidence_packet,
    render_evidence_packet_markdown,
)
from scorecard_pipeline.render_site import _render_agency, _render_board_page, _render_brief

FIXTURE = Path(__file__).parent / "fixtures" / "golden_site" / "data" / "artifacts"

UNITRANS_TRIPS = 3_456_789
RIDERSHIP_STAMP = SourceStamp("FTA National Transit Database, report year 2024", "2026-09-17")
US_NEED_STAMP = SourceStamp("US Census ACS 5-year 2022, statewide overlay", "2026-09-14")
CA_NEED_STAMP = SourceStamp(CIMD_SOURCE, "2026-09-01")


def _artifact(agency_id: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURE / agency_id / "latest.json").read_text())
    return loaded


def _sources(
    *,
    ridership: RidershipSnapshot | None = None,
    quarantined: frozenset[str] = frozenset(),
    us_need: NeedOverlay | None = None,
    ca_need: NeedOverlay | None = None,
) -> RenderSources:
    return RenderSources(
        ridership=ridership,
        quarantined_ntd_ids=quarantined,
        us_need=us_need,
        ca_need=ca_need,
    )


def _full_sources(quarantined: frozenset[str] = frozenset()) -> RenderSources:
    return _sources(
        ridership=RidershipSnapshot(
            trips={"90142": UNITRANS_TRIPS, "90090": 1_000_000}, stamp=RIDERSHIP_STAMP
        ),
        quarantined=quarantined,
        us_need=NeedOverlay(tiers={"California": "moderate"}, stamp=US_NEED_STAMP),
        ca_need=NeedOverlay(tiers={"barrie-transit": "high"}, stamp=CA_NEED_STAMP),
    )


def _text(markup: str) -> str:
    """Visible text, with entities decoded, so assertions read like the page."""
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


def _block(markup: str) -> str:
    """The consequence block alone, so an assertion cannot pass on other copy."""
    start = markup.index('<div class="consequence">')
    return _text(markup[start : markup.index("</div>", start)])


RenderFn = Callable[[dict[str, Any], Any], str]
PAGES: dict[str, RenderFn] = {
    "agency": lambda artifact, ctx: _render_agency(artifact, feed_context=ctx),
    "brief": lambda artifact, ctx: _render_brief(artifact, feed_context=ctx),
    "board": lambda artifact, ctx: _render_board_page(artifact, feed_context=ctx),
    "packet": lambda artifact, ctx: render_evidence_packet_markdown(
        build_evidence_packet(artifact, feed_context=ctx)
    ),
}


def _render(page: str, artifact: dict[str, Any], ctx: Any) -> str:
    """The consequence copy one surface shows, as plain text."""
    out = PAGES[page](artifact, ctx)
    if page == "packet":
        start = out.index("## Riders and need behind these fixes")
        return out[start : out.index("## Completion evidence")]
    return _block(out)


def _assert_no_absence_as_value(text: str) -> None:
    """The portfolio's commonest defect: a missing number shown as a value."""
    assert not re.search(r"\b0 rider trips\b", text)
    assert "counted  rider" not in text  # a blank where a number was expected
    assert "None" not in text
    assert "measures  on" not in text and "measures None" not in text


# --- case 1: a US feed whose NTD reporter matches ----------------------------


@pytest.mark.parametrize("page", sorted(PAGES))
def test_a_matched_us_feed_shows_its_trips_with_source_and_date(page: str) -> None:
    ctx = join_feed_context(_artifact("unitrans"), _full_sources(), us_state="California")
    text = _render(page, _artifact("unitrans"), ctx)
    assert f"It counted {UNITRANS_TRIPS:,} rider trips in a year." in text
    assert "National Transit Database ID 90142" in text
    assert "Source: FTA National Transit Database, report year 2024, as of 2026-09-17." in text
    # The US need tier is a statewide reading and says so, with its own stamp.
    assert "California as a whole measures moderate on transit need" in text
    assert "not one for this feed's service area" in text
    assert "US Census ACS 5-year 2022, statewide overlay, as of 2026-09-14" in text
    _assert_no_absence_as_value(text)


@pytest.mark.parametrize("page", sorted(PAGES))
def test_negative_control_an_undated_snapshot_hides_the_number(page: str) -> None:
    """The same feed and trips, with the stamp removed: the number must go."""
    undated = RidershipSnapshot(trips={"90142": UNITRANS_TRIPS}, stamp=None)
    sources = _sources(
        ridership=undated,
        us_need=NeedOverlay(tiers={"California": "moderate"}, stamp=None),
    )
    assert undated.trips["90142"] == UNITRANS_TRIPS  # the row is still there
    assert sources.ridership is not None and sources.ridership.stamp is None  # sabotage landed
    ctx = join_feed_context(_artifact("unitrans"), sources, us_state="California")
    assert ctx.ridership.reason == ctx.need.reason == UNDATED_SNAPSHOT
    text = _render(page, _artifact("unitrans"), ctx)
    assert f"{UNITRANS_TRIPS:,}" not in text
    assert "does not record its report year or fetch date" in text
    assert "does not record when it was built" in text
    assert "moderate" not in text
    _assert_no_absence_as_value(text)


# --- case 2: a Canadian feed --------------------------------------------------


@pytest.mark.parametrize("page", sorted(PAGES))
def test_a_canadian_feed_states_the_ntd_scope_and_its_cimd_tier(page: str) -> None:
    artifact = _artifact("barrie-transit")
    ctx = join_feed_context(artifact, _full_sources())
    assert ctx.ridership.reason == OUTSIDE_RIDERSHIP_SCOPE
    text = _render(page, artifact, ctx)
    assert "United States National Transit Database, which does not cover this feed's country" in (
        text
    )
    assert "The areas this feed serves measure high on transit need" in text
    assert f"{CIMD_SOURCE}, as of 2026-09-01" in text
    _assert_no_absence_as_value(text)


@pytest.mark.parametrize("page", sorted(PAGES))
def test_negative_control_a_canadian_feed_with_an_ntd_id_still_gets_no_trips(page: str) -> None:
    """Give the Canadian record a US reporter id the snapshot holds. Still no trips."""
    artifact = _artifact("barrie-transit")
    artifact["ntd_id_alignment"] = {"ntd_id": "90142"}
    sources = _full_sources()
    assert artifact["ntd_id_alignment"]["ntd_id"] == "90142"  # sabotage landed
    assert sources.ridership is not None and sources.ridership.trips["90142"] == UNITRANS_TRIPS
    text = _render(page, artifact, join_feed_context(artifact, sources))
    assert f"{UNITRANS_TRIPS:,}" not in text
    assert "does not cover this feed's country" in text


# --- case 3: two records sharing one NTD reporter ----------------------------


@pytest.mark.parametrize("page", sorted(PAGES))
def test_a_shared_ntd_reporter_is_held_back_on_every_record(page: str) -> None:
    """The snapshot holds the reporter's trips, and a naive join would show them."""
    from scorecard_pipeline.ridership import duplicate_ntd_reporter_ids

    registry = [
        Agency(
            id="unitrans", name="Unitrans", static_gtfs_url="https://e.org/u.zip", ntd_id="90142"
        ),
        Agency(
            id="davis-2", name="Davis 2", static_gtfs_url="https://e.org/d.zip", ntd_id="0090142"
        ),
    ]
    quarantined = frozenset(duplicate_ntd_reporter_ids(registry))
    sources = _full_sources(quarantined=quarantined)
    assert "90142" in quarantined  # the collision is real
    assert sources.ridership is not None and sources.ridership.trips["90142"] == UNITRANS_TRIPS

    for record in (_artifact("unitrans"), {**_artifact("unitrans"), "agency": {"id": "davis-2"}}):
        ctx = join_feed_context(record, sources, us_state="California")
        assert ctx.ridership.reason == DUPLICATE_NTD_REPORTER
        text = _render(page, _artifact("unitrans"), ctx)
        assert f"{UNITRANS_TRIPS:,}" not in text
        assert "More than one feed record claims this National Transit Database reporter" in text
        _assert_no_absence_as_value(text)


def test_negative_control_without_the_collision_the_same_snapshot_shows_trips() -> None:
    """Proves the test above is not vacuous: the number is there to be held back."""
    ctx = join_feed_context(_artifact("unitrans"), _full_sources(), us_state="California")
    assert ctx.ridership.annual_rider_trips == UNITRANS_TRIPS


# --- case 4: the ridership snapshot is missing -------------------------------


@pytest.mark.parametrize("page", sorted(PAGES))
def test_a_missing_snapshot_is_stated_not_zeroed(page: str, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    csv = root / "data" / "ntd-ridership.csv"
    assert not csv.exists()  # sabotage: no snapshot file at all
    sources = load_render_sources(root, frozenset())
    assert sources.ridership is None
    ctx = join_feed_context(_artifact("unitrans"), sources, us_state="California")
    assert ctx.ridership.reason == NO_RIDERSHIP_DATA
    assert ctx.need.reason == NO_SERVED_AREA_DATA
    text = _render(page, _artifact("unitrans"), ctx)
    assert "No ridership snapshot was on hand when this was built" in text
    assert "No need reading for this feed was on hand when this was built" in text
    _assert_no_absence_as_value(text)

    # And the control: write the snapshot with its stamp, and the number appears.
    csv.write_text("ntd_id,upt\n90142,3456789\n")
    (root / "data" / "ntd-ridership.meta.json").write_text(
        json.dumps(ridership_meta(2024, dt.date(2026, 9, 17)))
    )
    shown = join_feed_context(_artifact("unitrans"), load_render_sources(root, frozenset()))
    assert f"{UNITRANS_TRIPS:,} rider trips" in _render(page, _artifact("unitrans"), shown)


# --- a caller holding no snapshots --------------------------------------------


def test_with_no_sources_the_page_keeps_the_artifacts_own_absences() -> None:
    ctx = join_feed_context(_artifact("unitrans"))
    assert ctx.ridership.reason == ctx.need.reason == NOT_JOINED_HERE
    text = _block(_render_agency(_artifact("unitrans")))
    assert "add them from the ridership snapshot and name its date" in text
    _assert_no_absence_as_value(text)


def test_every_top_fix_carries_its_reach_line_on_each_page() -> None:
    artifact = _artifact("unitrans")
    for page in ("agency", "brief", "board"):
        text = _text(PAGES[page](artifact, None))
        assert "Fixing this covers all 296 stops in the feed." in text
        assert "This is a validator notice" in text  # unused_shape has no network share
    items = build_evidence_packet(artifact)["work_items"]
    assert items[0]["consequence"]["line"] == "Fixing this covers all 296 stops in the feed."
    assert items[0]["consequence"]["reach"]["share"] == 1.0


def test_the_packet_context_never_changes_its_evidence_id() -> None:
    artifact = _artifact("unitrans")
    joined = build_evidence_packet(
        artifact, feed_context=join_feed_context(artifact, _full_sources(), us_state="California")
    )
    bare = build_evidence_packet(artifact)
    assert joined["packet_id"] == bare["packet_id"]
    assert joined["consequence_context"]["ridership"]["source"] == RIDERSHIP_STAMP.to_json()
    assert bare["consequence_context"]["ridership"]["source"] is None


# --- the loaders -----------------------------------------------------------------


def test_the_loaders_read_stamps_and_refuse_to_invent_them(tmp_path: Path) -> None:
    root = tmp_path
    assert load_ridership_snapshot(root) is None
    assert load_us_need(root) is None
    assert load_ca_need(root) is None

    (root / "data" / "artifacts").mkdir(parents=True)
    (root / "web" / "api" / "v1").mkdir(parents=True)
    (root / "data" / "ntd-ridership.csv").write_text("ntd_id,upt\n90142,10\n")
    assert load_ridership_snapshot(root) == RidershipSnapshot(trips={"90142": 10}, stamp=None)
    (root / "data" / "ntd-ridership.meta.json").write_text(
        json.dumps({"report_year": "2024", "fetched_on": "2026-09-17"})
    )
    # A report year written as a string is not trusted as one.
    snapshot = load_ridership_snapshot(root)
    assert snapshot is not None and snapshot.stamp is None

    equity: dict[str, Any] = {"states": [{"state": "California", "need_tier": "moderate"}]}
    (root / "web" / "api" / "v1" / "equity.json").write_text(json.dumps(equity))
    assert load_us_need(root) == NeedOverlay(tiers={"California": "moderate"}, stamp=None)
    equity.update({"acs_year": "2022", "generated_on": "2026-09-14"})
    (root / "web" / "api" / "v1" / "equity.json").write_text(json.dumps(equity))
    us = load_us_need(root)
    assert us is not None and us.stamp == US_NEED_STAMP

    cimd = {"agencies": {"barrie-transit": {"need_tier": None}}, "generated_on": "not a date"}
    (root / "data" / "artifacts" / "canada-equity.json").write_text(json.dumps(cimd))
    ca = load_ca_need(root)
    assert ca is not None and ca.stamp is None and ca.tiers == {"barrie-transit": ""}
    (root / "data" / "artifacts" / "canada-equity.json").write_text("{not json")
    assert load_ca_need(root) is None


def test_a_territory_without_a_cimd_tier_is_unknown_not_lower() -> None:
    artifact = _artifact("barrie-transit")
    sources = _sources(ca_need=NeedOverlay(tiers={"barrie-transit": ""}, stamp=CA_NEED_STAMP))
    ctx = join_feed_context(artifact, sources)
    assert ctx.need.reason == UNKNOWN_TIER
    assert "lower" not in ctx.need_line()


def test_a_us_feed_with_no_known_state_gets_no_state_tier() -> None:
    ctx = join_feed_context(_artifact("unitrans"), _full_sources(), us_state="")
    assert ctx.need.reason == NO_SERVED_AREA_DATA
    assert ctx.need.scale == US_STATE_NEED_SCALE


def test_the_to_json_names_a_source_only_beside_a_value() -> None:
    joined = join_feed_context(_artifact("unitrans"), _full_sources(), us_state="California")
    payload = joined.to_json()
    assert payload["ridership"]["annual_rider_trips"] == UNITRANS_TRIPS
    assert payload["ridership"]["source"] == RIDERSHIP_STAMP.to_json()
    assert payload["served_area_need"]["area"] == "California"
    canadian = join_feed_context(_artifact("barrie-transit"), _full_sources()).to_json()
    assert canadian["ridership"]["annual_rider_trips"] is None
    assert canadian["ridership"]["source"] is None


def test_unexpected_reasons_still_read_as_plain_absences() -> None:
    from scorecard_pipeline.consequence import FeedContext, Ridership, ServedAreaNeed

    odd = FeedContext(ridership=Ridership(reason="new"), need=ServedAreaNeed(reason="new"))
    assert odd.lines() == [
        "Annual rider-trips are not known for this feed.",
        "Transit need is not known for this feed.",
    ]


# --- the copy -----------------------------------------------------------------------


def _readability() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_readability.py"
    spec = importlib.util.spec_from_file_location("check_readability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_new_sentence_clears_the_plain_language_bars() -> None:
    from scorecard_pipeline import consequence as c
    from scorecard_pipeline.render_site import _CONSEQUENCE_NOT_A_RANKING

    readability = _readability()
    us = join_feed_context(_artifact("unitrans"), _full_sources(), us_state="California")
    ca = join_feed_context(_artifact("barrie-transit"), _full_sources())
    texts = {
        "ridership line": us.ridership_line(),
        "us need line": us.need_line(),
        "ca need line": ca.need_line(),
        "not a ranking": _CONSEQUENCE_NOT_A_RANKING,
    }
    for reason in (c.NOT_JOINED_HERE, c.UNDATED_SNAPSHOT, c.NO_RIDERSHIP_DATA):
        texts[f"ridership {reason}"] = c._RIDERSHIP_ABSENCE[reason]
    for reason in (c.NOT_JOINED_HERE, c.UNDATED_SNAPSHOT, c.NO_SERVED_AREA_DATA):
        texts[f"need {reason}"] = c._NEED_ABSENCE[reason]
    for label, text in texts.items():
        assert readability.check_text(label, text) == [], text


# --- the producers record the stamps pages cite ---------------------------------


def test_the_ridership_fetch_writes_its_stamp_beside_the_csv(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scorecard_pipeline import cli
    from scorecard_pipeline.cli import main

    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n  - id: a\n    name: A\n    static_gtfs_url: https://example.org/a.zip\n"
    )
    rows = "".join(f"{90000 + i},{1000 + i}\n" for i in range(150))
    monkeypatch.setattr(
        "scorecard_pipeline.ridership.fetch_ridership_csv", lambda _year: "ntd_id,upt\n" + rows
    )
    monkeypatch.setattr(cli, "utc_today", lambda: dt.date(2026, 9, 17))
    assert main(["ntd-ridership", "--fetch"]) == 0
    meta = json.loads((isolated_repo_root / "data" / "ntd-ridership.meta.json").read_text())
    assert meta == {
        "source": "FTA National Transit Database",
        "report_year": 2025,
        "fetched_on": "2026-09-17",
    }
    snapshot = load_ridership_snapshot(isolated_repo_root)
    assert snapshot is not None and snapshot.stamp == SourceStamp(
        "FTA National Transit Database, report year 2025", "2026-09-17"
    )


def test_the_equity_overlay_records_its_acs_year_and_build_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from scorecard_pipeline import cli, config, equity

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "index.json").write_text(json.dumps({"agencies": {}}))
    monkeypatch.setattr(config, "artifacts_dir", lambda: artifact_root)
    monkeypatch.setattr(cli, "AGENCIES", {})
    monkeypatch.setattr(cli, "_published_states", dict)
    monkeypatch.setattr(cli, "utc_today", lambda: dt.date(2026, 9, 14))
    monkeypatch.setattr(equity, "fetch_state_indicators", lambda: {})
    monkeypatch.setattr(
        equity,
        "build_overlay",
        lambda *_a, **_k: {
            "states": [{"state": "California", "need_tier": "moderate"}],
            "priority": [],
        },
    )
    monkeypatch.setattr(equity, "render_overlay", lambda _overlay: "")
    out = tmp_path / "equity.json"
    args = argparse.Namespace(allow_empty=True, json_out=str(out), out=None)
    assert cli._cmd_equity(args, argparse.ArgumentParser()) == 0
    written = json.loads(out.read_text())
    assert written["acs_year"] == equity.ACS_YEAR
    assert written["generated_on"] == "2026-09-14"


def test_the_evidence_packet_verb_joins_the_repository_snapshots(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    root = isolated_repo_root
    (root / "data").mkdir(parents=True)
    (root / "web").mkdir()
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: unitrans\n"
        "    name: Unitrans\n"
        "    static_gtfs_url: https://example.org/unitrans.zip\n"
        "    ntd_id: '90142'\n"
    )
    (root / "data" / "ntd-ridership.csv").write_text(f"ntd_id,upt\n90142,{UNITRANS_TRIPS}\n")
    (root / "data" / "ntd-ridership.meta.json").write_text(
        json.dumps(ridership_meta(2024, dt.date(2026, 9, 17)))
    )
    artifact_path = root / "unitrans.json"
    artifact_path.write_text(json.dumps(_artifact("unitrans")))
    assert main(["evidence-packet", str(artifact_path), "--format", "markdown"]) == 0
    out = capsys.readouterr().out
    assert f"It counted {UNITRANS_TRIPS:,} rider trips in a year." in out
    assert "report year 2024, as of 2026-09-17" in out
    # No catalog state and no overlay file: an absence, not a tier.
    assert "No need reading for this feed was on hand when this was built" in out
