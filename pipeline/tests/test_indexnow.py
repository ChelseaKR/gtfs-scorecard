"""IndexNow (scorecard_pipeline/indexnow.py, ADR 0073): selection from the
sitemap's content-derived lastmod, submission, and the Deploy site workflow.
A fake HTTP client stands in for the network everywhere; every negative
control asserts its sabotage applied before it concludes anything."""

from __future__ import annotations

import json
import re
import shutil
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import indexnow as ix

BASE = "https://example.test"
ORIGIN = "https://gtfsscorecard.org"
# Deliberately low-entropy so the secret scanners do not read it as a key; a
# real IndexNow key is public by design anyway.
KEY = "ab" * 16
PAGE = "<html><head><title>t</title></head><body>x</body></html>"
NOINDEX = '<html><head><meta name="robots" content="noindex,follow"></head></html>'
REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
GOLDEN_WEB = Path(__file__).parent / "fixtures" / "golden_site" / "web"
WORKFLOWS = REPO / ".github" / "workflows"


class FakeClient:
    def __init__(self, status: int = 200, raises: Exception | None = None) -> None:
        self.status, self.raises = status, raises
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post_json(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        self.calls.append((url, json.loads(body), dict(headers)))
        if self.raises:
            raise self.raises
        return self.status


def _sitemap(entries: Mapping[str, str]) -> str:
    rows = "".join(
        f"<url><loc>{u}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>"
        for u, m in entries.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>'
    )


def _site(tmp_path: Path, pages: Mapping[str, str]) -> Path:
    root = tmp_path / "site"
    for rel, html in pages.items():
        f = root / rel / "index.html" if rel else root / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html, encoding="utf-8")
    (root / f"{KEY}.txt").write_text(KEY + "\n", encoding="utf-8")
    robots = f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n"
    (root / "robots.txt").write_text(robots, encoding="utf-8")
    return root


def _select(
    tmp_path: Path,
    site: Path,
    live: str | None,
    monkeypatch: pytest.MonkeyPatch,
    base: str = BASE,
) -> dict[str, Any]:
    monkeypatch.setattr(ix, "fetch_text", lambda url, missing_is_empty: live)
    out = tmp_path / "urls.json"
    argv = ["select", "--site-dir", str(site), "--base-url", base, "--kind", "sitemap"]
    assert ix.main([*argv, "--file", "sitemap.xml", "--missing-is-empty", "--out", str(out)]) == 0
    payload: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return payload


# -- the module ---------------------------------------------------------------


def test_new_and_changed_pages_are_selected_and_unchanged_are_not() -> None:
    prev = {f"{BASE}/a/": "2026-11-01", f"{BASE}/b/": "2026-11-01", f"{BASE}/n/": ""}
    cur = {
        f"{BASE}/a/": "2026-11-01",
        f"{BASE}/b/": "2026-11-05",
        f"{BASE}/c/": "2026-11-05",
        f"{BASE}/n/": "",
    }
    # A page with no lastmod on either side is unchanged, not "changed today".
    assert ix.select_changed(prev, cur) == [f"{BASE}/b/", f"{BASE}/c/"]


def test_an_unreadable_live_site_selects_nothing_but_an_empty_one_selects_all() -> None:
    cur = {f"{BASE}/a/": "2026-11-05"}
    assert ix.select_changed(None, cur) == []
    assert ix.select_changed({}, cur) == [f"{BASE}/a/"]


def test_the_sitemap_parser_reads_one_line_sitemaps_entities_and_missing_lastmod() -> None:
    text = _sitemap({f"{BASE}/a/?x=1&amp;y=2": "2026-11-05", f"{BASE}/b/": ""})
    assert ix.parse_sitemap(text) == {f"{BASE}/a/?x=1&y=2": "2026-11-05", f"{BASE}/b/": ""}


def test_filter_drops_noindex_foreign_host_and_unbuilt_pages(tmp_path: Path) -> None:
    site = _site(tmp_path, {"": PAGE, "a": PAGE, "thin": NOINDEX})
    urls = [
        f"{BASE}/a/",
        f"{BASE}/thin/",
        "https://evil.test/a/",
        f"{BASE}/missing/",
        "http://example.test/a/",
    ]
    kept, notes = ix.filter_submittable(urls, base_url=BASE, site_dir=site)
    assert kept == [f"{BASE}/a/"]
    assert len(notes) == 4


def test_negative_control_validate_rejects_over_cap_duplicates_and_foreign_hosts(
    tmp_path: Path,
) -> None:
    site = _site(tmp_path, {"a": PAGE})
    ix.validate_submission([f"{BASE}/a/"], base_url=BASE, site_dir=site)  # the clean list passes
    over = [f"{BASE}/p{i}/" for i in range(ix.MAX_URLS + 1)]
    with pytest.raises(ix.IndexNowError, match="exceeds"):
        ix.validate_submission(over, base_url=BASE, site_dir=site)
    with pytest.raises(ix.IndexNowError, match="duplicate"):
        ix.validate_submission([f"{BASE}/a/", f"{BASE}/a/"], base_url=BASE, site_dir=site)
    with pytest.raises(ix.IndexNowError, match="not on"):
        ix.validate_submission(["https://evil.test/a/"], base_url=BASE, site_dir=site)


def test_the_key_file_must_exist_once_and_match_its_name(tmp_path: Path) -> None:
    site = _site(tmp_path, {"": PAGE})
    assert ix.find_key(site) == KEY
    (site / f"{KEY}.txt").write_text("wrong\n", encoding="utf-8")
    with pytest.raises(ix.IndexNowError, match="body must equal"):
        ix.find_key(site)
    (site / f"{KEY}.txt").unlink()
    with pytest.raises(ix.IndexNowError, match="exactly one"):
        ix.find_key(site)


def test_robots_problems_are_named(tmp_path: Path) -> None:
    assert ix.check_robots(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", BASE) == []
    blocked = ix.check_robots("User-agent: bingbot\nDisallow: /\n", BASE)
    assert len(blocked) == 2  # Bingbot blocked, and no sitemap line


def test_submit_posts_the_documented_payload_and_never_raises() -> None:
    payload = ix.build_payload(BASE, KEY, [f"{BASE}/a/"])
    assert payload == {
        "host": "example.test",
        "key": KEY,
        "keyLocation": f"{BASE}/{KEY}.txt",
        "urlList": [f"{BASE}/a/"],
    }
    ok = FakeClient(202)
    assert "accepted 1 URLs (HTTP 202)" in ix.submit(payload, ok)
    assert ok.calls[0][0] == ix.ENDPOINT
    assert ok.calls[0][1] == payload
    for client in (FakeClient(403), FakeClient(429), FakeClient(raises=OSError("down"))):
        assert "normal crawl" in ix.submit(payload, client)
        assert client.calls  # the failure path really ran
    assert "no urlList" in ix.submit({"urlList": "x"}, FakeClient())


def test_submit_command_exits_zero_even_when_the_list_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ix.main(["submit", "--list", str(tmp_path / "nope.json")]) == 0
    assert "::notice" in capsys.readouterr().out


def test_fetch_text_separates_missing_from_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def answer(status: int) -> Any:
        return lambda method, url, body, headers: (status, b"<urlset/>")

    monkeypatch.setattr(ix, "_request", answer(200))
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=True) == "<urlset/>"
    monkeypatch.setattr(ix, "_request", answer(404))
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=True) == ""
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=False) is None
    monkeypatch.setattr(ix, "_request", answer(503))
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=True) is None

    def raise_(exc: Exception) -> Any:
        def f(method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> Any:
            raise exc

        return f

    monkeypatch.setattr(ix, "_request", raise_(socket.gaierror("no such host")))
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=True) == ""
    monkeypatch.setattr(ix, "_request", raise_(TimeoutError()))
    assert ix.fetch_text(f"{BASE}/sitemap.xml", missing_is_empty=True) is None


def test_only_https_is_ever_requested() -> None:
    with pytest.raises(ix.IndexNowError, match="only https"):
        ix._request("GET", "http://example.test/", None, {})
    with pytest.raises(ix.IndexNowError, match="https with a host"):
        ix.host_of("http://example.test")


def test_select_with_an_unreadable_live_sitemap_submits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path, {"a": PAGE})
    (site / "sitemap.xml").write_text(_sitemap({f"{BASE}/a/": "2026-11-05"}), encoding="utf-8")
    assert _select(tmp_path, site, None, monkeypatch)["urlList"] == []
    assert "submitting nothing" in capsys.readouterr().out


def test_select_never_fails_the_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path, {"a": PAGE})  # no sitemap.xml at all
    assert _select(tmp_path, site, "", monkeypatch)["urlList"] == []
    assert "selection skipped" in capsys.readouterr().out


def test_negative_control_an_unchanged_sitemap_sends_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero changed URLs end to end: select finds nothing and submit sends
    nothing. One moved lastmod does send, so the empty case is not an accident
    of the fixture."""
    site = _site(tmp_path, {"": PAGE, "a": PAGE})
    current = {f"{BASE}/": "2026-11-05", f"{BASE}/a/": "2026-11-04"}
    (site / "sitemap.xml").write_text(_sitemap(current), encoding="utf-8")
    same = _select(tmp_path, site, _sitemap(current), monkeypatch)
    assert same["urlList"] == []
    quiet = FakeClient()
    assert "nothing to submit" in ix.submit(same, quiet)
    assert quiet.calls == []

    older = {**current, f"{BASE}/a/": "2026-11-01"}
    assert older != current  # the sabotage applied
    changed = _select(tmp_path, site, _sitemap(older), monkeypatch)
    assert changed["urlList"] == [f"{BASE}/a/"]
    sent = FakeClient()
    ix.submit(changed, sent)
    assert len(sent.calls) == 1


# -- the golden site, assembled the way pages.yml assembles _site -------------


def _assembled(tmp_path: Path) -> Path:
    """The golden render plus what `cp -r web/. _site/` brings from the
    committed web/ tree: robots.txt, the key file and the static pages the
    sitemap lists. Only those files are copied (web/ is about 100 MB)."""
    site = tmp_path / "_site"
    shutil.copytree(GOLDEN_WEB, site)
    shutil.copy2(WEB / "robots.txt", site / "robots.txt")
    keys = [p for p in WEB.iterdir() if ix.KEY_FILE_RE.match(p.name)]
    assert len(keys) == 1
    shutil.copy2(keys[0], site / keys[0].name)
    for url in ix.parse_sitemap((site / "sitemap.xml").read_text(encoding="utf-8")):
        built = ix.page_file(site, ORIGIN, url)
        assert built is not None
        if not built.is_file():
            source = WEB / built.relative_to(site)
            built.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, built)
    return site


def test_the_site_serves_one_key_file_and_robots_lets_bingbot_in(tmp_path: Path) -> None:
    site = _assembled(tmp_path)
    key = ix.find_key(site)
    assert re.fullmatch(r"[0-9a-f]{32}", key)
    assert ix.check_robots((site / "robots.txt").read_text(encoding="utf-8"), ORIGIN) == []


def test_every_golden_sitemap_url_is_announceable(tmp_path: Path) -> None:
    site = _assembled(tmp_path)
    locs = sorted(ix.parse_sitemap((site / "sitemap.xml").read_text(encoding="utf-8")))
    assert len(locs) > 20, "a near-empty sitemap would make this check prove nothing"
    kept, notes = ix.filter_submittable(locs, base_url=ORIGIN, site_dir=site)
    assert notes == [] and kept == locs


def test_negative_control_the_golden_site_against_itself_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deploy whose sitemap equals the live one (a code push with no content
    change) announces nothing. Moving one agency page's lastmod in the "live"
    copy then selects exactly that page."""
    site = _assembled(tmp_path)
    text = (site / "sitemap.xml").read_text(encoding="utf-8")
    same = _select(tmp_path, site, text, monkeypatch, base=ORIGIN)
    assert same["urlList"] == []
    client = FakeClient()
    ix.submit(same, client)
    assert client.calls == []

    entries = ix.parse_sitemap(text)
    target = next(u for u, m in sorted(entries.items()) if "/agency/" in u and m)
    older = text.replace(
        f"<loc>{target}</loc><lastmod>{entries[target]}</lastmod>",
        f"<loc>{target}</loc><lastmod>2001-01-01</lastmod>",
    )
    assert older != text  # the sabotage applied
    changed = _select(tmp_path, site, older, monkeypatch, base=ORIGIN)
    assert changed["urlList"] == [target]
    assert changed["host"] == "gtfsscorecard.org"


# -- the workflow --------------------------------------------------------------


def _block(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    return text[i : text.index(end, i + len(start))] if end else text[i:]


def test_pages_selects_before_the_upload_and_submits_after_the_production_smoke() -> None:
    text = (WORKFLOWS / "pages.yml").read_text(encoding="utf-8")
    build = _block(text, "\n  lighthouse:\n", "\n  deploy:\n")
    order = [
        "- name: Render and assemble the Pages site",
        "- name: Enforce the structural SEO contract",
        "- name: Enforce generated page-size budgets",
        "- name: Pick the pages to announce to IndexNow",
        "- name: Keep the IndexNow list",
        "- name: Upload the Pages artifact\n",
    ]
    positions = [build.index(step) for step in order]
    assert positions == sorted(positions)
    assert "--kind sitemap --file sitemap.xml --missing-is-empty" in build
    assert "indexnow.py submit" not in build
    job = _block(text, "\n  indexnow:\n", None)
    assert "    needs: production-smoke\n" in job
    assert "indexnow.py submit" in job
    head = job.split("steps:")[0]
    assert "write" not in head and "id-token" not in head
    assert "secrets." not in job and "aws-actions" not in job
    mine = job + _block(
        build, "- name: Pick the pages to announce", "- name: Upload the Pages artifact\n"
    )
    code = [ln for ln in mine.splitlines() if not ln.strip().startswith("#")]
    assert not [ln for ln in code if "continue-on-error" in ln]


def test_no_other_workflow_announces_to_indexnow() -> None:
    """Only the production deploy calls it; pull-request CI never does."""
    callers = sorted(
        p.name for p in WORKFLOWS.glob("*.yml") if "indexnow" in p.read_text(encoding="utf-8")
    )
    assert callers == ["pages.yml"]
