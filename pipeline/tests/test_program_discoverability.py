"""How the program rollups and /bundle/ are found from outside the site.

Internal linking is covered next door in ``test_paid_tier_visibility.py``: a
reader can now reach every rollup from an indexable page. These tests cover the
other half, which is what a machine gets when it arrives — the structured data
each page publishes about itself, and whether the build can silently stop
publishing it.

Four properties, and each is here because its absence is invisible:

1. **A rollup says it is a dataset, and names downloads the site really ships.**
   A ``DataDownload`` is the only part of a structured-data block that promises
   something outside the page. Nothing in a golden diff, an accessibility scan,
   or a link checker reads inside a ``<script type="application/ld+json">``
   block, so a distribution can 404 for every machine reader while every gate
   stays green. The deploy-time half of this lives in
   ``check_site_seo.py::_validate_json_ld_distributions``, which resolves those
   URLs against the assembled ``_site`` — that is where the public-artifact
   allowlist is actually tested.
2. **The dataset node restates no aggregate the page guards.** A structured
   block is the classic place for a withheld number to reappear as a confident
   one: the page prints "average unavailable" and the machine-readable twin
   prints 62.3. This asserts the node cannot, for every rollup in the real
   artifact store rather than for the three in the fixture.
3. **Dates describe content, not the build.** ``dateModified`` and the sitemap
   ``lastmod`` come from the newest member snapshot, never from the payload's
   ``generated_at``, which every deploy rewrites.
4. **The gate that would notice is configured.** ``required_json_ld_types`` is
   data in ``site-seo.json``; deleting an entry from it removes a blocking
   check with no code change and no test failure anywhere else.

**What these assert over.** Like ``test_paid_tier_visibility.py`` next door, the
rendered-output tests read the committed goldens -- the render's output of
record -- rather than rendering here. ``test_render_golden.py`` is what binds
those goldens to the renderer, so a renderer change that dropped a Dataset node
or a sitemap ``lastmod`` reddens that test when the goldens are not refreshed,
and reddens these when they are. Measured rather than assumed: a negative
control that sabotaged only the renderer left the ``lastmod`` test green and
reddened ``test_render_site_golden_output`` instead, which is what the two-step
chain looks like from the inside.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from scorecard_pipeline.render_site import _rollup_content_date, _rollup_dataset_jsonld
from scorecard_pipeline.rollups import csv_column_headers

# pipeline/tests/test_program_discoverability.py -> parents[2] is the repo root.
_REPO = Path(__file__).resolve().parents[2]
_GOLDENS = _REPO / "pipeline" / "tests" / "goldens"
_ROLLUP_STORE = _REPO / "data" / "artifacts" / "rollups"
_ORIGIN = "https://gtfsscorecard.org"
_JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _configured_rollup_ids() -> set[str]:
    """Every rollup slug rollups.yaml declares — derived, never listed here."""
    document = yaml.safe_load((_REPO / "rollups.yaml").read_text())
    return {str(entry["id"]) for entry in (document or {}).get("rollups", [])}


def _golden_rollup_ids() -> set[str]:
    program = _GOLDENS / "program"
    return {
        child.name
        for child in program.iterdir()
        if child.is_dir() and (child / "index.html").is_file()
    }


def _json_ld_nodes(html: str) -> list[dict[str, Any]]:
    """Every top-level JSON-LD node in a page, parsed.

    One ``<script>`` per node is what ``site_shell._page`` emits, and parsing
    each one separately is what makes "this page publishes two nodes" a
    statement a test can fail on.
    """
    nodes: list[dict[str, Any]] = []
    for block in _JSON_LD_RE.findall(html):
        value = json.loads(block)
        nodes.extend(value if isinstance(value, list) else [value])
    return nodes


def _nodes_of_type(nodes: list[dict[str, Any]], type_name: str) -> list[dict[str, Any]]:
    return [node for node in nodes if node.get("@type") == type_name]


def _identified_nodes(value: Any) -> list[tuple[str, dict[str, Any]]]:
    """Every ``@id``-bearing node in a JSON-LD value, at any depth.

    A node carrying only ``@id`` is a bare pointer and is skipped: it makes no
    claim, so there is nothing for the drift check below to compare.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        identifier = value.get("@id")
        if isinstance(identifier, str) and len(value) > 1:
            found.append((identifier, value))
        for child in value.values():
            found.extend(_identified_nodes(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_identified_nodes(child))
    return found


def _page_identified_nodes(html: str) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for block in _JSON_LD_RE.findall(html):
        found.extend(_identified_nodes(json.loads(block)))
    return found


def _content_urls(node: dict[str, Any]) -> list[str]:
    distribution = node.get("distribution")
    entries = distribution if isinstance(distribution, list) else [distribution]
    return [
        entry["contentUrl"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("contentUrl"), str)
    ]


# --- a rollup is a listing page and a dataset, and says both ---------------


def test_every_rendered_rollup_publishes_a_dataset_beside_its_collection_page() -> None:
    """Both nodes, on every rollup the render wrote, with the page's own URL.

    A rollup page is two things and a crawler should be able to tell: a listing
    a person reads, and a dataset a machine can take away. Publishing only the
    CollectionPage is what the page did before, and it is why 67 pages of
    graded public-agency data were invisible to every dataset index.
    """
    published = _golden_rollup_ids()
    assert published, "no rollup goldens were rendered; this gate would pass vacuously"

    for rollup_id in sorted(published):
        html = (_GOLDENS / "program" / rollup_id / "index.html").read_text()
        nodes = _json_ld_nodes(html)
        canonical = f"{_ORIGIN}/program/{rollup_id}/"

        collection = _nodes_of_type(nodes, "CollectionPage")
        datasets = _nodes_of_type(nodes, "Dataset")
        assert len(collection) == 1, (
            f"{rollup_id}: expected one CollectionPage, got {len(collection)}"
        )
        assert len(datasets) == 1, f"{rollup_id}: expected one Dataset node, got {len(datasets)}"

        for node in (*collection, *datasets):
            assert node.get("@context") == "https://schema.org", (
                f"{rollup_id}: {node.get('@type')} carries no schema.org @context, so "
                "check_site_seo.py's required-type check cannot accept it"
            )
            assert node.get("url") == canonical, (
                f"{rollup_id}: {node.get('@type')} url is {node.get('url')!r}, "
                f"not this page's canonical {canonical!r}"
            )


def test_the_rollup_dataset_advertises_only_downloads_the_artifact_store_holds() -> None:
    """The two files named in ``distribution`` exist for every declared rollup.

    ``publish_rollups`` writes ``<id>.json`` and ``<id>.csv`` side by side and
    ``assemble_public_artifacts.sh`` copies both across the deployment
    boundary by an allowlist. This asserts the source half — the store really
    holds what the page offers — for every id ``rollups.yaml`` declares, not
    only the three the golden fixture renders. The destination half, whether
    the allowlist still lets them through, is asserted at deploy time by
    ``jsonld.missing_distribution`` over the assembled site.
    """
    configured = _configured_rollup_ids()
    assert configured, "rollups.yaml declares no rollups; this gate would pass vacuously"
    assert _ROLLUP_STORE.is_dir(), f"no rollup artifact store at {_ROLLUP_STORE}"

    for rollup_id in sorted(configured):
        for suffix in ("json", "csv"):
            path = _ROLLUP_STORE / f"{rollup_id}.{suffix}"
            assert path.is_file(), (
                f"/program/{rollup_id}/ advertises a .{suffix} download, but "
                f"{path.relative_to(_REPO)} is not in the artifact store"
            )

    for rollup_id in sorted(_golden_rollup_ids()):
        html = (_GOLDENS / "program" / rollup_id / "index.html").read_text()
        (dataset,) = _nodes_of_type(_json_ld_nodes(html), "Dataset")
        assert _content_urls(dataset) == [
            f"{_ORIGIN}/data/artifacts/rollups/{rollup_id}.json",
            f"{_ORIGIN}/data/artifacts/rollups/{rollup_id}.csv",
        ], f"{rollup_id}: the advertised downloads are not the published artifact paths"


def test_the_rollup_dataset_variables_are_the_published_csv_columns() -> None:
    """``variableMeasured`` is the CSV's own header row, read from both ends.

    Naming variables by hand is how a structured block starts describing a file
    that has since gained or lost a column. The renderer reads
    ``rollups.csv_column_headers()``; this asserts that list is also literally
    the first line of a published CSV, so the claim is checked against the
    artifact and not only against the constant that generated it.
    """
    headers = list(csv_column_headers())
    assert headers, "the CSV column table is empty; this test would prove nothing"

    published = sorted(_golden_rollup_ids())
    assert published, "no rollup goldens were rendered; this gate would pass vacuously"
    for rollup_id in published:
        html = (_GOLDENS / "program" / rollup_id / "index.html").read_text()
        (dataset,) = _nodes_of_type(_json_ld_nodes(html), "Dataset")
        assert dataset.get("variableMeasured") == headers, (
            f"{rollup_id}: the dataset names variables the CSV writer does not publish"
        )

    sample = next(iter(sorted(_ROLLUP_STORE.glob("*.csv"))), None)
    assert sample is not None, "the artifact store publishes no rollup CSV to check against"
    assert sample.read_text().splitlines()[0].split(",") == headers, (
        f"{sample.name}'s header row and csv_column_headers() have drifted apart"
    )


def test_the_rollup_dataset_restates_no_cross_feed_average() -> None:
    """The machine-readable twin cannot publish an average, guarded or not.

    ``_rollup_guarded_summary`` decides whether the page may print a cross-feed
    average; a rollup with no comparison cohort prints "average unavailable"
    instead. A Dataset node is exactly where that withheld number reappears as
    a confident one, so the node states no aggregate at all — it names what is
    measured (the CSV's columns) and never a measurement.

    Asserted over every payload in the real artifact store rather than the
    three in the fixture, because the fixture's rollups all happen to have a
    publishable average: a prohibition is only as wide as the documents the
    test hands it.
    """
    payload_files = sorted(
        path for path in _ROLLUP_STORE.glob("*.json") if path.name != "index.json"
    )
    assert len(payload_files) > 10, (
        f"only {len(payload_files)} rollup payloads found; the sweep collapsed"
    )

    checked = 0
    for path in payload_files:
        payload = json.loads(path.read_text())
        average = payload.get("average_score")
        if not isinstance(average, (int, float)) or isinstance(average, bool):
            continue
        rollup_id = str(payload["rollup"]["id"])
        canonical = f"{_ORIGIN}/program/{rollup_id}/"
        # A sentinel description isolates the structured fields: the real meta
        # description is the page's own visible sentence and is published here
        # only because the page already prints it.
        node = _rollup_dataset_jsonld(payload, "description under test", canonical)
        serialized = json.dumps(node)
        assert str(average) not in serialized, (
            f"{rollup_id}: the dataset node restates the cross-feed average "
            f"{average}, which the page publishes only when it is guarded"
        )
        checked += 1
    assert checked > 10, f"only {checked} payloads carried an average; the sweep proved little"


def test_the_rollup_date_is_content_not_the_build_clock() -> None:
    """``dateModified`` is the newest member snapshot, never ``generated_at``.

    Every deploy runs ``scorecard rollups`` before rendering, so a payload's
    ``generated_at`` is the moment of the build. Publishing it — as a date on
    the page or as a sitemap ``<lastmod>`` — would tell a crawler that all 68
    program pages changed every time the site was rebuilt. A member's
    ``snapshot_date`` is when that feed was actually checked, so it moves only
    when the data does.

    The three cases below are not reachable by reading the committed artifacts:
    every real payload carries dated members, which is exactly why the
    no-date branches have to be constructed.
    """
    payload = json.loads((_ROLLUP_STORE / "all.json").read_text())
    canonical = f"{_ORIGIN}/program/all/"
    newest = max(member["snapshot_date"] for member in payload["members"])
    build_day = str(payload["generated_at"])[:10]

    node = _rollup_dataset_jsonld(payload, "description under test", canonical)
    assert node["dateModified"] == newest
    assert _rollup_content_date(payload) == newest
    if newest != build_day:
        assert node["dateModified"] != build_day, (
            "the rollup publishes its build date, so every rebuild would announce 68 changed pages"
        )

    for broken, why in (
        ({**payload, "members": []}, "no members"),
        ({**payload, "members": [{"snapshot_date": "the seventh of August"}]}, "unparseable"),
        ({**payload, "members": [{"id": "x"}]}, "undated"),
    ):
        assert _rollup_content_date(broken) == "", why
        assert "dateModified" not in _rollup_dataset_jsonld(broken, "d", canonical), why


def test_every_rollup_url_in_the_sitemap_carries_a_lastmod() -> None:
    """A crawler schedules by ``<lastmod>``; the rollups were the family with none.

    The sitemap comment in ``render_site`` already draws the line: a generated
    page passes a date it can source, a hand-authored page passes none. The 67
    rollups and their index are generated and had a date available in their own
    payloads, so their silence was an omission rather than the decision the
    comment describes.
    """
    sitemap = (_GOLDENS / "sitemap.xml").read_text()
    entries = re.findall(r"<url>(.*?)</url>", sitemap, re.S)
    assert entries, "the golden sitemap has no entries; this gate would pass vacuously"

    program_entries = [entry for entry in entries if f"<loc>{_ORIGIN}/program/" in entry]
    expected = len(_golden_rollup_ids()) + 1  # the rollups plus the /program/ index
    assert len(program_entries) == expected, (
        f"expected {expected} program URLs in the sitemap, found {len(program_entries)}"
    )
    for entry in program_entries:
        location = re.search(r"<loc>(.*?)</loc>", entry)
        assert location is not None
        assert re.search(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", entry), (
            f"{location.group(1)} is in the sitemap with no lastmod a crawler can schedule by"
        )


# --- /bundle/ names the entities it points at -----------------------------


def test_bundle_jsonld_stubs_match_the_home_page_nodes() -> None:
    """Every field /bundle/ repeats from a home-page node still equals it.

    ``/bundle/``'s Service node points at the site Organization and at the free
    single-agency scorecard by ``@id``. Both are defined in full on the home
    page, and cross-document ``@id`` merging is not something to count on, so
    each reference also carries that node's ``@type``, ``name`` and ``url`` --
    enough for a crawler reading only ``/bundle/`` to know who the provider is.

    Repeating three fields is repeating three fields, so this asserts they have
    not drifted: the home page stays the definition, and renaming the
    organisation there fails here instead of leaving two names in the graph.
    """
    web = _REPO / "web"
    definitions = dict(_page_identified_nodes((web / "index.html").read_text()))
    assert definitions, "the home page defines no identified JSON-LD nodes"

    stubs = [
        (identifier, node)
        for identifier, node in _page_identified_nodes((web / "bundle" / "index.html").read_text())
        if identifier in definitions and node is not definitions[identifier]
    ]
    assert len(stubs) >= 2, (
        f"/bundle/ names only {len(stubs)} home-page entities inline; a crawler "
        "reading that page alone gets a provider with no name"
    )

    for identifier, stub in stubs:
        definition = definitions[identifier]
        for key, value in stub.items():
            if key == "@id":
                continue
            assert definition.get(key) == value, (
                f"/bundle/ says {key}={value!r} for {identifier}, but the home "
                f"page defines {key}={definition.get(key)!r}"
            )


# --- and the deploy gate is configured to notice --------------------------


def test_the_structural_seo_gate_requires_the_structured_data_these_pages_publish() -> None:
    """``required_json_ld_types`` is data, so deleting an entry breaks no code.

    Everything above tests the render. This tests the only thing that runs
    against the deployed tree: without these patterns in ``site-seo.json``, a
    page could stop publishing its Service or Dataset node and every check
    would still pass, on all 68 program pages at once.

    ``check_site_seo.py`` also refuses a pattern that matches no page
    (``jsonld.pattern_unmatched``), so an entry here cannot go stale silently
    in the other direction either.
    """
    config = json.loads((_REPO / "site-seo.json").read_text())
    required = config["required_json_ld_types"]
    for pattern, types in (
        ("/agency/*/", {"Dataset"}),
        ("/bundle/", {"Service", "Product"}),
        ("/program/", {"CollectionPage"}),
        ("/program/*/", {"CollectionPage", "Dataset"}),
    ):
        assert pattern in required, f"{pattern} is no longer gated for structured data"
        assert types <= set(required[pattern]), (
            f"{pattern} no longer requires {sorted(types - set(required[pattern]))}"
        )
