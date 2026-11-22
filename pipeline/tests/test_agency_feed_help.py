"""Agency pages: the free alert under the grade, and help when the feed address fails.

Real searchers land almost only on agency pages, and the ones whose feed
address on file had failed left without a next step (research of 2026-11-20:
0 of 8 engaged). Two lines answer that:

* every agency page offers the free feed-health alert right under the grade,
  with the agency already chosen on the alerts form;
* a page whose address on file answered the daily check with an HTTP 4xx says
  so at the top, links the Mobility Database's newest saved copy when the grade
  was scored from one, and points to the existing correction route for the new
  address. No new form and no new email collection.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.render_site import (
    _dead_feed_note,
    _render_agency,
    _saved_copy_url,
    _watch_line,
)

_GOLDENS = Path(__file__).resolve().parent / "goldens" / "agency"
_MDB_COPY = "https://files.mobilitydatabase.org/mdb-615/latest.zip"
_GCS_COPY = (
    "https://storage.googleapis.com/storage/v1/b/mdb-latest/o/"
    "us-california-torrance-transit-gtfs-34.zip?alt=media"
)


def _artifact(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agency": {"id": "demo-transit", "name": "Demo Transit"},
        "overall": {"grade": "D", "score": 63.5},
        "snapshot_date": "2026-11-09",
        "categories": {"realtime": {"status": "not_yet_measured"}},
        "feed": {"static_url": "https://feeds.example.org/demo/gtfs.zip"},
    }
    base.update(overrides)
    return base


def _mirror(url: str) -> dict[str, Any]:
    return {"source": "mirror", "final_url": url}


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


# --- the free alert under the grade -------------------------------------------------


def test_the_watch_line_links_the_alerts_form_with_this_agency_chosen() -> None:
    line = _watch_line("demo-transit")
    assert 'href="/subscribe.html?agency=demo-transit"' in line
    assert ">Watch this feed</a>" in line
    assert _visible(line) == (
        "Watch this feed for free: we email you before it expires or when its grade drops."
    )


def test_the_watch_line_sits_right_under_the_answer_block() -> None:
    """Under the grade and the feed card (ADR 0085), before the other actions."""
    html = _render_agency(_artifact())
    watch = html.index('<p class="watch-line">')
    assert html.index('class="score-big"') < html.index('<p class="feed-source">') < watch
    assert watch < html.index('<nav class="report-actions"')


@pytest.mark.parametrize("page", sorted(p.parent.name for p in _GOLDENS.glob("*/index.html")))
def test_every_rendered_agency_page_offers_the_alert_once(page: str) -> None:
    html = (_GOLDENS / page / "index.html").read_text()
    assert html.count('<p class="watch-line">') == 1
    assert f'href="/subscribe.html?agency={page}" data-measure="agency_watch_click">' in html
    assert ">Watch this feed</a> for free" in html


# --- help when the feed address on file failed ------------------------------------


def test_a_404_with_a_saved_copy_links_the_copy_and_the_correction_route() -> None:
    note = _dead_feed_note("demo-transit", {"status": 404}, _artifact(fetch=_mirror(_MDB_COPY)))
    assert f'<a href="{_MDB_COPY}">Download the newest saved copy</a>' in note
    assert '<a href="/claim/?agency=demo-transit">send us the new address</a>' in note
    assert _visible(note) == (
        "The feed address on file failed at our last check (HTTP 404). Download the newest "
        "saved copy from the Mobility Database, or send us the new address."
    )


def test_a_failure_without_a_saved_copy_offers_only_the_new_address() -> None:
    note = _dead_feed_note("demo-transit", {"status": 403}, _artifact())
    assert "mobilitydatabase" not in note and "Download" not in note
    assert _visible(note) == (
        "The feed address on file failed at our last check (HTTP 403). If the feed moved, "
        "send us the new address."
    )


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        {"status": 200},
        {"status": 304},
        {"status": 301},
        # A server error, a timeout or a certificate failure can pass by the
        # next check, so none of them says the address failed.
        {"status": 503},
        {"status": None, "consecutive_failures": 4},
        {"status": True},
        {"status": "404"},
    ],
)
def test_no_note_unless_the_last_check_was_an_http_4xx(record: dict[str, Any] | None) -> None:
    assert _dead_feed_note("demo-transit", record, _artifact(fetch=_mirror(_MDB_COPY))) == ""


@pytest.mark.parametrize("url", [_MDB_COPY, _GCS_COPY])
def test_the_two_saved_copy_shapes_are_linked(url: str) -> None:
    assert _saved_copy_url(_artifact(fetch=_mirror(url))) == url


@pytest.mark.parametrize(
    "fetch",
    [
        {"source": "origin", "final_url": _MDB_COPY},
        {"source": "mirror", "final_url": "https://gtfsscorecard.org/data/raw/demo.zip"},
        {"source": "mirror", "final_url": "https://files.mobilitydatabase.org/guess/latest.zip"},
        {"source": "mirror", "final_url": _MDB_COPY + "?token=abc"},
        {"source": "mirror", "final_url": "http://files.mobilitydatabase.org/mdb-615/latest.zip"},
        {"source": "mirror"},
        "mirror",
    ],
)
def test_nothing_else_is_linked_as_a_saved_copy(fetch: object) -> None:
    """The site never hosts a copy, and a guessed or credentialed address is
    not a link a reader should follow."""
    assert _saved_copy_url(_artifact(fetch=fetch)) is None


def test_the_note_is_the_first_thing_above_the_agency_name() -> None:
    """First in the page, above the breadcrumb and the name (ADR 0085)."""
    html = _render_agency(_artifact(fetch=_mirror(_MDB_COPY)), liveness={"status": 404})
    assert html.count('<p class="feed-help">') == 1
    note = html.index('<p class="feed-help">')
    assert html.index('<div class="report-head">') < note < html.index('class="breadcrumb"')
    assert note < html.index('class="board-title"')


def test_a_page_whose_address_works_carries_no_note() -> None:
    html = _render_agency(_artifact(fetch=_mirror(_MDB_COPY)), liveness={"status": 304})
    assert "feed-help" not in html


def test_the_new_lines_have_their_styles() -> None:
    css = (Path(__file__).resolve().parents[2] / "web" / "src" / "styles.css").read_text()
    assert ".watch-line {" in css and ".feed-help {" in css
