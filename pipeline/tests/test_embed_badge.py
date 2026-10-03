"""The named, dated embed badge served at /agency/<id>/badge.svg.

The badge sits on other people's sites for months after it is pasted, so the
case that matters most is the one fixtures rarely carry: no current score.
It must say so in words, with no letter, no number, and no zero.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from scorecard_pipeline.embed_badge import (
    CURRENT_DAYS,
    HEIGHT,
    WIDTH,
    badge_sentence,
    badge_state,
    render_named_badge,
)
from scorecard_pipeline.render_site import _embed_section

TODAY = dt.date(2026, 10, 2)
_SVG = "{http://www.w3.org/2000/svg}"
_SCORE_TEXT = re.compile(r"\b\d+(?:\.\d+)? of 100\b")


def _artifact(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agency": {"id": "demo", "name": "Demo Transit"},
        "overall": {"grade": "C", "score": 74.0},
        "snapshot_date": "2026-10-02",
    }
    base.update(overrides)
    return base


def _texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return ["".join(node.itertext()) for node in root.iter(f"{_SVG}text")]


def test_current_badge_names_the_agency_grade_score_and_date() -> None:
    state = badge_state("Demo Transit", _artifact(), TODAY)
    svg = render_named_badge(state)
    texts = _texts(svg)
    assert texts == [
        "C",
        "Demo Transit",
        "GTFS feed score 74.0 of 100",
        "Checked 2026-10-02 · gtfsscorecard.org",
    ]
    root = ET.fromstring(svg)
    assert root.get("role") == "img"
    assert root.get("width") == str(WIDTH) and root.get("height") == str(HEIGHT)
    title = root.find(f"{_SVG}title")
    assert title is not None
    assert title.text == root.get("aria-label") == badge_sentence(state)
    assert "grade C, 74.0 of 100, checked 2026-10-02" in str(title.text)


@pytest.mark.parametrize(
    ("overrides", "last_checked"),
    [
        ({"overall": None}, "2026-10-02"),
        ({"overall": {"grade": "C"}}, "2026-10-02"),
        ({"overall": {"grade": "C", "score": None}}, "2026-10-02"),
        ({"overall": {"grade": "C", "score": False}}, "2026-10-02"),
        ({"overall": {"grade": "", "score": 0}}, "2026-10-02"),
        ({"overall": {"grade": "Z", "score": 50}}, "2026-10-02"),
        ({"overall": {"grade": "C", "score": 101}}, "2026-10-02"),
        ({"snapshot_date": None}, None),
        ({"snapshot_date": "soon"}, None),
        # A real grade whose last check is older than the current window.
        ({"snapshot_date": "2026-09-17"}, "2026-09-17"),
        # A check dated after the render is not trusted either.
        ({"snapshot_date": "2026-10-09"}, "2026-10-09"),
    ],
)
def test_no_current_score_is_said_in_words_never_as_a_value(
    overrides: dict[str, Any], last_checked: str | None
) -> None:
    state = badge_state("Demo Transit", _artifact(**overrides), TODAY)
    assert not state.current
    svg = render_named_badge(state)
    texts = _texts(svg)
    assert "No current score" in texts
    joined = " ".join(texts)
    assert not _SCORE_TEXT.search(joined)
    assert not re.search(r"\b0\b", joined.replace("2026", ""))
    assert all(len(t) != 1 or not t.isalpha() for t in texts), "a letter grade is drawn"
    if last_checked:
        assert f"Last checked {last_checked}" in joined
    else:
        assert "Last checked" not in joined
    assert "no current GTFS feed quality score" in badge_sentence(state)


def test_the_no_score_detectors_fire_on_a_current_badge() -> None:
    # Negative control for the test above: the same detectors must trip on a
    # badge that does show a grade, or their silence proves nothing.
    texts = _texts(render_named_badge(badge_state("Demo Transit", _artifact(), TODAY)))
    joined = " ".join(texts)
    assert _SCORE_TEXT.search(joined)
    assert any(len(t) == 1 and t.isalpha() for t in texts)
    assert "No current score" not in texts


def test_current_window_boundary() -> None:
    edge = (TODAY - dt.timedelta(days=CURRENT_DAYS)).isoformat()
    past = (TODAY - dt.timedelta(days=CURRENT_DAYS + 1)).isoformat()
    assert badge_state("D", _artifact(snapshot_date=edge), TODAY).current
    assert not badge_state("D", _artifact(snapshot_date=past), TODAY).current


def test_badge_is_self_contained_and_escapes_the_name() -> None:
    svg = render_named_badge(badge_state('Bus & "Rail" <Co>', _artifact(), TODAY))
    ET.fromstring(svg)  # well formed
    for forbidden in ("<script", "<image", "<a ", "href", "@import", "url(", "http://", "https://"):
        assert forbidden not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "Bus &amp; " in svg


def test_long_name_uses_its_short_form_or_a_word_boundary() -> None:
    sfmta = "San Francisco Municipal Transportation Agency (SFMTA - Muni)"
    assert _texts(render_named_badge(badge_state(sfmta, _artifact(), TODAY)))[1] == "SFMTA - Muni"
    long_plain = "Southeastern Regional Transportation Authority Commuter Network"
    shown = _texts(render_named_badge(badge_state(long_plain, _artifact(), TODAY)))[1]
    assert shown.endswith("…") and long_plain.startswith(shown[:-1])
    assert long_plain[len(shown) - 1] == " "
    # The full name is never lost: the accessible sentence carries it.
    assert long_plain in badge_sentence(badge_state(long_plain, _artifact(), TODAY))


def test_embed_snippets_link_back_and_carry_no_grade() -> None:
    state = badge_state("Demo Transit", _artifact(), TODAY)
    html = _embed_section("demo", "Demo Transit", state)
    from html import unescape

    md = unescape(html.split('id="embed-md"', 1)[1].split(">", 1)[1].split("</textarea>", 1)[0])
    snippet = unescape(
        html.split('id="embed-html"', 1)[1].split(">", 1)[1].split("</textarea>", 1)[0]
    )
    assert "https://gtfsscorecard.org/agency/demo/badge.svg" in snippet
    assert 'href="https://gtfsscorecard.org/agency/demo/"' in snippet
    assert "(https://gtfsscorecard.org/agency/demo/)" in md
    # Pasted markup never updates, so it names the agency and no grade.
    for copied in (snippet, md):
        assert "Demo Transit" in copied
        assert "grade" not in copied.lower()
        assert "74" not in copied
        assert "<script" not in copied and "?" not in copied.split("badge.svg", 1)[1][:2]
    # The on-page preview's alt is the badge's own current sentence.
    assert f'alt="{badge_sentence(state)}"' in html


def test_render_writes_a_badge_beside_each_agency_page(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import shutil
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "golden_site"
    root = Path(tmp_path) / "golden_site"
    shutil.copytree(fixture, root)
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    from scorecard_pipeline.render_site import render_site

    now = dt.datetime(2026, 7, 3, 2, tzinfo=dt.UTC)
    render_site(now=now)
    web = root / "web"
    latest = json.loads((root / "data" / "artifacts" / "unitrans" / "latest.json").read_text())
    svg = (web / "agency" / "unitrans" / "badge.svg").read_text()
    assert f"checked {latest['snapshot_date']}" in badge_sentence(
        badge_state(latest["agency"]["name"], latest, now.date())
    )
    assert svg == render_named_badge(badge_state(latest["agency"]["name"], latest, now.date()))
    assert "badge.svg" not in (web / "sitemap.xml").read_text()
