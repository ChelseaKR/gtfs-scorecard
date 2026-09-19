"""The app's consequence wording (web/src/consequence.js), walked against Python.

The static pages word a finding's consequence in ``consequence.py``. The
interactive app words it again in JavaScript, from the same templates, and this
file holds the two together: the same input must read the same in both, and an
absence must never read as a number in either.

Each test runs the real module under Node, in a scratch folder marked as an ES
module package so it loads on any Node version. The negative controls first
prove their sabotage landed: each one renders an intact block, checks that it
shows a number, and only then breaks it and checks that the number is gone.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import consequence as c
from scorecard_pipeline.consequence import Reach, reach_sentence

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "web" / "src"

_HARNESS = """
import { readFileSync } from "node:fs";
globalThis.document = { documentElement: { lang: "en" } };
const mod = await import("./consequence.js");
const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = cases.map(({ fn, args }) => mod[fn](...args));
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The module and what it imports, copied beside a package.json that marks
    them as ES modules."""
    folder = tmp_path_factory.mktemp("consequence-web")
    (folder / "package.json").write_text('{"type": "module"}')
    (folder / "generated").mkdir()
    for name in ("consequence.js", "locale.js"):
        shutil.copy(WEB_SRC / name, folder / name)
    shutil.copy(WEB_SRC / "generated" / "constants.js", folder / "generated" / "constants.js")
    (folder / "run.mjs").write_text(_HARNESS)
    return folder


def run_js(sandbox: Path, calls: list[tuple[str, list[Any]]]) -> list[Any]:
    """Call exported functions of consequence.js and return their results."""
    node = shutil.which("node")
    assert node is not None, "node is required for the web tests"
    cases = sandbox / "cases.json"
    cases.write_text(json.dumps([{"fn": fn, "args": args} for fn, args in calls]))
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [node, str(sandbox / "run.mjs"), str(cases)],
        check=True,
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def reach_json(**overrides: Any) -> dict[str, Any]:
    """A known partial reach, published as the artifact publishes it."""
    reach = Reach(
        basis=c.STOPS,
        basis_label="stops",
        affected=296,
        total=9850,
        share=round(296 / 9850, 4),
        total_source="geo.stop_count",
    ).to_json()
    reach.update(overrides)
    return reach


def js_sentences(sandbox: Path, reaches: list[Any]) -> list[str]:
    return [str(text) for text in run_js(sandbox, [("reachSentence", [r]) for r in reaches])]


# --- the sentence is the same in both languages -------------------------------------


def _states() -> list[Reach]:
    """Every shape a reach takes, from the publisher's own dataclass."""
    known: list[Reach] = []
    for affected, total, basis in (
        (296, 9850, c.STOPS),
        (3, 9850, c.STOPS),
        (9847, 9850, c.BOARDABLE_STOPS),
        (1, 3, c.ROUTES),
        (2, 3, c.TRIPS),
        (5, 5, c.STOPS),
        (0, 1200, c.TRIPS),
        (1, 1, c.ROUTES),
        (25, 200, c.STOPS),  # 12.5 percent: the half-to-even case
        (27, 200, c.STOPS),  # 13.5 percent
        (1234567, 2345678, c.TRIPS),
    ):
        label = c.BASIS_LABEL[basis]
        known.append(
            Reach(
                basis=basis,
                basis_label=label,
                affected=affected,
                total=total,
                share=round(affected / total, 4),
                total_source="x",
            )
        )
    absent = [
        Reach(basis=c.NO_BASIS, basis_label="", reason=reason)
        for reason in (
            c.FEED_LEVEL,
            c.SAMPLED_WINDOW,
            c.NOT_NETWORK_COUNTABLE,
            c.VALIDATOR_NOTICE,
            c.UNMAPPED_FINDING,
        )
    ]
    absent += [
        Reach(basis=c.STOPS, basis_label="stops", reason=c.COUNT_MISSING),
        Reach(basis=c.STOPS, basis_label="stops", affected=4, reason=c.DENOMINATOR_MISSING),
        Reach(
            basis=c.TRIPS,
            basis_label="trips",
            affected=9,
            total=4,
            total_source="x",
            reason=c.INCONSISTENT_COUNTS,
        ),
        Reach(basis=c.STOPS, basis_label="stops", reason="something_new"),
        Reach(basis=c.NO_BASIS, basis_label="", reason="something_new"),
    ]
    return known + absent


def test_every_reach_state_reads_the_same_as_the_static_pages(sandbox: Path) -> None:
    states = _states()
    expected = [reach_sentence(state) for state in states]
    got = js_sentences(sandbox, [state.to_json() for state in states])
    assert got == expected
    # The comparison is not vacuous: partial, all, none, and absences are all in it.
    assert any(text.startswith("Fixing this covers 296 of 9,850") for text in got)
    assert any(text.startswith("Fixing this covers all 5") for text in got)
    assert any(text.startswith("None of the feed's 1,200") for text in got)
    assert any("no share of it to count" in text for text in got)


def test_every_four_place_share_rounds_the_way_python_does(sandbox: Path) -> None:
    # 10,001 shares from 0.0000 to 1.0000. Half-to-even is where a naive port
    # of Python's round() goes wrong, and it goes wrong at exactly the shares
    # that land on a half percent.
    total = 10_000
    states = [
        Reach(
            basis=c.STOPS,
            basis_label="stops",
            affected=affected,
            total=total,
            share=round(affected / total, 4),
            total_source="x",
        )
        for affected in range(total + 1)
    ]
    expected = [reach_sentence(state) for state in states]
    got = js_sentences(sandbox, [state.to_json() for state in states])
    mismatches = [(i, e, g) for i, (e, g) in enumerate(zip(expected, got, strict=True)) if e != g]
    assert mismatches == []
    assert sum("about 12%" in text for text in got) > 0
    assert sum("about 14%" in text for text in got) > 0


def test_small_totals_agree_at_every_count(sandbox: Path) -> None:
    states = [
        Reach(
            basis=c.ROUTES,
            basis_label="routes",
            affected=affected,
            total=total,
            share=round(affected / total, 4),
            total_source="x",
        )
        for total in range(1, 61)
        for affected in range(total + 1)
    ]
    expected = [reach_sentence(state) for state in states]
    assert js_sentences(sandbox, [state.to_json() for state in states]) == expected


# --- an absence never reads as a number ---------------------------------------------

_SCHEMA = json.loads((ROOT / "web" / "schemas" / "artifact.schema.json").read_text())
_REACH_REASONS = [
    reason
    for reason in _SCHEMA["$defs"]["consequenceReach"]["properties"]["reason"]["enum"]
    if reason
]


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d|%|\bnearly all\b", text))


@pytest.mark.parametrize("basis", ["stops", "boardable_stops", "routes", "trips", "none"])
def test_no_reason_in_the_schema_renders_a_number(sandbox: Path, basis: str) -> None:
    label = "" if basis == "none" else basis.replace("_", " ")
    blocks = [
        {
            "basis": basis,
            "basis_label": label or None,
            "affected": None,
            "total": None,
            "share": None,
            "total_source": None,
            "reason": reason,
        }
        for reason in _REACH_REASONS
    ]
    for text in js_sentences(sandbox, blocks):
        assert not _has_number(text), text


def test_negative_control_a_broken_block_shows_words_not_a_number(sandbox: Path) -> None:
    intact = reach_json()
    control = js_sentences(sandbox, [intact])[0]
    assert _has_number(control), "the intact block must show a number, or nothing is proven"

    broken = {
        "share is zero but the reason says the count is missing": reach_json(
            share=0, affected=0, reason="count_missing"
        ),
        "share is null with an empty reason": reach_json(share=None),
        "share is null and the counts are gone": reach_json(share=None, affected=None, total=None),
        "a reason sits beside a share": reach_json(reason="feed_level"),
        "more affected than the total": reach_json(affected=9851, share=1.0),
        "share disagrees with its own counts": reach_json(share=0.5),
        "share above one": reach_json(share=1.5),
        "share below zero": reach_json(share=-0.1),
        "share is not a number": reach_json(share="0.03"),
        "counts are fractions": reach_json(affected=2.5),
        "total of zero": reach_json(total=0, share=0),
        "affected is negative": reach_json(affected=-3, share=-0.0003),
        "basis is none but a share is present": reach_json(basis="none", basis_label=None),
        "basis is unknown": reach_json(basis="riders"),
        "label is empty": reach_json(basis_label=""),
        "share is null but the counts would give one": reach_json(share=None, affected=0, total=1),
    }
    for label, block in broken.items():
        text = js_sentences(sandbox, [block])[0]
        assert not _has_number(text), f"{label}: {text}"
        assert "None of the feed" not in text, label


def test_a_missing_or_odd_reach_block_is_still_a_sentence(sandbox: Path) -> None:
    odd_blocks: list[Any] = [None, "stops", 12, [], {}]
    for odd in odd_blocks:
        [text] = js_sentences(sandbox, [odd])
        assert text.startswith("The feed's network count is not published here"), odd
        assert not _has_number(text)


# --- rider-trips and need are never worded as numbers -------------------------------

_NOT_JOINED = {"ridership": "APP RIDERSHIP WORDING", "need": "APP NEED WORDING"}


def context(sandbox: Path, consequence: Any) -> dict[str, Any]:
    [result] = run_js(sandbox, [("feedContext", [consequence, _NOT_JOINED])])
    return result  # type: ignore[no-any-return]


def _block(ridership: dict[str, Any], need: dict[str, Any]) -> dict[str, Any]:
    return {"code": "x", "ridership": ridership, "served_area_need": need}


_RIDERSHIP_REASONS = [
    reason
    for reason in _SCHEMA["$defs"]["consequenceRidership"]["properties"]["reason"]["enum"]
    if reason
]
_NEED_REASONS = [
    reason
    for reason in _SCHEMA["$defs"]["consequenceNeed"]["properties"]["reason"]["enum"]
    if reason
]


def test_every_ridership_reason_states_itself_in_the_static_pages_words(sandbox: Path) -> None:
    for reason in _RIDERSHIP_REASONS:
        block = _block(
            {"annual_rider_trips": None, "ntd_id": "90142", "reason": reason},
            {"tier": None, "scale": None, "reason": "outside_need_scope"},
        )
        got = context(sandbox, block)["ridership"]
        if reason == c.NOT_JOINED_HERE:
            assert got == _NOT_JOINED["ridership"]
        else:
            assert got == c._RIDERSHIP_ABSENCE[reason]
        assert not _has_number(got), reason


def test_every_need_reason_states_itself_in_the_static_pages_words(sandbox: Path) -> None:
    for reason in _NEED_REASONS:
        block = _block(
            {"annual_rider_trips": None, "ntd_id": None, "reason": "outside_ridership_scope"},
            {"tier": None, "scale": "us_acs", "reason": reason},
        )
        got = context(sandbox, block)["need"]
        if reason == c.NOT_JOINED_HERE:
            assert got == _NOT_JOINED["need"]
        else:
            assert got == c._NEED_ABSENCE[reason]


def test_only_a_record_that_leaves_the_join_to_the_agency_page_points_there(
    sandbox: Path,
) -> None:
    joined_later = _block(
        {"annual_rider_trips": None, "ntd_id": "90142", "reason": "not_joined_here"},
        {"tier": None, "scale": "us_acs", "reason": "not_joined_here"},
    )
    assert context(sandbox, joined_later)["pointsToAgencyPage"] is True
    canadian = _block(
        {"annual_rider_trips": None, "ntd_id": None, "reason": "outside_ridership_scope"},
        {"tier": None, "scale": None, "reason": "outside_need_scope"},
    )
    assert context(sandbox, canadian)["pointsToAgencyPage"] is False
    # One line pointing there is enough to offer the link.
    half = _block(
        {"annual_rider_trips": None, "ntd_id": None, "reason": "outside_ridership_scope"},
        {"tier": None, "scale": "ca_cimd", "reason": "not_joined_here"},
    )
    assert context(sandbox, half)["pointsToAgencyPage"] is True


def test_negative_control_a_value_with_no_source_and_date_is_not_shown(sandbox: Path) -> None:
    # The control: the same record, stated the way the static pages state a
    # joined number, does put the figure and its source in front of a reader.
    from scorecard_pipeline.consequence import (
        FeedContext,
        Ridership,
        ServedAreaNeed,
        SourceStamp,
    )

    stamped = FeedContext(
        ridership=Ridership(annual_rider_trips=3_456_789, ntd_id="90142"),
        need=ServedAreaNeed(tier="high", scale="us_acs_state"),
        ridership_source=SourceStamp("FTA National Transit Database", "2026-09-17"),
        need_source=SourceStamp("US Census ACS 5-year 2022", "2026-09-14"),
        need_area="California",
    )
    assert "3,456,789" in stamped.ridership_line()
    assert "high" in stamped.need_line()

    # The sabotage: the same numbers arrive in the artifact with no stamp beside them.
    for trips in (3_456_789, 0):
        block = _block(
            {"annual_rider_trips": trips, "ntd_id": "90142", "reason": ""},
            {"tier": "high", "scale": "us_acs", "reason": ""},
        )
        got = context(sandbox, block)
        assert "3,456,789" not in got["ridership"] and "3456789" not in got["ridership"]
        assert not re.search(r"\b0\b", got["ridership"])
        assert got["ridership"] == c._RIDERSHIP_ABSENCE[c.UNDATED_SNAPSHOT]
        assert "high" not in got["need"]
        assert got["need"] == c._NEED_ABSENCE[c.UNDATED_SNAPSHOT]


def test_a_block_with_neither_a_value_nor_a_reason_reads_as_not_known(sandbox: Path) -> None:
    empty = _block(
        {"annual_rider_trips": None, "ntd_id": None, "reason": ""},
        {"tier": None, "scale": None, "reason": ""},
    )
    got = context(sandbox, empty)
    assert got["ridership"] == c.RIDERSHIP_UNKNOWN
    assert got["need"] == c.NEED_UNKNOWN
    odd_records: list[Any] = [
        None,
        {},
        {"ridership": 3},
        {"ridership": None, "served_area_need": []},
    ]
    for odd in odd_records:
        got = context(sandbox, odd)
        assert got["ridership"] == c.RIDERSHIP_UNKNOWN
        assert got["need"] == c.NEED_UNKNOWN
        assert not _has_number(got["ridership"] + got["need"])


def test_an_unfamiliar_reason_reads_as_not_known_never_as_a_value(sandbox: Path) -> None:
    block = _block(
        {"annual_rider_trips": None, "ntd_id": "90142", "reason": "a_reason_from_the_future"},
        {"tier": None, "scale": "us_acs", "reason": "a_reason_from_the_future"},
    )
    got = context(sandbox, block)
    assert got["ridership"] == c.RIDERSHIP_UNKNOWN
    assert got["need"] == c.NEED_UNKNOWN


# --- finding and record lookups -----------------------------------------------------


def test_a_finding_without_a_block_has_no_reach_and_one_with_it_says_whether_it_is_known(
    sandbox: Path,
) -> None:
    known = {"consequence": {"reach": reach_json()}}
    absent = {"consequence": {"reach": reach_json(share=None, reason="count_missing")}}
    results = run_js(
        sandbox,
        [
            ("findingReach", [{}]),
            ("findingReach", [None]),
            ("findingReach", [{"consequence": "nope"}]),
            ("findingReach", [{"consequence": {"reach": None}}]),
            ("findingReach", [known]),
            ("findingReach", [absent]),
        ],
    )
    assert results[:4] == [None, None, None, None]
    assert results[4]["known"] is True
    assert results[4]["text"].startswith("Fixing this covers 296 of 9,850 stops")
    assert results[5]["known"] is False
    assert not _has_number(results[5]["text"])


def test_the_feed_block_comes_from_the_first_finding_that_has_one(sandbox: Path) -> None:
    block = _block(
        {"annual_rider_trips": None, "ntd_id": None, "reason": "outside_ridership_scope"},
        {"tier": None, "scale": None, "reason": "outside_need_scope"},
    )
    only_in_a_category = {
        "top_fixes": [{"code": "a"}],
        "categories": {"freshness": {"findings": [{"code": "b", "consequence": block}]}},
    }
    in_the_fixes = {"top_fixes": [{"code": "a", "consequence": block}], "categories": {}}
    none_anywhere = {"top_fixes": [{"code": "a"}], "categories": {"x": {"findings": [{}]}}}
    results = run_js(
        sandbox,
        [
            ("feedConsequence", [only_in_a_category]),
            ("feedConsequence", [in_the_fixes]),
            ("feedConsequence", [none_anywhere]),
            ("feedConsequence", [{}]),
            ("feedConsequence", [None]),
        ],
    )
    assert results == [block, block, None, None, None]


# --- the copy -----------------------------------------------------------------------

_CATALOG = json.loads(
    (ROOT / "pipeline" / "src" / "scorecard_pipeline" / "locales" / "app.en.json").read_text()
)
_NEW_KEYS = sorted(key for key in _CATALOG if key.startswith("consequence_"))


def test_the_app_catalog_holds_every_consequence_key_the_app_asks_for() -> None:
    app = (WEB_SRC / "app.js").read_text()
    asked = set(re.findall(r't\("(consequence_\w+)"', app))
    assert asked, "app.js should ask the catalog for consequence copy"
    assert asked <= set(_CATALOG), sorted(asked - set(_CATALOG))
    assert set(_NEW_KEYS) == asked, "every consequence catalog key should be in use"


def _readability() -> Any:
    import importlib.util

    path = ROOT / "pipeline" / "scripts" / "check_readability.py"
    spec = importlib.util.spec_from_file_location("check_readability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_new_app_copy_clears_the_plain_language_bars() -> None:
    readability = _readability()
    # Prose only. The link label is a six-word fragment, and the gate excludes
    # fragments for the same reason it excludes effort hints: a Flesch score of
    # a handful of words measures the words, not the writing.
    prose = [key for key in _NEW_KEYS if str(_CATALOG[key]).endswith(".")]
    assert len(prose) == len(_NEW_KEYS) - 1
    for key in prose:
        text = str(_CATALOG[key])
        assert readability.check_text(key, text) == [], text


def test_the_new_app_copy_follows_the_house_style() -> None:
    joined = " ".join(str(_CATALOG[key]) for key in _NEW_KEYS)
    assert "—" not in joined and "–" not in joined, "no em or en dashes"
    banned = ("leverage", "seamless", "robust", "powerful", "cutting-edge", "unlock")
    assert not [word for word in banned if word in joined.lower()]
    # Findings are framed as fixes and the reader is addressed respectfully.
    assert not re.search(r"\b(fail|failed|failure|poor|bad)\b", joined.lower())


def test_the_app_never_words_a_consequence_by_itself() -> None:
    # The wording is the static pages' wording, filled from the shared copy.
    # A sentence typed into the module would be a second copy that can drift, so
    # no string literal in it may hold more than one word.
    source = (WEB_SRC / "consequence.js").read_text()
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    literals = re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'|`([^`]*)`', code)
    phrases = [text for group in literals for text in group if re.search(r"\S\s+\S", text)]
    assert phrases == [], phrases
