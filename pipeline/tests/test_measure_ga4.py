"""Google Analytics 4, held from the script side (ADR 0056).

GA4 is the second block of ``web/src/measure.js``, so it reaches every page
the measurement script reaches, and ``check_site_seo.py`` already holds that
script to exactly one copy on every page and none on a redirect stub. These
tests hold what that gate cannot see:

- where the measurement id comes from (``measurement_ga4_id`` in
  ``site-seo.json``) and the one line a deploy writes it into;
- that with no id, nothing loads;
- that with an id, the Google loader is added once, with the consent defaults
  and the config this ADR promises, and with no query string or full referrer;
- that Global Privacy Control, Do Not Track, and a page served from this
  machine each stop it before anything loads.

The behaviour tests execute the rendered script in Node against a stub page,
the same harness shape ``test_frontend_guidance.py`` uses. Each negative
control asserts that its sabotage changed the script before it reads the
verdict, so a control that silently did nothing cannot pass.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.cli import main
from scorecard_pipeline.site_shell import (
    ANALYTICS_OPT_OUT_HTML,
    ANALYTICS_OPT_OUT_HTML_ES,
    FOOTER_HTML,
    FOOTER_HTML_ES,
    FOOTER_HTML_WITHOUT_US_TOOLS,
    GA4_ID_SETTING,
    GA4_LOADER_HOST,
    MEASURE_SCRIPT_PATH,
    MEASURED_STATIC_PAGES,
    _page,
    ga4_measurement_id,
    render_measure_script,
)

_REPO = Path(__file__).resolve().parents[2]
_SHIM = (_REPO / "web" / MEASURE_SCRIPT_PATH).read_text()
_GA4_MARKER = "// Google Analytics 4 (docs/decisions/0056"
_GA4_BLOCK = _SHIM[_SHIM.index(_GA4_MARKER) :]
# Where the PostHog block begins; the opt-out control runs before it.
_POSTHOG_START = (
    '(function () {\n  "use strict";\n\n  // Written at deploy time from the POSTHOG_KEY'
)
_GOLDEN_SITE = _REPO / "pipeline" / "tests" / "fixtures" / "golden_site" / "web"
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"
_ABOUT = (_REPO / "web" / "about" / "index.html").read_text()

_ID = "G-TEST0A1B2C"
_KEY = "phc_TestKey0123456789abcdefghijklmnopqrstuv"  # gitleaks:allow (fixture key, not real)
_ID_LINE = '  var GA4_ID = ""; // measure:ga4-id'
_GPC_GUARD = "  if (nav.globalPrivacyControl === true) return;\n"
_DNT_GUARD = (
    '  if (nav.doNotTrack === "1" || win.doNotTrack === "1" || nav.msDoNotTrack === "1") return;\n'
)
_STOPPED_GUARD = 'if (doc.documentElement.hasAttribute("data-measure-stopped")) return;'
_EMPTY_GUARDS = ("  if (!GA4_ID) return;\n", "  if (!/^G-[A-Z0-9]+$/.test(GA4_ID)) return;\n")

# The European Economic Area (the 27 EU members, Iceland, Liechtenstein and
# Norway), the United Kingdom and Switzerland.
_EU = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
}  # fmt: skip
_CONSENT_REQUIRED = _EU | {"IS", "LI", "NO", "GB", "CH"}
_ADS_DENIED = {"ad_storage": "denied", "ad_user_data": "denied", "ad_personalization": "denied"}


# --- where the id comes from ------------------------------------------------


def test_the_committed_shim_carries_no_id() -> None:
    """The id reaches the site only through the deploy render, so the copy a
    local server or the accessibility build serves never loads Google."""
    assert re.search(r'^\s*var GA4_ID = ""; // measure:ga4-id$', _SHIM, re.MULTILINE)
    assert not re.search(r"G-[A-Z0-9]{4,}", _SHIM)


def test_the_repository_config_carries_a_well_formed_id() -> None:
    raw = json.loads((_REPO / "site-seo.json").read_text(encoding="utf-8"))
    assert GA4_ID_SETTING in raw
    assert raw["measurement_ga4_host"] == GA4_LOADER_HOST
    value = ga4_measurement_id(_REPO / "site-seo.json")
    assert value == raw[GA4_ID_SETTING]
    assert value == "" or re.fullmatch(r"G-[A-Z0-9]{4,16}", value)


def _config(tmp_path: Path, value: object, *, present: bool = True) -> Path:
    path = tmp_path / "site-seo.json"
    path.write_text(json.dumps({GA4_ID_SETTING: value} if present else {}), encoding="utf-8")
    return path


def test_the_config_reader_returns_the_id_or_empty(tmp_path: Path) -> None:
    assert ga4_measurement_id(_config(tmp_path, _ID)) == _ID
    assert ga4_measurement_id(_config(tmp_path, f"  {_ID} ")) == _ID
    assert ga4_measurement_id(_config(tmp_path, "")) == ""
    assert ga4_measurement_id(_config(tmp_path, None, present=False)) == ""


@pytest.mark.parametrize("bad", ["UA-1234-1", "g-abc123", 'G-ABC123"; fetch("x"); //', 7])
def test_the_config_reader_refuses_anything_that_is_not_an_id(tmp_path: Path, bad: object) -> None:
    with pytest.raises(ValueError, match=GA4_ID_SETTING):
        ga4_measurement_id(_config(tmp_path, bad))


# --- the one line a deploy writes -------------------------------------------


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    return [
        (old, new)
        for old, new in zip(before.splitlines(), after.splitlines(), strict=True)
        if old != new
    ]


def test_render_with_no_id_is_byte_identical_to_the_committed_shim() -> None:
    assert render_measure_script(None, source=_SHIM, ga4_id="") == _SHIM
    assert render_measure_script(None, source=_SHIM, ga4_id="   ") == _SHIM
    assert render_measure_script(None, source=_SHIM) == _SHIM


def test_render_writes_the_id_into_exactly_one_line() -> None:
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    assert _changed_lines(_SHIM, rendered) == [
        (_ID_LINE, f'  var GA4_ID = "{_ID}"; // measure:ga4-id')
    ]


def test_render_writes_the_key_and_the_id_independently() -> None:
    rendered = render_measure_script(_KEY, source=_SHIM, ga4_id=_ID)
    assert _changed_lines(_SHIM, rendered) == [
        ('  var KEY = ""; // measure:key', f'  var KEY = "{_KEY}"; // measure:key'),
        (_ID_LINE, f'  var GA4_ID = "{_ID}"; // measure:ga4-id'),
    ]


@pytest.mark.parametrize("bad", ['G-ABC123"; fetch("https://evil.example"); //', "UA-1-1", "G-a"])
def test_render_refuses_anything_that_is_not_an_id(bad: str) -> None:
    with pytest.raises(ValueError, match=GA4_ID_SETTING):
        render_measure_script(None, source=_SHIM, ga4_id=bad)


def test_render_refuses_a_source_without_exactly_one_id_line() -> None:
    without = _SHIM.replace(_ID_LINE + "\n", "")
    assert without != _SHIM
    with pytest.raises(ValueError, match="exactly one `var GA4_ID"):
        render_measure_script(None, source=without, ga4_id=_ID)
    doubled = _SHIM.replace(_ID_LINE, _ID_LINE + "\n" + _ID_LINE)
    with pytest.raises(ValueError, match="exactly one `var GA4_ID"):
        render_measure_script(None, source=doubled, ga4_id=_ID)


def _deploy_root(tmp_path: Path, value: object) -> Path:
    root = tmp_path / "root"
    (root / "web" / "src").mkdir(parents=True)
    (root / "web" / MEASURE_SCRIPT_PATH).write_text(_SHIM)
    (root / "site-seo.json").write_text(json.dumps({GA4_ID_SETTING: value}), encoding="utf-8")
    # The CLI loads the agency registry before any command runs.
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: demo\n"
        "    name: Demo Transit\n"
        "    static_gtfs_url: https://example.org/gtfs.zip\n"
        "    license_note: CC-BY\n"
    )
    return root


def test_render_measure_command_writes_the_configured_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("POSTHOG_KEY", raising=False)
    out = tmp_path / "site" / "src" / "measure.js"

    monkeypatch.setenv("SCORECARD_ROOT", str(_deploy_root(tmp_path / "off", "")))
    assert main(["render-measure", "--out", str(out)]) == 0
    assert out.read_text() == _SHIM
    assert "Google Analytics off (measurement_ga4_id" in capsys.readouterr().out

    monkeypatch.setenv("SCORECARD_ROOT", str(_deploy_root(tmp_path / "on", _ID)))
    assert main(["render-measure", "--out", str(out)]) == 0
    assert f'var GA4_ID = "{_ID}"; // measure:ga4-id' in out.read_text()
    assert f"Google Analytics on ({_ID})" in capsys.readouterr().out

    monkeypatch.setenv("SCORECARD_ROOT", str(_deploy_root(tmp_path / "bad", "UA-1-1")))
    with pytest.raises(SystemExit) as failed:
        main(["render-measure", "--out", str(out)])
    assert failed.value.code == 2
    # A refused id never reaches the file: the last good render stands.
    assert f'var GA4_ID = "{_ID}"; // measure:ga4-id' in out.read_text()


# --- what the block promises about itself ------------------------------------


def _code_only(source: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)


def test_the_block_names_one_host_and_reads_nothing_it_promises_not_to() -> None:
    code = _code_only(_GA4_BLOCK)
    hosts = {match.group(1) for match in re.finditer(r"https://([a-z0-9.-]+)", _GA4_BLOCK)}
    assert hosts == {GA4_LOADER_HOST.removeprefix("https://")}
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "FormData",
        ".value",
        "innerText",
        "textContent",
        "location.search",
        "location.hash",
        "location.href",
    ):
        assert forbidden not in code, forbidden
    # It listens for one thing, the opt-out, and writes a cookie only to expire
    # one: every cookie assignment carries Max-Age=0.
    assert re.findall(r'addEventListener\("([^"]+)"', code) == ["scorecard:measure-stopped"]
    assert code.count("doc.cookie =") == 2
    assert 'var gone = names[n] + "=; Max-Age=0; path=/";' in code
    # The referrer is read once, inside the helper that reduces it to an origin.
    assert code.count("doc.referrer") == 1
    assert "document.referrer" not in code
    assert "new URL(ref).origin" in code


def test_the_opt_out_and_empty_checks_come_before_anything_loads() -> None:
    """The guards in the rendered file, in order: nothing is written to the
    page or to dataLayer until every one of them has had its chance."""
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    block = _code_only(rendered[rendered.index(_GA4_MARKER) :])
    first_effect = min(block.index("dataLayer"), block.index("createElement"))
    guards = ("if (!GA4_ID) return;", _GPC_GUARD.strip(), _DNT_GUARD.strip(), _STOPPED_GUARD)
    for guard in (*guards, "localhost"):
        assert guard in block, guard
        assert block.index(guard) < first_effect, guard


def test_the_consent_region_list_is_the_eea_the_uk_and_switzerland() -> None:
    listed = set(re.findall(r'"([A-Z]{2})"', _GA4_BLOCK[_GA4_BLOCK.index("CONSENT_REQUIRED") :]))
    assert listed == _CONSENT_REQUIRED
    assert len(_CONSENT_REQUIRED) == 32


# --- what the block does, run in Node against a stub page --------------------

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const cases = JSON.parse(process.argv[2]);

class Element {}
function element(attrs) {
  const el = Object.create(Element.prototype);
  el.attrs = Object.assign({}, attrs);
  el.textContent = "";
  el.listeners = {};
  el.getAttribute = function (n) { return n in this.attrs ? this.attrs[n] : null; };
  el.setAttribute = function (n, v) { this.attrs[n] = String(v); };
  el.hasAttribute = function (n) { return n in this.attrs; };
  el.removeAttribute = function (n) { delete this.attrs[n]; };
  el.addEventListener = function (t, fn) {
    (this.listeners[t] = this.listeners[t] || []).push(fn);
  };
  el.closest = function (sel) {
    return sel === "[data-measure]" && this.hasAttribute("data-measure") ? this : null;
  };
  return el;
}
function fire(listeners, type, event) {
  let prevented = false;
  event.type = type;
  event.preventDefault = function () { prevented = true; };
  (listeners[type] || []).forEach(function (fn) { fn(event); });
  return prevented;
}

const out = cases.map(function (c) {
  const appended = [];
  const sent = [];
  const cookies = [];
  const store = Object.assign({}, c.storage);
  const root = element({});
  root.appendChild = function (el) {
    appended.push({ tag: el.tagName, src: el.src, async: el.async });
  };
  const status = element({ "data-analytics-status": "" });
  const toggle = element({
    "data-analytics-toggle": "",
    href: "/about/#privacy-opt-out",
    "data-label-on": "LABEL-ON",
    "data-label-off": "LABEL-OFF",
    "data-status-on": "STATUS-ON",
    "data-status-off": "STATUS-OFF",
  });
  toggle.textContent = "LABEL-ON";
  toggle.parentNode = {
    querySelector: function (sel) { return sel === "[data-analytics-status]" ? status : null; },
  };
  const checkout = element({
    "data-measure": "bundle_checkout_click",
    "data-measure-plan": "annual",
  });
  const docListeners = {};
  const location = {
    hostname: c.hostname,
    host: c.hostname,
    origin: "https://" + c.hostname,
    pathname: c.pathname,
    search: c.search,
    hash: c.hash,
    href: "https://" + c.hostname + c.pathname + c.search + c.hash,
  };
  const navigator = Object.assign({}, c.navigator);
  const document = {
    referrer: c.referrer,
    head: root,
    documentElement: root,
    createElement: function (tag) { return { tagName: tag.toUpperCase() }; },
    querySelectorAll: function (sel) {
      return sel === "[data-analytics-toggle]" && c.toggle !== false ? [toggle] : [];
    },
    addEventListener: function (t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
    dispatchEvent: function (event) { fire(docListeners, event.type, event); return true; },
  };
  Object.defineProperty(document, "cookie", {
    get: function () { return ""; },
    set: function (value) { cookies.push(value); },
  });
  const window = Object.assign(
    {
      navigator: navigator,
      location: location,
      document: document,
      fetch: function (url, init) {
        sent.push(JSON.parse(init.body).event);
        return Promise.resolve();
      },
      crypto: {
        getRandomValues: function (b) {
          for (let i = 0; i < b.length; i++) b[i] = (i * 37) % 256;
          return b;
        },
      },
      sessionStorage: { getItem: function () { return null; }, setItem: function () {} },
      localStorage: {
        getItem: function (k) { return k in store ? store[k] : null; },
        setItem: function (k, v) { store[k] = String(v); },
        removeItem: function (k) { delete store[k]; },
      },
      CustomEvent: function (type) { this.type = type; },
    },
    c.window
  );
  const context = vm.createContext({
    window: window, document: document, navigator: navigator, location: location,
    URL: URL, Element: Element,
  });
  vm.runInContext(source, context);
  const prevented = [];
  (c.actions || []).forEach(function (action) {
    if (action === "click") prevented.push(fire(toggle.listeners, "click", { target: toggle }));
    if (action === "space") {
      prevented.push(fire(toggle.listeners, "keydown", { target: toggle, key: " " }));
    }
    if (action === "checkout") fire(docListeners, "click", { target: checkout });
  });
  return {
    appended: appended,
    sent: sent,
    dataLayer: window.dataLayer
      ? window.dataLayer.map(function (a) { return Array.from(a); })
      : null,
    cookies: cookies,
    storage: store,
    stopped: root.getAttribute("data-measure-stopped"),
    label: toggle.textContent,
    status: status.textContent,
    role: toggle.getAttribute("role"),
    prevented: prevented,
    gaDisabled: Object.keys(window).filter(function (k) {
      return k.indexOf("ga-disable-") === 0 && window[k] === true;
    }),
  };
});
process.stdout.write(JSON.stringify(out));
"""


def _visit(**overrides: Any) -> dict[str, Any]:
    visit: dict[str, Any] = {
        "hostname": "gtfsscorecard.org",
        "pathname": "/bundle/setup/",
        "search": "?session_id=cs_test_order_reference",
        "hash": "#done",
        "referrer": "https://checkout.stripe.com/c/pay/cs_test_order_reference?x=1",
        "navigator": {},
        "window": {},
    }
    visit.update(overrides)
    return visit


def _run(tmp_path: Path, source: str, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    node = shutil.which("node")
    assert node is not None
    script = tmp_path / "measure.js"
    script.write_text(source)
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [node, "-e", _HARNESS, str(script), json.dumps(cases)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _loaded(result: dict[str, Any]) -> bool:
    return bool(result["appended"]) or result["dataLayer"] is not None


def test_with_no_id_nothing_loads(tmp_path: Path) -> None:
    unset = render_measure_script(None, source=_SHIM, ga4_id="")
    [result] = _run(tmp_path, unset, [_visit()])
    assert (result["appended"], result["sent"], result["dataLayer"]) == ([], [], None)
    assert result["cookies"] == [] and result["gaDisabled"] == []


def test_with_an_id_the_loader_is_added_once_with_the_promised_config(tmp_path: Path) -> None:
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    [result] = _run(tmp_path, rendered, [_visit()])

    assert result["appended"] == [
        {"tag": "SCRIPT", "src": f"{GA4_LOADER_HOST}/gtag/js?id={_ID}", "async": True}
    ]
    assert result["sent"] == []  # PostHog stays off: no key was written.
    layer = result["dataLayer"]
    assert [entry[:2] for entry in layer] == [
        ["consent", "default"],
        ["consent", "default"],
        ["js", layer[2][1]],
        ["config", _ID],
    ]
    strict, elsewhere = layer[0][2], layer[1][2]
    assert set(strict.pop("region")) == _CONSENT_REQUIRED
    assert strict == {**_ADS_DENIED, "analytics_storage": "denied"}
    assert elsewhere == {**_ADS_DENIED, "analytics_storage": "granted"}
    assert layer[3][2] == {
        "allow_google_signals": False,
        "allow_ad_personalization_signals": False,
        # The Stripe order reference in the query string, the fragment, and the
        # referrer's path and query never leave the browser.
        "page_location": "https://gtfsscorecard.org/bundle/setup/",
        "page_referrer": "https://checkout.stripe.com/",
    }


def test_with_no_referrer_none_is_sent(tmp_path: Path) -> None:
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    [result] = _run(tmp_path, rendered, [_visit(referrer="")])
    assert result["dataLayer"][3][2]["page_referrer"] == ""


def test_both_blocks_run_independently_when_both_are_configured(tmp_path: Path) -> None:
    rendered = render_measure_script(_KEY, source=_SHIM, ga4_id=_ID)
    posthog_only = render_measure_script(_KEY, source=_SHIM, ga4_id="")
    both, only = _run(tmp_path, rendered, [_visit()]) + _run(tmp_path, posthog_only, [_visit()])
    assert both["sent"] == ["$pageview"] and len(both["appended"]) == 1
    assert only["sent"] == ["$pageview"] and not _loaded(only)


_OPT_OUTS: dict[str, dict[str, Any]] = {
    "global privacy control": {"navigator": {"globalPrivacyControl": True}},
    "do not track": {"navigator": {"doNotTrack": "1"}},
    "window do not track": {"window": {"doNotTrack": "1"}},
    "ms do not track": {"navigator": {"msDoNotTrack": "1"}},
    "localhost": {"hostname": "localhost"},
    "loopback": {"hostname": "127.0.0.1"},
}


@pytest.mark.parametrize("name", sorted(_OPT_OUTS))
def test_an_opt_out_or_a_local_page_loads_nothing(tmp_path: Path, name: str) -> None:
    rendered = render_measure_script(_KEY, source=_SHIM, ga4_id=_ID)
    [result] = _run(tmp_path, rendered, [_visit(**_OPT_OUTS[name])])
    assert not _loaded(result), name


def test_a_false_privacy_signal_does_not_opt_out(tmp_path: Path) -> None:
    """GPC off and DNT "0" are not opt-outs; only the set signals are."""
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    visit = _visit(navigator={"globalPrivacyControl": False, "doNotTrack": "0"})
    [result] = _run(tmp_path, rendered, [visit])
    assert _loaded(result)


# --- the footer opt-out, run in Node against the same stub page ------------

_STORE = "scorecard-analytics"
_OPTED_OUT = {_STORE: "off"}


def _both() -> str:
    return render_measure_script(_KEY, source=_SHIM, ga4_id=_ID)


def test_a_stored_opt_out_stops_both_tools(tmp_path: Path) -> None:
    [result] = _run(tmp_path, _both(), [_visit(storage=_OPTED_OUT, actions=["checkout"])])
    assert result["sent"] == []
    assert not _loaded(result)
    assert result["stopped"] == "opted-out"
    # The control says what a click would do now, and is a button to
    # assistive technology.
    assert (result["label"], result["role"]) == ("LABEL-OFF", "button")


def test_opting_out_mid_page_stops_both_and_forgets_the_ga4_cookies(tmp_path: Path) -> None:
    visit = _visit(actions=["checkout", "click", "checkout"])
    [result] = _run(tmp_path, _both(), [visit])

    # Before the click both tools ran; after it, PostHog reports nothing more
    # and GA4 is switched off with Google's own flag for this id.
    assert result["sent"] == ["$pageview", "bundle_checkout_click"]
    assert len(result["appended"]) == 1
    assert result["gaDisabled"] == [f"ga-disable-{_ID}"]
    assert result["storage"] == _OPTED_OUT
    assert result["stopped"] == "opted-out"
    assert (result["label"], result["status"]) == ("LABEL-OFF", "STATUS-OFF")
    assert result["prevented"] == [True]
    # Every cookie write expires one of the two GA4 cookies, host-only and on
    # each parent domain.
    assert result["cookies"], "the opt-out wrote no cookie expiry"
    assert all("=; Max-Age=0; path=/" in cookie for cookie in result["cookies"])
    names = {cookie.split("=", 1)[0] for cookie in result["cookies"]}
    assert names == {"_ga", f"_ga_{_ID.removeprefix('G-')}"}
    assert "_ga=; Max-Age=0; path=/; domain=gtfsscorecard.org" in result["cookies"]


def test_the_next_page_after_opting_out_loads_nothing(tmp_path: Path) -> None:
    [first] = _run(tmp_path, _both(), [_visit(actions=["click"])])
    assert first["storage"] == _OPTED_OUT
    [second] = _run(tmp_path, _both(), [_visit(storage=first["storage"], actions=["checkout"])])
    assert second["sent"] == [] and not _loaded(second)


def test_opting_back_in_clears_the_choice_and_resumes_on_the_next_page(tmp_path: Path) -> None:
    [back] = _run(tmp_path, _both(), [_visit(storage=_OPTED_OUT, actions=["click", "checkout"])])
    assert back["storage"] == {}
    assert (back["label"], back["status"]) == ("LABEL-ON", "STATUS-ON")
    # This page stays stopped; the next one measures again.
    assert back["stopped"] == "until-next-page"
    assert back["sent"] == [] and not _loaded(back)
    [next_page] = _run(tmp_path, _both(), [_visit(storage=back["storage"])])
    assert next_page["sent"] == ["$pageview"] and len(next_page["appended"]) == 1


def test_the_space_key_toggles_the_control(tmp_path: Path) -> None:
    [result] = _run(tmp_path, _both(), [_visit(actions=["space"])])
    assert result["storage"] == _OPTED_OUT and result["prevented"] == [True]


def test_the_control_works_with_neither_tool_configured(tmp_path: Path) -> None:
    """The footer link has to work on a deploy with no key and no id, so a
    choice made then still holds once either is switched on."""
    unset = render_measure_script(None, source=_SHIM, ga4_id="")
    [result] = _run(tmp_path, unset, [_visit(actions=["click"])])
    assert result["storage"] == _OPTED_OUT
    assert (result["label"], result["role"]) == ("LABEL-OFF", "button")


def test_the_opt_out_control_carries_no_reader_copy() -> None:
    """Its wording comes from the markup, so the Spanish footer can carry
    Spanish and this file carries no sentence a reader sees."""
    block = _code_only(_SHIM[: _SHIM.index(_POSTHOG_START)])
    literals = re.findall(r'"([^"\n]*)"', block)
    assert literals, "the opt-out block was not found"
    assert [text for text in literals if re.search(r"[A-Za-z]{2,} [A-Za-z]{2,}", text)] == [
        "use strict"
    ]


# --- negative controls: the harness can see each guard fail -----------------


def _sabotaged(source: str, *guards: str, posthog: bool = False) -> str:
    """``source`` with each guard removed from one block only: the GA4 block,
    or with ``posthog`` the PostHog block. The other blocks carry the same
    opt-out lines and are left as they are. Each removal is asserted to have
    happened, and the result to differ."""
    start = source.index(_POSTHOG_START) if posthog else source.index(_GA4_MARKER)
    end = source.index(_GA4_MARKER) if posthog else len(source)
    head, block, tail = source[:start], source[start:end], source[end:]
    for guard in guards:
        assert block.count(guard) == 1, guard
        block = block.replace(guard, "")
        assert guard not in block, guard
    broken = head + block + tail
    assert broken != source
    return broken


def test_control_without_the_gpc_guard_the_harness_sees_ga_load(tmp_path: Path) -> None:
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    broken = _sabotaged(rendered, _GPC_GUARD)
    [result] = _run(tmp_path, broken, [_visit(**_OPT_OUTS["global privacy control"])])
    assert _loaded(result)


def test_control_without_the_dnt_guard_the_harness_sees_ga_load(tmp_path: Path) -> None:
    rendered = render_measure_script(None, source=_SHIM, ga4_id=_ID)
    broken = _sabotaged(rendered, _DNT_GUARD)
    [result] = _run(tmp_path, broken, [_visit(**_OPT_OUTS["do not track"])])
    assert _loaded(result)


def test_control_without_the_stopped_guard_ga4_loads_for_an_opted_out_reader(
    tmp_path: Path,
) -> None:
    broken = _sabotaged(_both(), _STOPPED_GUARD)
    [result] = _run(tmp_path, broken, [_visit(storage=_OPTED_OUT)])
    assert len(result["appended"]) == 1


def test_control_without_the_stopped_guards_posthog_sends_for_an_opted_out_reader(
    tmp_path: Path,
) -> None:
    broken = _sabotaged(_both(), f"\n  {_STOPPED_GUARD}", f"\n    {_STOPPED_GUARD}", posthog=True)
    [result] = _run(tmp_path, broken, [_visit(storage=_OPTED_OUT, actions=["checkout"])])
    assert result["sent"] == ["$pageview", "bundle_checkout_click"]
    assert not _loaded(result)  # GA4 kept its guard, so only PostHog broke


def test_control_without_the_empty_id_guards_the_harness_sees_ga_load(tmp_path: Path) -> None:
    unset = render_measure_script(None, source=_SHIM, ga4_id="")
    broken = _sabotaged(unset, *_EMPTY_GUARDS)
    [result] = _run(tmp_path, broken, [_visit()])
    assert result["appended"] == [
        {"tag": "SCRIPT", "src": f"{GA4_LOADER_HOST}/gtag/js?id=", "async": True}
    ]


# --- the generated pages -------------------------------------------------------


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []
        self.refreshes = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.sources.append(str(values["src"]))
        if tag == "meta" and (values.get("http-equiv") or "").casefold() == "refresh":
            self.refreshes = True


def test_every_generated_page_reaches_ga4_only_through_the_measurement_script() -> None:
    """The renderer's golden output covers each generated page family: agency
    pages and their board and brief views, program pages, fix guides, the query
    and status pages, and the rest. Each loads the measurement script exactly
    once, which is how GA4 reaches it, and none loads a Google host itself."""
    pages = sorted(_GOLDEN_SITE.rglob("*.html"))
    families = {page.relative_to(_GOLDEN_SITE).parts[0] for page in pages}
    assert {"agency", "program", "fix", "query", "status"} <= families
    checked = 0
    for page in pages:
        parser = _Scripts()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.refreshes:
            continue
        name = str(page.relative_to(_GOLDEN_SITE))
        assert parser.sources.count("/src/measure.js") == 1, name
        assert not any("google" in src for src in parser.sources), name
        checked += 1
    assert checked >= 30


class _Controls(HTMLParser):
    """Collect every opt-out control and status region in a document."""

    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, str | None]] = []
        self.statuses: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if "data-analytics-toggle" in values:
            self.controls.append({"tag": tag, **values})
        if "data-analytics-status" in values:
            self.statuses.append({"tag": tag, **values})


def _controls(html: str) -> _Controls:
    parser = _Controls()
    parser.feed(html)
    return parser


_EN_LABELS = ("Opt out of analytics", "Opt back in to analytics")


@pytest.mark.parametrize(
    ("name", "footer", "labels"),
    [
        ("english", FOOTER_HTML, _EN_LABELS),
        ("outside the US", FOOTER_HTML_WITHOUT_US_TOOLS, _EN_LABELS),
        ("spanish", FOOTER_HTML_ES, ("Desactivar la analítica", "Volver a activar la analítica")),
    ],
)
def test_every_footer_carries_one_opt_out_with_its_wording(
    name: str, footer: str, labels: tuple[str, str]
) -> None:
    found = _controls(footer)
    assert len(found.controls) == 1, name
    control = found.controls[0]
    assert control["tag"] == "a" and control["href"] == "/about/#privacy-opt-out"
    assert (control["data-label-on"], control["data-label-off"]) == labels
    assert control["data-status-on"] and control["data-status-off"]
    assert [status["role"] for status in found.statuses] == ["status"]
    assert f">{labels[0]}</a>" in footer


def test_generated_pages_carry_the_opt_out_in_every_footer_variant() -> None:
    variants: list[dict[str, Any]] = [{}, {"lang": "es"}, {"country_code": "CA"}]
    for kwargs in variants:
        html = _page(
            title="A page",
            description="A description of a page long enough to be one.",
            canonical="https://gtfsscorecard.org/x/",
            body="<h1>A page</h1>",
            **kwargs,
        )
        assert len(_controls(html).controls) == 1, kwargs


def test_every_hand_authored_page_carries_the_opt_out() -> None:
    """The nav-synced pages get it from FOOTER_HTML; the two landing pages
    carry their own footer and the same markup."""
    for rel in MEASURED_STATIC_PAGES:
        html = (_REPO / "web" / rel).read_text(encoding="utf-8")
        assert len(_controls(html).controls) == 1, f"{rel}: run `make sync-static-nav`"
    assert ANALYTICS_OPT_OUT_HTML in (_REPO / "web" / "index.html").read_text(encoding="utf-8")
    assert ANALYTICS_OPT_OUT_HTML_ES in (_REPO / "web" / "es" / "index.html").read_text(
        encoding="utf-8"
    )


def test_the_bundle_sample_page_offers_the_opt_out_and_a_buyer_report_never_does() -> None:
    """The sample is the one report rendered as a page on the site, so it
    measures and must offer the way out. A purchased report is a document,
    loads no script, and carries no control."""
    from scorecard_pipeline.report import _sample_foot_note_html

    assert ANALYTICS_OPT_OUT_HTML in _sample_foot_note_html()
    sample = (_REPO / "web" / "bundle" / "sample" / "index.html").read_text(encoding="utf-8")
    assert "/src/measure.js" in sample
    assert len(_controls(sample).controls) == 1
    reports = sorted((_GOLDENS / "report").glob("*.html"))
    assert reports
    for report in reports:
        assert "data-analytics-toggle" not in report.read_text(encoding="utf-8"), report.name


def test_every_rendered_golden_page_that_measures_offers_the_opt_out() -> None:
    """The render goldens cover each generated page family. A page that loads
    the measurement script carries the control; a redirect stub carries
    neither."""
    pages = sorted({*_GOLDENS.rglob("*.html"), *_GOLDEN_SITE.rglob("*.html")})
    measured = 0
    for page in pages:
        html = page.read_text(encoding="utf-8")
        if "/src/measure.js" not in html:
            continue
        measured += 1
        assert len(_controls(html).controls) == 1, page
    assert measured >= 60


# --- the disclosure ------------------------------------------------------------


def test_the_disclosure_describes_ga4_as_configured() -> None:
    privacy = _ABOUT[
        _ABOUT.index('id="privacy"') : _ABOUT.index("</section>", _ABOUT.index('id="privacy"'))
    ]
    for phrase in (
        "Google Analytics 4",
        "Google LLC",
        "_ga",
        "two years",
        "14 months",
        "European Economic Area, the United Kingdom, or Switzerland",
        "Google signals",
        "Global Privacy",
        "Do Not Track",
        "googletagmanager.com",
        "0056-google-analytics-4",
        "Opt out of analytics",
        "Opt back in to analytics",
        "scorecard-analytics",
        "deletes the\n      Google Analytics cookies",
        "from the next page you open",
    ):
        assert phrase in privacy, phrase
