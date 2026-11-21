"""The clearance log leads with the scorecard (the 2026-11 IA, phase 5).

The log at /agency/<id>/fixes/ outranks the scorecard for some "<agency> gtfs"
searches ("go transit gtfs", "transperth gtfs", "stcp gtfs", "auckland
transport gtfs"). Those readers came for the feed URL and the grade, which live
on the scorecard, so the log's first line now says so and links it, in the
approved words: "Feed URL and current grade: <agency> scorecard".
"""

from __future__ import annotations

import re
from typing import Any

from scorecard_pipeline.render_site import _render_fixlog_page

_RECEIPTS = [
    {
        "code": "expired_calendar",
        "what": "3 calendars expired.",
        "last_seen": "2026-06-30",
        "cleared": "2026-07-01",
    }
]


def _page(name: str = "Demo Transit") -> str:
    art: dict[str, Any] = {"agency": {"id": "demo", "name": name}}
    return _render_fixlog_page(art, _RECEIPTS)


def _main(html: str) -> str:
    return html[html.index("<main") : html.index("</main>")]


def test_the_first_line_names_what_the_scorecard_has_and_links_it() -> None:
    main = _main(_page())
    first = re.search(r"<p [^>]*>.*?</p>", main, re.S)
    assert first is not None
    assert first.group(0) == (
        '<p class="brief-nav fixlog-lead">Feed URL and current grade: '
        '<a href="/agency/demo/"><bdi>Demo Transit</bdi> scorecard</a></p>'
    )
    assert first.start() < main.index("<h1")
    assert "Back to the full scorecard" not in main


def test_the_agency_name_in_the_lead_is_escaped() -> None:
    main = _main(_page('Quoted " <Transit>'))
    assert "<bdi>Quoted &quot; &lt;Transit&gt;</bdi> scorecard</a>" in main
