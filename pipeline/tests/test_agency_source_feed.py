"""The visible "Source feed" line on an agency scorecard (owner scope, 2026-10-11).

Most disclosed search queries that land on an agency page ask for the agency's
GTFS file, and the page named that file's URL only inside its JSON-LD. The
line links the publisher's own download and, when the record carries a
Mobility Database id, that feed's version history there. It links; the site
never hosts a copy. These tests hold four things:

1. **No public source, no line.** A local zip, a credentialed fetch, a URL on
   this site, a withheld publisher, or a license block that forbids
   redistribution renders no "Source feed" line at all, with no placeholder.
2. **The Mobility Database link is never guessed.** Only an id of a shape that
   was opened on mobilitydatabase.org is linked; anything else is omitted.
3. **The JSON-LD agrees with the page.** ``isBasedOn`` is present exactly when
   the visible link is, and names the same URL.
4. **The negative controls bite.** Each sabotage is asserted to have landed,
   and the unsabotaged control is asserted to render the line, before the
   absence is checked.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from scorecard_pipeline.config import Agency, LicenseBlock
from scorecard_pipeline.render_site import (
    _license_forbids_redistribution,
    _mdb_feed_page,
    _public_source_url,
    _render_agency,
    _source_feed_line,
    _withheld_source_ids,
)

_REPO = Path(__file__).resolve().parents[2]
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"
_FIXTURE = _REPO / "pipeline" / "tests" / "fixtures" / "golden_site"
_LINE_RE = re.compile(r'<p class="feed-source">.*?</p>', re.S)
_HREF_RE = re.compile(r'href="([^"]+)"')
_JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_BARRIE_URL = "http://www.myridebarrie.ca/gtfs/Google_transit.zip"
_BARRIE_MDB = "https://mobilitydatabase.org/feeds/gtfs/mdb-3"


def _artifact(agency_id: str = "barrie-transit") -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (_FIXTURE / "data" / "artifacts" / agency_id / "latest.json").read_text()
    )
    return data


def _record(mdb_id: object = "3") -> dict[str, Any]:
    return {"id": "barrie-transit", "country": "CA", "mdb_id": mdb_id}


def _page(artifact: dict[str, Any], **kwargs: Any) -> str:
    kwargs.setdefault("dir_record", _record())
    return _render_agency(artifact, **kwargs)


def _line(html: str) -> str:
    lines = _LINE_RE.findall(html)
    assert len(lines) <= 1, "more than one source line on one page"
    return lines[0] if lines else ""


def _dataset_jsonld(html: str) -> dict[str, Any]:
    for block in _JSONLD_RE.findall(html):
        node = json.loads(block)
        if isinstance(node, dict) and node.get("@type") == "Dataset":
            return node
    raise AssertionError("no Dataset JSON-LD on the page")


# --- 1. the line, as it renders --------------------------------------------


def test_the_line_links_the_feed_and_its_mobility_database_history() -> None:
    line = _line(_page(_artifact()))
    assert line == (
        f'<p class="feed-source">Source feed: <a href="{_BARRIE_URL}">{_BARRIE_URL}</a> '
        '<span aria-hidden="true">&middot;</span> '
        f'<a href="{_BARRIE_MDB}">Version history on the Mobility Database</a></p>'
    )


def test_no_mobility_database_id_keeps_the_source_and_drops_only_the_history() -> None:
    line = _line(_page(_artifact(), dir_record=_record(mdb_id="")))
    assert f'href="{_BARRIE_URL}"' in line
    assert "Mobility Database" not in line


@pytest.mark.parametrize("agency_id", ["unitrans", "yolobus", "barrie-transit"])
def test_every_golden_scorecard_links_its_feed_and_never_this_site(agency_id: str) -> None:
    html = (_GOLDENS / "agency" / agency_id / "index.html").read_text()
    line = _line(html)
    assert line.startswith('<p class="feed-source">Source feed: <a href="http')
    hrefs = _HREF_RE.findall(line)
    for href in hrefs:
        host = urlsplit(href).hostname or ""
        assert host and not host.endswith("gtfsscorecard.org"), f"{agency_id}: {href}"
    # The JSON-LD names the same source the reader sees.
    assert _dataset_jsonld(html)["isBasedOn"] == hrefs[0]


def test_only_the_scorecard_carries_the_line_not_the_brief_or_board() -> None:
    for page in sorted((_GOLDENS / "agency").rglob("*.html")):
        rel = page.relative_to(_GOLDENS).as_posix()
        if rel.count("/") > 2:
            assert 'class="feed-source"' not in page.read_text(), rel


def test_the_line_escapes_the_url_it_prints() -> None:
    line = _source_feed_line('https://ex.org/g.zip?a=1&b="x"', None)
    assert 'href="https://ex.org/g.zip?a=1&amp;b=&quot;x&quot;"' in line
    assert '"x"' not in line


# --- 2. no public source, no line (negative controls) ----------------------

_Sabotage = Callable[[dict[str, Any]], None]
_Landed = Callable[[dict[str, Any]], bool]


def _local_zip(a: dict[str, Any]) -> None:
    a["feed"]["static_url"] = "Google_transit.zip"


def _no_url(a: dict[str, Any]) -> None:
    del a["feed"]["static_url"]


def _javascript(a: dict[str, Any]) -> None:
    a["feed"]["static_url"] = "javascript:alert(1)"


def _credentialed(a: dict[str, Any]) -> None:
    a["fetch"] = {"source": "origin", "auth": "credentialed", "auth_kind": "header"}


def _this_site(a: dict[str, Any]) -> None:
    a["feed"]["static_url"] = "https://gtfsscorecard.org/data/artifacts/barrie-transit/feed.zip"


def _this_site_subdomain(a: dict[str, Any]) -> None:
    a["feed"]["static_url"] = "https://files.gtfsscorecard.org/barrie.zip"


_SABOTAGE: dict[str, tuple[_Sabotage, _Landed]] = {
    "local-zip": (_local_zip, lambda a: a["feed"]["static_url"] == "Google_transit.zip"),
    "no-url": (_no_url, lambda a: "static_url" not in a["feed"]),
    "javascript-url": (_javascript, lambda a: a["feed"]["static_url"].startswith("javascript:")),
    "credentialed": (_credentialed, lambda a: a["fetch"]["auth_kind"] == "header"),
    "this-site": (_this_site, lambda a: "//gtfsscorecard.org/" in a["feed"]["static_url"]),
    "this-site-subdomain": (
        _this_site_subdomain,
        lambda a: ".gtfsscorecard.org/" in a["feed"]["static_url"],
    ),
}


@pytest.mark.parametrize("case", sorted(_SABOTAGE))
def test_negative_control_no_public_source_renders_no_line_and_no_isbasedon(case: str) -> None:
    control = _page(_artifact())
    assert "Source feed:" in control and '"isBasedOn"' in control, (
        "the unsabotaged control renders no source line; this proves nothing"
    )

    sabotage, landed = _SABOTAGE[case]
    artifact = _artifact()
    sabotage(artifact)
    assert landed(artifact), f"{case}: the sabotage did not apply"
    html = _page(artifact)
    assert "Source feed" not in html
    assert 'class="feed-source"' not in html
    # No Mobility Database link on its own either: no label without a link.
    assert "mobilitydatabase.org/feeds/" not in html
    assert '"isBasedOn"' not in html


def test_negative_control_a_withheld_publisher_renders_no_line_and_no_isbasedon() -> None:
    assert "Source feed:" in _page(_artifact(), source_withheld=False)
    html = _page(_artifact(), source_withheld=True)
    assert "Source feed" not in html
    assert '"isBasedOn"' not in html
    assert _BARRIE_URL not in html.partition("<footer")[0].partition('id="report-overview"')[2]


def test_public_source_url_is_the_one_rule_for_both_surfaces() -> None:
    artifact = _artifact()
    assert _public_source_url(artifact) == _BARRIE_URL
    assert _public_source_url(artifact, withheld=True) is None
    assert _source_feed_line(None, _BARRIE_MDB) == ""


# --- 3. who is withheld -------------------------------------------------------


def _agency(block: LicenseBlock | None) -> Agency:
    return Agency(
        id="demo",
        name="Demo Transit",
        static_gtfs_url="https://ex.org/g.zip",
        license_block=block,
    )


def _block(redistribution: bool | str) -> LicenseBlock:
    return LicenseBlock(
        id="other",
        attribution_required="unknown",
        redistribution_allowed=redistribution,  # type: ignore[arg-type]
        share_alike="unknown",
        status="needs_review",
    )


def test_only_a_license_that_forbids_redistribution_withholds_the_link() -> None:
    assert _license_forbids_redistribution(_agency(_block(False))) is True
    assert _license_forbids_redistribution(_agency(_block(True))) is False
    assert _license_forbids_redistribution(_agency(_block("unknown"))) is False
    assert _license_forbids_redistribution(_agency(None)) is False
    assert _license_forbids_redistribution(None) is False


def test_the_exclusion_ledger_withholds_its_ids_and_fails_closed(tmp_path: Path) -> None:
    ledger = tmp_path / "history-export-exclusions.yaml"
    assert _withheld_source_ids(tmp_path) is None, "a missing ledger must withhold every link"
    ledger.write_text("excluded: []\n")
    assert _withheld_source_ids(tmp_path) == frozenset()
    ledger.write_text(
        "excluded:\n"
        "  - agency_id: barrie-transit\n"
        '    requested_on: "2026-10-01"\n'
        "    reason: test request\n"
    )
    assert _withheld_source_ids(tmp_path) == frozenset({"barrie-transit"})
    ledger.write_text("not: [a ledger\n")
    assert _withheld_source_ids(tmp_path) is None


def test_the_repo_ledger_is_readable_so_the_live_render_links_sources() -> None:
    assert _withheld_source_ids(_REPO) is not None
    assert _withheld_source_ids(_FIXTURE) is not None


# --- 4. the Mobility Database link is never guessed ---------------------------


@pytest.mark.parametrize(
    ("mdb_id", "page"),
    [
        ("3", "https://mobilitydatabase.org/feeds/gtfs/mdb-3"),
        (3, "https://mobilitydatabase.org/feeds/gtfs/mdb-3"),
        ("0003", "https://mobilitydatabase.org/feeds/gtfs/mdb-3"),
        ("mdb-225", "https://mobilitydatabase.org/feeds/gtfs/mdb-225"),
        ("tld-764", "https://mobilitydatabase.org/feeds/gtfs/tld-764"),
        ("ntd-44929", "https://mobilitydatabase.org/feeds/gtfs/ntd-44929"),
        ("tdg-83582", "https://mobilitydatabase.org/feeds/gtfs/tdg-83582"),
    ],
)
def test_a_known_mobility_database_id_links_its_feed_page(mdb_id: object, page: str) -> None:
    assert _mdb_feed_page(mdb_id) == page


@pytest.mark.parametrize(
    "mdb_id",
    ["", None, True, "abc", "mdb-", "xyz-12", "3/../../admin", "mdb-3?x=1", " ", 3.5],
)
def test_an_unknown_mobility_database_id_is_omitted(mdb_id: object) -> None:
    assert _mdb_feed_page(mdb_id) is None
