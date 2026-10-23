"""Per-state NTD Report Year 2026 pages (/ntd/states/<slug>/).

A state page lists every tracked feed in the state with its shapes.txt and
agency_id checks. The two properties worth defending are that a feed nobody
measured never reads as a pass or a failure (it is listed as not checked and
left out of every count), and that a state with too few measured feeds gets no
page at all rather than a thin one.
"""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.ntd import (
    MIN_STATE_PAGE_FEEDS,
    state_pages,
    state_slug,
)
from scorecard_pipeline.render_site import (
    _FEDERAL_REGISTER_RY2026_PROPOSAL,
    _render_ntd_page,
    _render_ntd_state_page,
    _render_shapes_page,
)


def _art(
    agency_id: str,
    state: str,
    total: int | None,
    with_shape: int = 0,
    *,
    country: str = "US",
    agency_ids: list[str] | None = None,
) -> dict[str, Any]:
    art: dict[str, Any] = {
        "agency": {"id": agency_id, "name": f"Agency {agency_id}", "state": state},
        "feed": {"reachable": True, "static_url": "https://ex.org/g.zip"},
        "categories": {
            "correctness": {"status": "measured", "findings": []},
            "freshness": {"status": "measured", "details": {"days_until_expiry": 90}},
        },
    }
    if country != "US":
        art["agency"]["country"] = country
    if agency_ids is not None:
        art["ntd_id_alignment"] = {"status": "unknown", "detail": "", "feed_agency_ids": agency_ids}
    if total is not None:
        art["shapes_readiness"] = {"total_trips": total, "trips_with_shape": with_shape}
    return art


def _five(state: str = "Iowa") -> list[dict[str, Any]]:
    return [_art(f"{state[:2].lower()}{i}", state, 10, 10, agency_ids=["x"]) for i in range(5)]


def test_slug_is_lowercase_hyphenated() -> None:
    assert state_slug("District of Columbia") == "district-of-columbia"
    assert state_slug("New Hampshire") == "new-hampshire"


def test_a_state_below_the_threshold_gets_no_page() -> None:
    arts = _five()[: MIN_STATE_PAGE_FEEDS - 1]
    assert state_pages(arts) == {}
    assert list(state_pages(_five())) == ["Iowa"]


def test_unchecked_feeds_do_not_count_toward_the_threshold() -> None:
    # Four measured feeds plus any number of unmeasured ones is still four.
    arts = _five()[: MIN_STATE_PAGE_FEEDS - 1] + [_art(f"u{i}", "Iowa", None) for i in range(6)]
    assert state_pages(arts) == {}
    # A feed with no trips is unmeasurable too.
    arts = [*_five()[: MIN_STATE_PAGE_FEEDS - 1], _art("empty", "Iowa", 0)]
    assert state_pages(arts) == {}


def test_non_us_and_unlocated_feeds_are_never_listed() -> None:
    arts = [*_five(), _art("ca1", "Iowa", 10, 10, country="CA"), _art("lost", "", 10, 10)]
    pages = state_pages(arts)
    assert [r.id for r in pages["Iowa"]].count("ca1") == 0
    assert "Unlocated" not in pages and "" not in pages


def test_worst_feeds_sort_first_and_unchecked_last() -> None:
    arts = [
        _art("a-full", "Iowa", 10, 10),
        _art("b-none", "Iowa", 10, 0),
        _art("c-part", "Iowa", 10, 4),
        _art("d-unchecked", "Iowa", None),
        _art("e-full", "Iowa", 5, 5),
        _art("f-full", "Iowa", 5, 5),
    ]
    rows = state_pages(arts)["Iowa"]
    assert [r.id for r in rows] == ["b-none", "c-part", "a-full", "e-full", "f-full", "d-unchecked"]
    unchecked = rows[-1]
    assert unchecked.shapes is None
    assert unchecked.trips_with_shape is None and unchecked.total_trips is None


def test_agency_id_is_none_when_it_was_never_read() -> None:
    rows = state_pages([*_five(), _art("noid", "Iowa", 10, 10)])["Iowa"]
    by_id = {r.id: r for r in rows}
    assert by_id["noid"].agency_id is None
    assert by_id["io0"].agency_id == "ready"
    # An agency.txt with no agency_id is a measured failure, not an absence.
    blank = _art("blank", "Iowa", 10, 10, agency_ids=[])
    rows = state_pages([*_five(), blank])["Iowa"]
    assert {r.id: r for r in rows}["blank"].agency_id == "not_ready"


def test_page_counts_only_measured_feeds_and_lists_the_rest_as_not_checked() -> None:
    arts = [*_five(), _art("none1", "Iowa", 10, 0), _art("part1", "Iowa", 10, 4)]
    arts += [_art("skip1", "Iowa", None)]
    rows = state_pages(arts)["Iowa"]
    html = _render_ntd_state_page("Iowa", rows)
    assert "Of the 7 Iowa feeds" in html
    assert "<strong>5 carry a shape for every trip</strong>" in html
    assert "1 cover some trips, and 1 has no shapes yet" in html
    assert "1 of the 8 feeds listed has not been checked" in html
    assert "(4 of 10 trips have one)" in html
    # The unchecked row reads as unchecked in both columns, never as 0 or N/A.
    row = html.split('href="/agency/skip1/"')[1].split("</tr>")[0]
    assert row.count("Not checked yet") == 2
    assert "N/A" not in html and ">0<" not in row
    # No compliance claim and no filing date.
    assert "out of compliance" in html  # the disclaimer says this is NOT a finding
    assert "not an official compliance" in html


def test_negative_control_counts_would_change_if_an_unchecked_feed_were_counted() -> None:
    """Sabotage the population (count the unmeasured feed as a pass) and show
    the assertion in the test above would no longer hold."""
    arts = [*_five(), _art("skip1", "Iowa", None)]
    rows = state_pages(arts)["Iowa"]
    honest = _render_ntd_state_page("Iowa", rows)
    sabotaged_rows = [
        r if r.shapes is not None else type(r)(r.id, r.name, "ready", 1, 1, r.agency_id)
        for r in rows
    ]
    assert sabotaged_rows != rows  # the sabotage applied
    sabotaged = _render_ntd_state_page("Iowa", sabotaged_rows)
    assert "Of the 5 Iowa feeds" in honest
    assert "Of the 5 Iowa feeds" not in sabotaged
    assert "Of the 6 Iowa feeds" in sabotaged


def test_pages_quote_the_notice_and_carry_the_flex_caveat_not_the_each_route_claim() -> None:
    """The final notice says "make the shapes.txt file mandatory" and nothing about
    routes, trips or Flex. The pages say that, not "a file for each route"."""
    rows = state_pages(_five())["Iowa"]
    state_html = _render_ntd_state_page("Iowa", rows)
    shapes = {
        "total": 5,
        "ready": 5,
        "at_risk": 0,
        "not_ready": 0,
        "pct_ready": 100.0,
        "by_state": {"Iowa": {"ready": 5, "at_risk": 0, "not_ready": 0, "total": 5}},
    }
    explainer_html = _render_shapes_page(shapes, {"Iowa": "/ntd/states/iowa/"})
    for html in (state_html, explainer_html):
        assert "for each route" not in html
        assert "the shapes.txt file mandatory" in html
        assert "does not mention GTFS-Flex" in html
        assert "reported on its own row as a Flex-only feed" in html
        assert "stays in the count" in html
    # Negative control: the old, unsourced sentence is what the check rejects.
    old = state_html.replace(
        "FTA's final notice says it is making",
        "FTA's notice describes shapes.txt as a file for each route. It is making",
    )
    assert old != state_html  # the sabotage applied
    assert "for each route" in old


def test_state_page_head_fits_the_seo_contract_for_the_longest_name() -> None:
    rows = state_pages(_five("District of Columbia"))["District of Columbia"]
    html = _render_ntd_state_page("District of Columbia", rows)
    title = html.split("<title>")[1].split("</title>")[0]
    assert 15 <= len(title) <= 60, title
    desc = html.split('<meta name="description" content="')[1].split('"')[0]
    assert 50 <= len(desc) <= 155, desc
    assert (
        'rel="canonical" href="https://gtfsscorecard.org/ntd/states/district-of-columbia/"' in html
    )


def test_hubs_link_only_to_states_that_have_a_page() -> None:
    shapes = {
        "total": 6,
        "ready": 5,
        "at_risk": 0,
        "not_ready": 1,
        "pct_ready": 83.3,
        "by_state": {
            "Iowa": {"ready": 5, "at_risk": 0, "not_ready": 0, "total": 5},
            "Utah": {"ready": 0, "at_risk": 0, "not_ready": 1, "total": 1},
        },
    }
    html = _render_shapes_page(shapes, {"Iowa": "/ntd/states/iowa/"})
    assert '<a href="/ntd/states/iowa/">Iowa</a>' in html
    assert "<td>Utah</td>" in html
    assert "/ntd/states/utah/" not in html
    # Without any state pages the explanatory note is absent too.
    assert "A state name that is a link" not in _render_shapes_page(shapes)
    payload = {
        "total": 1,
        "ready": 1,
        "at_risk": 0,
        "not_ready": 0,
        "pct_ready": 100.0,
        "by_state": {"Iowa": {"ready": 1, "at_risk": 0, "not_ready": 0, "total": 1}},
    }
    assert '<a href="/ntd/states/iowa/">Iowa</a>' in _render_ntd_page(
        payload, None, {"Iowa": "/ntd/states/iowa/"}
    )
    assert "/ntd/states/" not in _render_ntd_page(payload)


def test_one_third_estimate_is_attributed_to_the_october_2024_proposal() -> None:
    html = _render_shapes_page({"total": 0, "by_state": {}})
    assert "proposed the requirement in October 2024" in html
    assert f'<a href="{_FEDERAL_REGISTER_RY2026_PROPOSAL}">' in html
    assert "just over a third" not in html
    assert "finalized the rule in July 2025, it estimated" not in html


def test_waiver_is_described_as_a_2022_proposal_not_a_current_entitlement() -> None:
    page = _render_shapes_page({"total": 0, "by_state": {}})
    assert "In 2022 FTA proposed" in page
    assert "can request a one-year waiver" not in page
    ntd = _render_ntd_page({"total": 0})
    assert "In 2022 FTA proposed" in ntd
    assert "can request a one-year waiver" not in ntd


def test_writer_emits_one_page_per_qualifying_state_and_returns_the_links() -> None:
    from scorecard_pipeline.render_site import _write_ntd_state_pages

    written: dict[str, tuple[str, str | None]] = {}

    def fake_write(rel: str, content: str, url: str | None = None, **_: Any) -> None:
        written[rel] = (content, url)

    arts = [*_five("Iowa"), *_five("Utah")[:3]]
    links = _write_ntd_state_pages(fake_write, arts)
    assert links == {"Iowa": "/ntd/states/iowa/"}
    assert list(written) == ["ntd/states/iowa/index.html"]
    assert written["ntd/states/iowa/index.html"][1] == "https://gtfsscorecard.org/ntd/states/iowa/"
    # Negative control: with the qualifying state's feeds removed nothing is written.
    written.clear()
    assert _write_ntd_state_pages(fake_write, _five("Utah")[:3]) == {}
    assert written == {}
