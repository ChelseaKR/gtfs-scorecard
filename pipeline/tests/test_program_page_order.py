"""Program pages: the member list first, a free watch card, and a place crumb.

The state and country pages under /program/ are the place hubs of the 2026-11
information architecture. A reader there wants every agency in the group, so
the member list moves up, under a card offering the free alert for the group.
ADR 0064's program panel is unchanged and stays last. These tests hold the
order, the crumb, and that nothing paid moved up with them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scorecard_pipeline.render_site import _ROLLUP_WATCH_CARD, _rollup_place_label

_GOLDENS = Path(__file__).resolve().parent / "goldens" / "program"
_ROLLUPS = sorted(p.parent.name for p in _GOLDENS.glob("*/index.html"))


def _main(slug: str) -> str:
    html = (_GOLDENS / slug / "index.html").read_text()
    return html[html.index("<main") : html.index("</main>")]


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


@pytest.mark.parametrize("slug", _ROLLUPS)
def test_the_member_list_comes_right_after_the_summary_and_watch_card(slug: str) -> None:
    main = _main(slug)
    members = main.index('id="members-h"')
    assert main.index('id="watch-feeds-h"') < members
    for later in (
        'id="rollup-common-fixes-h"',
        'id="rollup-expired-h"',
        'id="rollup-rt-h"',
        'id="rollup-shapes-h"',
        'id="rollup-reconcile-h"',
        'id="bundle-h"',
    ):
        if later in main:
            assert members < main.index(later), later


@pytest.mark.parametrize("slug", _ROLLUPS)
def test_the_program_panel_is_still_last_and_the_watch_card_is_free(slug: str) -> None:
    main = _main(slug)
    card = re.search(r'<section class="watch-card".*?</section>', main, re.S)
    assert card is not None
    assert "/bundle/" not in card.group(0) and "paid" not in card.group(0).casefold()
    if 'id="bundle-h"' in main:
        assert main.index('id="bundle-h"') > main.index('id="members-h"')
        assert main.index("/bundle/") > main.index('id="members-h"')


def test_the_watch_card_wording_and_link() -> None:
    assert _visible(_ROLLUP_WATCH_CARD) == (
        "Watch these feeds Get an email before a feed expires or its grade drops. Feed alerts"
    )
    assert '<a class="button button-secondary" href="/subscribe.html">Feed alerts</a>' in (
        _ROLLUP_WATCH_CARD
    )


def test_a_state_page_reads_as_a_place() -> None:
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', _main("california"), re.S)
    assert crumb is not None
    assert _visible(crumb.group(0)) == "Home Agencies California"
    assert 'href="/agencies/"' in crumb.group(0)


@pytest.mark.parametrize("slug", ["all", "yolo-county"])
def test_a_named_cohort_keeps_the_rollup_index_as_its_parent(slug: str) -> None:
    crumb = re.search(r'<nav class="breadcrumb".*?</nav>', _main(slug), re.S)
    assert crumb is not None
    assert 'href="/program/"' in crumb.group(0)
    assert "Program rollups" in _visible(crumb.group(0))


@pytest.mark.parametrize(
    ("rid", "name", "label"),
    [
        ("california", "California agencies", "California"),
        ("new-mexico", "New Mexico agencies", "New Mexico"),
        ("country-ca", "Canada", "Canada"),
        ("all", "All tracked agencies", ""),
        ("yolo-county", "Yolo County", ""),
    ],
)
def test_place_labels(rid: str, name: str, label: str) -> None:
    assert _rollup_place_label({"rollup": {"id": rid, "name": name}}) == label
