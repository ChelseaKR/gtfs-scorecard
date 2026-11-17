"""JSON written into a ``<script>`` element stays inside that element.

A script element is read by the HTML parser before anything reads the JSON in
it, so the JSON has to be written for both readers. ``json_for_script`` is the
one serializer the site shell and page renderers use for that; these tests hold
the serializer, each place that uses it, and the rule that nothing writes JSON
into a script element another way.
"""

from __future__ import annotations

import ast
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import pages_tools, render_site, site_shell
from scorecard_pipeline.render_site import _agency_map_script, _render_agency
from scorecard_pipeline.site_shell import _page, json_for_script

SRC = Path(__file__).resolve().parents[1] / "src" / "scorecard_pipeline"

# Text a registry name, note or URL could carry. Each one holds a character the
# HTML parser or an older JavaScript parser gives a meaning of its own.
HOSTILE_TEXT = [
    "Demo </script><p id=after>Transit",
    "Demo </SCRIPT ><p id=after>Transit",
    "Demo <!-- <script> Transit",
    "Demo & Sons <b>Transit</b>",
    "Demo\u2028Transit\u2029Authority",
    "Demo ]]> Transit",
]


class _Elements(HTMLParser):
    """What an HTML parser makes of a document: script bodies and other tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_bodies: list[str] = []
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self._in_script = True
            self.script_bodies.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.script_bodies[-1] += data


def _parse(document: str) -> _Elements:
    parser = _Elements()
    parser.feed(document)
    parser.close()
    return parser


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_json_for_script_round_trips_and_writes_no_markup_characters(text: str) -> None:
    value = {"name": text, "nested": [text, {"k": text}]}
    for ensure_ascii in (True, False):
        written = json_for_script(value, ensure_ascii=ensure_ascii)
        assert json.loads(written) == value
        for char in ("<", ">", "&", "\u2028", "\u2029"):
            assert char not in written


def test_json_for_script_leaves_ordinary_values_as_compact_json() -> None:
    value = {"@type": "Dataset", "name": "Demo Transit", "n": 3, "ok": True, "none": None}
    assert json_for_script(value) == json.dumps(value, separators=(",", ":"))
    assert json_for_script({"name": "Montréal"}, ensure_ascii=False) == '{"name":"Montréal"}'
    assert json_for_script({"name": "Montréal"}) == '{"name":"Montr\\u00e9al"}'


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_page_shell_keeps_each_jsonld_node_in_its_own_script_element(text: str) -> None:
    nodes: list[dict[str, Any]] = [
        {"@context": "https://schema.org", "@type": "Dataset", "name": text},
        {"@context": "https://schema.org", "@type": "WebPage", "description": text},
    ]
    document = _page(
        title="Demo",
        description="Demo page",
        canonical="/demo/",
        body="<p>body</p>",
        jsonld=nodes,
    )
    parsed = _parse(document)
    ld_bodies = [body for body in parsed.script_bodies if body.lstrip().startswith('{"@context"')]
    assert [json.loads(body) for body in ld_bodies] == nodes
    assert not any(attrs.get("id") == "after" for _tag, attrs in parsed.tags)
    assert not any(tag == "b" for tag, _attrs in parsed.tags)


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_agency_page_jsonld_survives_a_hostile_registry_name(text: str) -> None:
    artifact: dict[str, Any] = {
        "agency": {"id": "demo", "name": text},
        "overall": {"grade": "C", "score": 74.0},
        "snapshot_date": "2026-10-02",
        "categories": {"realtime": {"status": "not_yet_measured"}},
    }
    document = _render_agency(artifact, dir_record={"state": text})
    parsed = _parse(document)
    ld_bodies = [body for body in parsed.script_bodies if body.lstrip().startswith('{"@context"')]
    assert ld_bodies, "the agency page lost its JSON-LD block"
    for body in ld_bodies:
        node = json.loads(body)
        assert isinstance(node, dict)
    assert any(text in json.dumps(json.loads(body), ensure_ascii=False) for body in ld_bodies)
    # Nothing in the name became an element of its own.
    assert not any(attrs.get("id") == "after" for _tag, attrs in parsed.tags)
    assert not any(tag == "b" for tag, _attrs in parsed.tags)


@pytest.mark.parametrize("region", ["bundle_offers_region", "history_offers_region"])
@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_offer_regions_keep_their_jsonld_in_one_script_element(
    monkeypatch: pytest.MonkeyPatch, region: str, text: str
) -> None:
    node = {"@context": "https://schema.org", "@type": "Service", "name": text}
    source = "bundle_offers_jsonld" if region == "bundle_offers_region" else "history_offers_jsonld"
    monkeypatch.setattr(site_shell, source, lambda _plan: node)
    parsed = _parse(getattr(site_shell, region)({}))
    assert [json.loads(body) for body in parsed.script_bodies] == [node]
    assert [tag for tag, _attrs in parsed.tags] == ["script"]


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_agency_map_script_reads_its_url_as_one_string(text: str) -> None:
    parsed = _parse(_agency_map_script(f"/map/{text}.geojson"))
    assert len(parsed.script_bodies) == 1
    assert [tag for tag, _attrs in parsed.tags] == ["script"]
    line = next(ln for ln in parsed.script_bodies[0].splitlines() if "var geoUrl =" in ln)
    literal = line.split("var geoUrl =", 1)[1].strip().rstrip(";")
    assert json.loads(literal) == f"/map/{text}.geojson"


def _script_interpolations(path: Path) -> list[tuple[int, str]]:
    """Every expression an f-string interpolates between ``<script`` and ``</script>``."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.JoinedStr):
            continue
        in_script = False
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                opened, closed = part.value.rfind("<script"), part.value.rfind("</script>")
                if opened != closed:
                    in_script = opened > closed
            elif isinstance(part, ast.FormattedValue) and in_script:
                found.append((node.lineno, ast.unparse(part.value)))
    return found


def test_no_renderer_writes_json_into_a_script_element_another_way() -> None:
    """``json.dumps`` output is not safe in a script element; the helper's is.

    Walks every f-string in the package. An interpolation that sits inside a
    script element and calls ``json.dumps`` directly is the pattern this file
    exists to keep out, wherever a later page adds it.
    """
    offenders = [
        f"{path.name}:{line}: {expr}"
        for path in sorted(SRC.glob("*.py"))
        for line, expr in _script_interpolations(path)
        if "json.dumps" in expr
    ]
    assert not offenders, "use site_shell.json_for_script here: " + "; ".join(offenders)


def test_values_built_for_inline_scripts_come_from_the_helper() -> None:
    """The names inline scripts read are assigned from ``json_for_script``.

    The f-string walk above sees ``{labels}`` or ``{type_expr}``, not how the
    name was built. These are the names that hold JSON today; each must be
    assigned from the helper in its module.
    """
    expected = {
        pages_tools: ["labels = json_for_script("],
        render_site: [
            "country_labels_json = json_for_script(",
            "type_expr = json_for_script(",
            "grade_expr = json_for_script(",
            '.replace("__GEO_URL_JSON__", json_for_script(geo_url))',
        ],
    }
    for module, assignments in expected.items():
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        for assignment in assignments:
            assert assignment in source, f"{module.__name__}: {assignment}"
