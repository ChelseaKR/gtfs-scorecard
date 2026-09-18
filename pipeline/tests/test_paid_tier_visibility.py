"""Where the paid tier may appear, where it may not, and who checks it.

The program report bundle (ADR 0049) is the only thing on this site that costs
money, and the site's credibility rests on two claims that a visibility change
is the easiest way to break:

1. **Agency-facing scoring is free.** An agency's call brief, its board
   one-pager, and the self-contained report it hands a board carry no offer at
   all. Its scorecard page carries exactly one, the program panel addressed to
   people who support several agencies, placed after the evidence and the
   standards section and never in the hero beside the grade (ADR 0058, which
   narrowed the earlier "no offer anywhere on an agency page" rule). These
   tests assert the absences and the one exception's shape, because an absence
   is exactly what no accessibility scan, golden diff, or link checker will
   notice going away.
2. **A price lives in web/bundle/plan.json and nowhere else.** A price copied
   into a template is a price that keeps selling after the plan changes. A
   price *generated* from that file into a delimited region, by
   ``make sync-bundle-offers``, and compared byte for byte against the
   generator on every run, is not a copy — it is a rendering, and it changes
   when the plan changes or the build fails. The sweep below subtracts exactly
   those regions and nothing else.

The positive half is here too: the tier is meant to be *findable*, so the
pages a reader actually lands on must reach it, and the accessibility gate must
cover every page that renders a purchase surface rather than only the two that
had one when the tier launched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import yaml

from scorecard_pipeline.site_shell import (
    BUNDLE_GENERATED_REGION_RES,
    FOOTER_HTML,
    FOOTER_HTML_ES,
    FOOTER_HTML_WITHOUT_US_TOOLS,
    bundle_noscript_region,
    bundle_offers_region,
)

# pipeline/tests/test_paid_tier_visibility.py -> parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"

_BUNDLE_HREF = 'href="/bundle/"'
# The sentence /support/, /bundle/, and ADR 0049 all use, verbatim.
_INDEPENDENCE = "buys no influence over grades, methodology, or which agencies are listed"
_FOOTER_TAG = '<footer class="site-footer">'
# A page the crawler is told not to index is not an inbound route to anything.
# Read off the page's own robots tag rather than a path list, so a page that
# changes its mind is counted correctly on the same render.
_NOINDEX_RE = re.compile(r'<meta name="robots"[^>]*noindex')
_PROGRAM_HREF_RE = re.compile(r'href="/program/([a-z0-9-]+)/"')


def _plan() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((_WEB / "bundle" / "plan.json").read_text()))


def _configured_rollup_ids() -> set[str]:
    """Every rollup slug rollups.yaml declares.

    Derived, never listed here: a hand-maintained copy goes stale the next time
    a rollup is added, and a gate reading a stale list is a gate that cannot
    fail.
    """
    document = yaml.safe_load((_REPO / "rollups.yaml").read_text())
    return {str(entry["id"]) for entry in (document or {}).get("rollups", [])}


def _published_rollup_ids() -> set[str]:
    """Every rollup the render actually wrote a page for, from the goldens."""
    program = _GOLDENS / "program"
    return {
        child.name
        for child in program.iterdir()
        if child.is_dir() and (child / "index.html").is_file()
    }


def _program_links_from_indexable_pages(root: Path | None = None) -> tuple[set[str], int]:
    """Rollup slugs linked from a rendered page's own content, and pages swept.

    Two rules decide what counts, and both are the difference between a gate and
    a decoration:

    * **Split at the shared footer.** Every page on the site carries
      /program/all/ down there, so a sweep over whole documents would call every
      rollup reachable forever on the strength of one footer link. Only the
      content above the footer counts as a route. A page with no footer at all
      must prove it is one of the retired-URL redirect stubs, which carry no
      chrome; otherwise the split found nothing and the caller would be reading
      a whole document while believing it read a body.
    * **Skip noindex pages.** The call brief already links its state rollup and
      is `noindex,follow`. Counting it would report the rollups reachable while
      no indexable page named one, which is exactly the state measured on
      2026-09-12.

    Neither rule is exercised by the committed fixture -- its three agencies
    carry no state, so no golden brief links a rollup at all, and the fixture is
    exactly where both failures are impossible. ``root`` exists so the rules
    themselves can be tested against pages built to break them; see
    ``test_the_reach_sweep_counts_only_a_page_own_content``.
    """
    root = root or _GOLDENS
    linked: set[str] = set()
    swept = 0
    for path in sorted(root.rglob("*.html")):
        relative = path.relative_to(root)
        if relative.parts[0] == "report":
            continue  # the board report is a document, not a page on this site
        html = path.read_text()
        if _NOINDEX_RE.search(html):
            continue
        head, separator, _footer = html.partition(_FOOTER_TAG)
        if not separator:
            assert 'http-equiv="refresh"' in html, (
                f"{relative}: no shared footer and not a redirect stub, so the "
                "split below would read the whole document as page content"
            )
            continue
        swept += 1
        linked.update(_PROGRAM_HREF_RE.findall(head))
    return linked, swept


# --- the tier is findable -------------------------------------------------


def test_the_shared_footer_reaches_the_paid_tier_and_says_it_is_paid() -> None:
    """The footer is the only surface that reaches all ~2,000 pages at once.

    It carries the word "paid" in the link text on purpose: a reader must know
    what is on the other side before they click, not after.
    """
    for footer in (FOOTER_HTML, FOOTER_HTML_WITHOUT_US_TOOLS):
        assert _BUNDLE_HREF in footer
        assert "Board report bundle (paid)" in footer
        assert _INDEPENDENCE in footer


def test_the_spanish_footer_deliberately_does_not_sell_anything() -> None:
    """/es/ is the site's only rider-facing page, and its footer is a short strip
    of the few destinations a Spanish reader can act on.

    The bundle is an English-only purchase made by program staff, so it is left
    out on purpose rather than by oversight. Recorded as a test because the
    absence is the decision: adding the link should be a deliberate edit here,
    not a footer tidy-up. Discovery does not depend on it either way, since
    /bundle/ is linked from every English page and listed in the sitemap.
    """
    assert "/bundle/" not in FOOTER_HTML_ES
    assert "bundle" not in FOOTER_HTML_ES.lower()


def test_the_footer_carries_no_price() -> None:
    """Prices come from plan.json at view time; the footer is static HTML on
    every page, so it can only ever carry a stale one."""
    products = _plan()["products"]
    assert isinstance(products, dict)
    for product in products.values():
        assert f"${product['price']}" not in FOOTER_HTML


def test_each_landing_surface_reaches_the_paid_tier() -> None:
    """The pages a reader arrives on, or goes to when asking "who is this
    for" and "what does it cost"."""
    for rel in (
        "index.html",  # the home page
        "about/index.html",
        "data/index.html",
        "support/index.html",
    ):
        assert _BUNDLE_HREF in (_WEB / rel).read_text(), rel

    # /tools/ and the program rollups are generated; assert the shipped output.
    assert _BUNDLE_HREF in (_GOLDENS / "tools" / "index.html").read_text()
    assert _BUNDLE_HREF in (_GOLDENS / "program" / "california" / "index.html").read_text()


def test_the_program_audience_pages_reach_the_tier_above_the_footer() -> None:
    """A footer link is a fallback, not a path. These four generated pages are
    where the tier's buyers arrive: someone writing feed quality into a contract
    (/procurement/), someone reading the corpus rather than one feed (/pulse/),
    someone comparing what this site offers (/tools/), and someone already
    looking at a whole program at once (/program/all/).

    Split on the shared footer, so moving the body link into the footer and
    calling it done fails here. The independence promise travels with the offer
    on every page this repo renders, which is why it is asserted beside it.
    """
    for rel in ("procurement/index.html", "pulse/index.html", "program/all/index.html"):
        html = (_GOLDENS / rel).read_text()
        head, sep, _footer = html.partition('<footer class="site-footer">')
        assert sep, f"{rel}: no shared footer found; the split below proves nothing"
        assert _BUNDLE_HREF in head, (
            f"{rel}: reaches the paid tier only through the shared footer. "
            "This page's reader is who the tier is for."
        )
        assert _INDEPENDENCE in head, (
            f"{rel}: names the paid tier without the independence sentence."
        )

    # /tools/ is rendered by pages_tools.py, which states the offer in its own
    # words inside a capability list; assert the link, not this file's wording.
    tools = (_GOLDENS / "tools" / "index.html").read_text()
    assert _BUNDLE_HREF in tools.partition('<footer class="site-footer">')[0]


def test_the_reach_sweep_counts_only_a_page_own_content(tmp_path: Path) -> None:
    """The two rules the gate below stands on, against pages built to break them.

    The committed fixture cannot exercise either: its agencies carry no state,
    so no golden call brief links a rollup, and the shared footer links only
    `all`, which is published anyway. A guard whose failure mode is unreachable
    from the fixture is a guard nobody has measured, so these pages are written
    here on purpose:

    * a footer-only link, which is how every page on the real site mentions
      /program/all/ and must never count as a route;
    * a `noindex` page with the link in its body, which is the call brief;
    * an indexable page with the link in its body, which is the only thing that
      does count;
    * a page with neither a footer nor a meta refresh, which means the split
      found nothing and the sweep must refuse rather than read the whole
      document as though it were page content.
    """
    footer = _FOOTER_TAG + '<a href="/program/in-the-footer/">rollups</a></footer>'

    (tmp_path / "footer-only").mkdir()
    (tmp_path / "footer-only" / "index.html").write_text(f"<main>nothing here</main>{footer}")
    (tmp_path / "brief").mkdir()
    (tmp_path / "brief" / "index.html").write_text(
        '<meta name="robots" content="noindex,follow">'
        '<main><a href="/program/noindex-only/">portfolio</a></main>' + footer
    )
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "index.html").write_text(
        '<main><a href="/program/counted/">portfolio</a></main>' + footer
    )
    (tmp_path / "stub").mkdir()
    (tmp_path / "stub" / "index.html").write_text(
        '<meta http-equiv="refresh" content="0; url=/pulse/">'
    )

    linked, swept = _program_links_from_indexable_pages(tmp_path)
    assert linked == {"counted"}
    # Two of the four: the noindex brief and the redirect stub are not routes.
    assert swept == 2

    (tmp_path / "chromeless").mkdir()
    (tmp_path / "chromeless" / "index.html").write_text(
        '<main><a href="/program/uncounted/">portfolio</a></main>'
    )
    try:
        _program_links_from_indexable_pages(tmp_path)
    except AssertionError as failure:
        assert "not a redirect stub" in str(failure)
    else:  # pragma: no cover - the sweep must refuse this page
        raise AssertionError("a page with no footer was swept as though it had one")


def test_every_published_program_rollup_is_reachable_from_an_indexable_page() -> None:
    """The reach metric, and the one that read **zero** the day it was written.

    Measured against the deployed site on 2026-09-12: 67 program rollups were in
    the sitemap, and the only /program/ link any page emitted was
    /program/all/, inside the shared footer. The other 66 had no inbound link
    from any indexable page at all. The index of them existed only inside the
    JavaScript app at /app/#/programs, which no crawler and no reader without
    JavaScript can follow, and /program/ itself returned 404.

    That is worth a gate precisely because presence was already solved: the
    offer reached 6,177 of 6,355 rendered pages, on the one page family nothing
    linked. A page in the sitemap that nothing links is a page a reader arrives
    at by guessing a URL.

    Both id sets are derived — one from rollups.yaml, one from what the render
    wrote — and the sweep asserts it found pages before concluding anything from
    them.
    """
    configured = _configured_rollup_ids()
    assert configured, "rollups.yaml declares no rollups; this gate would pass vacuously"

    published = _published_rollup_ids()
    assert published, "no rollup pages were rendered; this gate would pass vacuously"
    assert published <= configured, (
        f"rollup pages were rendered for ids rollups.yaml does not declare: "
        f"{sorted(published - configured)}"
    )

    linked, swept = _program_links_from_indexable_pages()
    assert swept > 20, f"the page sweep collapsed at {swept} pages; it would prove nothing"

    orphans = published - linked
    assert not orphans, (
        f"these rollups have no inbound link from any indexable page's own "
        f"content: {sorted(orphans)}. The shared footer does not count — it "
        "carries one rollup on every page and would make this gate unfailable."
    )


def test_the_program_index_is_itself_reachable_from_the_agency_directory() -> None:
    """The index gives 66 rollups their only route, so it needs one of its own.

    /agencies/ is the "Find an agency" nav stop and the obvious place to start
    for someone who supports many of them. Its own wayfinding line offered four
    other views of the same scorecards and did not mention the per-program one,
    which is how a reader serving forty agencies was told about a map and never
    about the page for their job.
    """
    head, separator, _footer = (
        (_GOLDENS / "agencies" / "index.html").read_text().partition(_FOOTER_TAG)
    )
    assert separator, "no shared footer found; the split below proves nothing"
    assert 'href="/program/"' in head, (
        "/agencies/ does not offer the program view among its other views of "
        "the same scorecards, so the rollup index is reachable only by guessing"
    )


def test_the_program_index_publishes_no_average_its_own_rollup_page_withholds() -> None:
    """One guard, two surfaces, and no number the data does not support.

    A rollup with no comparison cohort prints "average unavailable" on its own
    page. The index lists the same rollups in one line each, which is exactly
    the shape where a missing measurement gets rendered as a confident number:
    a bare `average_score` read straight out of the artifact would have printed
    one for every rollup whose page declines to. Both surfaces call
    ``_rollup_guarded_summary``; this asserts they agree on the output.
    """
    index_html = (_GOLDENS / "program" / "index.html").read_text()
    rows = re.findall(r'<li class="agency-card">.*?</li>', index_html, re.S)
    assert rows, "the program index rendered no rows; this test would prove nothing"

    published = _published_rollup_ids()
    listed = set(_PROGRAM_HREF_RE.findall(index_html))
    assert listed == published, (
        f"the index lists {sorted(listed)} but the render published {sorted(published)}"
    )

    for rollup_id in sorted(published):
        page = (_GOLDENS / "program" / rollup_id / "index.html").read_text()
        row = next(r for r in rows if f'href="/program/{rollup_id}/"' in r)
        assert ("average unavailable" in page) == ("average unavailable" in row), (
            f"{rollup_id}: the index and the rollup page disagree about whether "
            "this group has a publishable average"
        )


def test_the_a11y_gate_opens_every_page_that_names_the_paid_tier_in_its_content() -> None:
    """Derived from the rendered pages, because a list is how one got missed.

    /program/all/ rendered the same offer block as /program/california/ and only
    the second was scanned. Every page that states the offer in its own content
    is a purchase surface for this purpose, whether or not it renders a plan
    grid — a11y.yml's own derived set reads `data-plan-summary`, which the
    rollup pages do not carry.

    A page that genuinely cannot be scanned may sit in `_unscannable` in the
    same config, and must carry a reason and a review date. That is deliberately
    not a free pass: a gap with a written reason in the file the gate reads is
    worth more than a silently shorter list, and an entry naming a page that no
    longer states the offer fails below rather than lingering.
    """
    config = json.loads((_REPO / ".pa11yci.json").read_text())
    scanned = {
        (entry["url"] if isinstance(entry, dict) else entry).replace("http://127.0.0.1:8080", "")
        for entry in config["urls"]
    }
    assert len(scanned) > 20, "the a11y config collapsed; this test would prove nothing"

    offer_pages = set()
    for path in sorted(_GOLDENS.rglob("*.html")):
        relative = path.relative_to(_GOLDENS)
        if relative.parts[0] == "report":
            continue
        head, separator, _footer = path.read_text().partition(_FOOTER_TAG)
        if not separator:
            continue
        if _BUNDLE_HREF in head:
            offer_pages.add("/" + relative.as_posix().removesuffix("index.html"))
    assert offer_pages, "no generated page names the paid tier; this would prove nothing"

    unscannable = config.get("_unscannable", {})
    for served, waiver in unscannable.items():
        assert served in offer_pages or served in scanned, (
            f"{served} is recorded as unscannable but is neither scanned nor an "
            "offer page; delete the entry rather than leaving it to rot"
        )
        assert served not in scanned, f"{served} is both scanned and waived"
        assert len(str(waiver.get("reason", ""))) > 120, (
            f"{served}: an exemption from the a11y gate needs a reason that says "
            "what was measured, not a label"
        )
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(waiver.get("last_reviewed", ""))), served
        assert waiver.get("review"), f"{served}: say what would let this be scanned again"

    missing = offer_pages - scanned - set(unscannable)
    assert not missing, (
        f"these pages state the offer but the axe gate never opens them: {sorted(missing)}"
    )


def test_the_paid_tier_pointer_is_one_shared_string_not_four_paraphrases() -> None:
    """Two promises ("free for every agency", "buys no influence") are the whole
    basis for selling anything here, so every generated surface says them the
    same way. Constants, checked through the rendered pages: a copy-pasted
    variant that drifts one word fails the assertions above, and a second
    constant that says it differently fails this one.
    """
    from scorecard_pipeline.render_site import (
        _BUNDLE_FREE_NOTE,
        _BUNDLE_INDEPENDENCE,
        _bundle_pointer,
    )

    assert _INDEPENDENCE in _BUNDLE_INDEPENDENCE
    assert "free" in _BUNDLE_FREE_NOTE

    pointer = _bundle_pointer("Lead sentence?", "anchor text")
    assert '<a href="/bundle/">anchor text</a>' in pointer
    assert _BUNDLE_FREE_NOTE in pointer
    assert _BUNDLE_INDEPENDENCE in pointer

    # Descriptive, and different per page: one anchor string repeated everywhere
    # reads as a banner and tells a reader nothing about where they are going.
    anchors = set()
    rels = (
        "procurement/index.html",
        "pulse/index.html",
        "program/all/index.html",
        "program/index.html",
    )
    for rel in rels:
        head = (_GOLDENS / rel).read_text().partition('<footer class="site-footer">')[0]
        anchors.update(re.findall(r'<a href="/bundle/">([^<]+)</a>', head))
    assert len(anchors) == len(rels), anchors
    for anchor in anchors:
        assert len(anchor.split()) >= 4, anchor
        assert "here" not in anchor.lower()


def test_the_app_says_what_its_static_twin_says_about_the_paid_tier() -> None:
    """web/src/app.js renders the same rollups the static site publishes.

    #/program/<id> is the app's drawing of /program/<id>/, the page whose static
    twin carries the offer, and #/programs is the index the static site now
    publishes at /program/. Until this landed, app.js contained the string
    "bundle" zero times: one view of one page named the tier and the other did
    not, which is a defect regardless of whether anyone buys anything.

    The two promises are pinned against the Python constants rather than a copy
    of them, so a reworded promise fails here instead of quietly shipping two
    versions of the same sentence. The app must not quote a price: plan.json
    owns those, and the sweep below would catch it anyway.
    """
    from scorecard_pipeline.render_site import _BUNDLE_FREE_NOTE, _BUNDLE_INDEPENDENCE

    app = (_WEB / "src" / "app.js").read_text()
    assert _BUNDLE_INDEPENDENCE in app
    assert _BUNDLE_FREE_NOTE in app
    assert app.count(_BUNDLE_INDEPENDENCE) == 1, (
        "the independence promise is written twice in app.js; it is a constant"
    )
    assert '<a href="/bundle/">' in app

    # And only on the two group views. A per-agency view in the app is the same
    # reader as /agency/<id>/, where the tier stays out of the body, and
    # #/cohort is a reader's own followed list -- an owner call, deliberately
    # not taken here.
    bodies = dict(
        zip(
            re.findall(r"^(?:async )?function (\w+)\(", app, re.M),
            re.split(r"^(?:async )?function \w+\(", app, flags=re.M)[1:],
            strict=True,
        )
    )
    for view in ("renderScorecard", "renderCohort"):
        assert view in bodies, f"{view} was renamed; this absence test now checks nothing"
        body = bodies[view]
        assert "/bundle/" not in body and "bundlePointer(" not in body, (
            f"{view} names the paid tier"
        )
    for view in ("renderPrograms", "renderProgram"):
        body = bodies[view]
        assert "/bundle/" in body or "bundlePointer(" in body, (
            f"{view} renders a page whose static twin names the tier, and says nothing"
        )


def test_the_app_rollup_offer_reads_word_for_word_like_the_static_rollup() -> None:
    """#/program/<id> and /program/<id>/ are two renderings of one page.

    The offer block is authored twice, once in Python and once in JavaScript,
    which is the shape where two surfaces drift into saying different things
    about the same purchase. Compared as text rather than as markup, so the
    `reveal` class and the template interpolation do not count as a difference
    and a changed sentence does.
    """
    from scorecard_pipeline.render_site import _BUNDLE_INDEPENDENCE, _ROLLUP_BUNDLE_SECTION

    def visible(markup: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).strip()

    app = (_WEB / "src" / "app.js").read_text()
    start = app.index('<section aria-labelledby="bundle-h"')
    end = app.index("</section>", start) + len("</section>")
    rendered = app[start:end].replace("${BUNDLE_INDEPENDENCE}", _BUNDLE_INDEPENDENCE)
    assert "${" not in rendered, "an unsubstituted interpolation would compare as literal text"

    assert visible(rendered) == visible(_ROLLUP_BUNDLE_SECTION)


def test_the_home_page_states_the_tier_as_a_section_not_a_passing_mention() -> None:
    html = (_WEB / "index.html").read_text()
    assert 'id="program-tier-h"' in html
    assert "data-plan-summary" in html
    assert 'src="/src/plan-summary.js"' in html
    assert _INDEPENDENCE in html


# --- and it stays away from a specific agency's grade ----------------------


_PROGRAM_PANEL_RE = re.compile(
    r'<section class="action-panel program-offer" aria-labelledby="program-offer-h">.*?</section>',
    re.S,
)


def test_agency_pages_name_the_paid_tier_only_in_the_program_panel() -> None:
    """The call brief and the on-site board one-pager are the free product and
    name nothing paid above the shared footer. The scorecard page names it in
    exactly one place, the program panel (ADR 0058), and that panel sits after
    the standards section: below the grade, the fixes, and the evidence.

    Split on the footer rather than searching the whole document, or this test
    would pass the moment the footer link were moved into the page body. The
    panel is subtracted by its exact opening tag, once, so a second offer, or
    a /bundle/ link typed anywhere else on the page, still fails.
    """
    for rel in (
        "agency/unitrans/brief/index.html",
        "agency/unitrans/board/index.html",
        "agency/yolobus/brief/index.html",
        "agency/yolobus/board/index.html",
        "agency/barrie-transit/brief/index.html",
        "agency/barrie-transit/board/index.html",
    ):
        html = (_GOLDENS / rel).read_text()
        head, sep, _footer = html.partition(_FOOTER_TAG)
        assert sep, f"{rel}: no shared footer found; the split below proves nothing"
        assert "/bundle/" not in head, (
            f"{rel}: the paid tier is named on an agency's brief or board page. "
            "Those stay free of any offer; the scorecard's program panel is the one place."
        )
        assert "program-offer" not in head, f"{rel}: carries the program panel"

    for rel in (
        "agency/unitrans/index.html",
        "agency/yolobus/index.html",
        "agency/barrie-transit/index.html",
    ):
        html = (_GOLDENS / rel).read_text()
        head, sep, _footer = html.partition(_FOOTER_TAG)
        assert sep, f"{rel}: no shared footer found; the split below proves nothing"
        panels = _PROGRAM_PANEL_RE.findall(head)
        assert len(panels) == 1, f"{rel}: expected exactly one program panel, found {len(panels)}"
        assert "/bundle/" in panels[0], f"{rel}: the program panel no longer reaches /bundle/"
        assert _INDEPENDENCE in panels[0], f"{rel}: the panel dropped the independence promise"
        rest = _PROGRAM_PANEL_RE.sub("", head, count=1)
        assert "/bundle/" not in rest, (
            f"{rel}: the paid tier is named outside the program panel, "
            "which is the only place on a scorecard page it may appear."
        )
        assert head.index('id="standards-h"') < head.index('id="program-offer-h"'), (
            f"{rel}: the program panel moved above the standards section, toward the grade"
        )
        hero_end = head.index('class="report-route"')
        assert "/bundle/" not in head[:hero_end], f"{rel}: an offer reached the hero"


def test_the_self_contained_board_report_carries_no_purchase_link() -> None:
    """report.py's document travels off this site: it is emailed, printed, and
    put in board packets, and it is also the thing the bundle sells. A purchase
    link in its methodology footer would advertise the bundle inside the very
    artifact a program bought, to the agency whose grade it carries.

    Deliberate owner-visible policy: the footer is unchanged, and this test is
    the record of that decision rather than an accident waiting to be undone.
    """
    for golden in sorted((_GOLDENS / "report").glob("*.html")):
        text = golden.read_text()
        assert "/bundle/" not in text, golden.name
        assert "buy" not in text.lower(), golden.name


def test_the_printed_one_pager_drops_the_footer_entirely() -> None:
    """On paper the shared footer is not rendered at all, so the board packet
    an agency prints from its own page carries no link to anything paid."""
    css = (_WEB / "src" / "styles.css").read_text()
    print_block = re.search(r"@media print \{(.*?)\n\}", css, re.S)
    assert print_block is not None
    assert re.search(r"\.site-footer[^{]*\{[^}]*display:\s*none", print_block.group(1))


def test_the_program_rollup_names_the_tier_after_the_member_list() -> None:
    """The one generated page family that names the tier in its body. It is a
    group view, read by the people the tier is for, and the offer sits after
    the member list rather than beside any one grade."""
    html = (_GOLDENS / "program" / "california" / "index.html").read_text()
    assert html.index('id="members-h"') < html.index('id="bundle-h"')
    assert _INDEPENDENCE in html
    assert "free, printable board one-pager on its own page" in html


# --- every price comes from plan.json -------------------------------------


def _generated_regions(text: str) -> list[str]:
    """Every ``make sync-bundle-offers`` region in ``text``, in file order."""
    return [
        match.group(0)
        for pattern in BUNDLE_GENERATED_REGION_RES
        for match in pattern.finditer(text)
    ]


def _without_generated_regions(text: str) -> str:
    """``text`` with those regions removed, so a sweep sees only typed markup."""
    for pattern in BUNDLE_GENERATED_REGION_RES:
        text = pattern.sub(" ", text)
    return text


def test_no_template_carries_a_price_that_plan_json_owns() -> None:
    """The design rule from ADR 0049: "/bundle/ and /bundle/setup/ read every
    price from web/bundle/plan.json". Every new surface reads it the same way,
    so switching the tier off stays a data change.

    Searched as the rendered amount ("$149"), which is the form that would
    actually mislead a reader, rather than the bare digits.

    **The one exemption, and why it is not a hole.** ``/bundle/`` states its
    prices in the served bytes -- issue #417 measured a page selling four plans
    whose HTML contained no amount at all, which is how a crawler, an assistant,
    and a reader with scripting off all saw a sales page that sold nothing.
    Those amounts are generated into two marker-delimited regions by
    ``make sync-bundle-offers`` and are re-derived from ``plan.json`` here on
    every run: a hand-edit inside the markers fails just as a hand-typed price
    outside them does, and a price changed in ``plan.json`` without a re-sync
    fails too. The sweep therefore subtracts the regions rather than the file,
    and asserts which file was allowed to have any -- so the exemption cannot
    widen to a second page, or to the rest of this one, without failing here.
    """
    plan = _plan()
    products = plan["products"]
    assert isinstance(products, dict)
    amounts = [f"${product['price']}" for product in products.values()]
    assert amounts, "plan.json lists no products; this test would pass vacuously"

    searched = [
        *(path for path in _WEB.rglob("*.html") if "/agency/" not in path.as_posix()),
        *(_WEB / "src").glob("*.js"),
        *(_REPO / "pipeline" / "src" / "scorecard_pipeline").glob("*.py"),
    ]
    assert len(searched) > 100, "the file sweep collapsed; it would prove nothing"

    exempted: dict[str, list[str]] = {}
    for path in searched:
        text = path.read_text(errors="ignore")
        # A generated region is a markup construct. The subtraction applies only
        # to markup, so the generator's own source -- which necessarily contains
        # the marker strings it writes -- is still swept in full. It is, and it
        # caught two prices typed into docstrings while this was being written.
        if path.suffix == ".html":
            regions = _generated_regions(text)
            if regions:
                exempted[path.relative_to(_REPO).as_posix()] = regions
            text = _without_generated_regions(text)
        for amount in amounts:
            assert amount not in text, (
                f"{path}: carries the literal price {amount} outside any generated region"
            )

    # Exactly one file may hold generated regions, and its regions must be what
    # the generator produces from the plan as it stands right now. Without this
    # the subtraction above would be blanket permission to type anything between
    # two comment markers.
    assert list(exempted) == ["web/bundle/index.html"], (
        f"generated price regions appeared in {sorted(exempted)}; only /bundle/ may carry them"
    )
    assert exempted["web/bundle/index.html"] == [
        bundle_offers_region(plan),
        bundle_noscript_region(plan),
    ], "the exempted regions are not what `make sync-bundle-offers` writes from plan.json"


# --- and the accessibility gate sees what was added -----------------------


def test_the_a11y_gate_covers_every_page_that_renders_a_purchase_surface() -> None:
    """A purchase control rendered after a fetch is invisible to a scan that
    does not wait for it, and a page that is not in the config is not scanned
    at all. Derive the page set from the markup instead of maintaining a list:
    adding a plan summary to a sixth page fails here until the gate covers it.
    """
    config = json.loads((_REPO / ".pa11yci.json").read_text())
    waits = {}
    for entry in config["urls"]:
        url = entry["url"] if isinstance(entry, dict) else entry
        waits[url.replace("http://127.0.0.1:8080", "")] = (
            entry.get("wait", 0) if isinstance(entry, dict) else 0
        )

    rendered_from_plan_json = set()
    for path in _WEB.rglob("*.html"):
        text = path.read_text(errors="ignore")
        if "data-plan-summary" in text or 'id="plan-grid"' in text:
            served = "/" + path.relative_to(_WEB).as_posix().removesuffix("index.html")
            rendered_from_plan_json.add(served.replace("/index.html", "/"))

    assert rendered_from_plan_json >= {"/", "/bundle/", "/support/"}
    for served in sorted(rendered_from_plan_json):
        assert served in waits, f"{served} renders a plan but the axe gate never opens it"
        assert waits[served] >= 1000, (
            f"{served} renders its plan after a fetch; without a wait the scan "
            "examines a page that has no purchase surface on it yet"
        )
