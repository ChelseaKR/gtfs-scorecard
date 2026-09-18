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
    GA4_ID_SETTING,
    GA4_LOADER_HOST,
    MEASURE_SCRIPT_PATH,
    ga4_measurement_id,
    render_measure_script,
)

_REPO = Path(__file__).resolve().parents[2]
_SHIM = (_REPO / "web" / MEASURE_SCRIPT_PATH).read_text()
_GA4_MARKER = "// Google Analytics 4 (docs/decisions/0056"
_GA4_BLOCK = _SHIM[_SHIM.index(_GA4_MARKER) :]
_GOLDEN_SITE = _REPO / "pipeline" / "tests" / "fixtures" / "golden_site" / "web"
_ABOUT = (_REPO / "web" / "about" / "index.html").read_text()

_ID = "G-TEST0A1B2C"
_KEY = "phc_TestKey0123456789abcdefghijklmnopqrstuv"  # gitleaks:allow (fixture key, not real)
_ID_LINE = '  var GA4_ID = ""; // measure:ga4-id'
_GPC_GUARD = "  if (nav.globalPrivacyControl === true) return;\n"
_DNT_GUARD = (
    '  if (nav.doNotTrack === "1" || win.doNotTrack === "1" || nav.msDoNotTrack === "1") return;\n'
)
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
        "addEventListener",
    ):
        assert forbidden not in code, forbidden
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
    for guard in ("if (!GA4_ID) return;", _GPC_GUARD.strip(), _DNT_GUARD.strip(), "localhost"):
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
const out = cases.map(function (c) {
  const appended = [];
  const sent = [];
  const head = {
    appendChild: function (el) {
      appended.push({ tag: el.tagName, src: el.src, async: el.async });
    },
  };
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
    head: head,
    documentElement: head,
    createElement: function (tag) { return { tagName: tag.toUpperCase() }; },
    addEventListener: function () {},
  };
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
    },
    c.window
  );
  const context = vm.createContext({
    window: window, document: document, navigator: navigator, location: location,
    URL: URL, Element: function () {},
  });
  vm.runInContext(source, context);
  return {
    appended: appended,
    sent: sent,
    dataLayer: window.dataLayer
      ? window.dataLayer.map(function (a) { return Array.from(a); })
      : null,
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
    assert result == {"appended": [], "sent": [], "dataLayer": None}


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


# --- negative controls: the harness can see each guard fail -----------------


def _sabotaged(source: str, *guards: str) -> str:
    """``source`` with each guard removed from the GA4 block only. The PostHog
    block above carries the same opt-out lines and is left as it is. Each
    removal is asserted to have happened, and the result to differ."""
    split = source.index(_GA4_MARKER)
    head, block = source[:split], source[split:]
    for guard in guards:
        assert block.count(guard) == 1, guard
        block = block.replace(guard, "")
        assert guard not in block, guard
    broken = head + block
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
    ):
        assert phrase in privacy, phrase
