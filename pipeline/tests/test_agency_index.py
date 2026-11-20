"""The small agency index and the matching the agency pickers do with it.

The builder (``agency_index.py``) is tested directly. The matching lives in the
browser (``web/src/agency-combobox.js``), so those tests run the real script
under Node, the way ``test_consequence_web.py`` runs ``consequence.js``: the
script is a classic file that defines ``globalThis.ScorecardAgencySearch``, and
importing it for its side effect is enough.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.agency_index import FIELDS, INDEX_PATH, build_agency_index

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
GENERATED_AT = "2026-11-19T00:00:00+00:00"


# --- the builder -------------------------------------------------------------


def test_index_rows_are_compact_sorted_and_carry_the_page_slug() -> None:
    payload = build_agency_index(
        [
            {"id": "yolobus", "name": "Yolobus", "country": "US", "subdivision_name": "California"},
            {"id": "barrie-transit", "name": "Barrie  Transit\n(Ontario)", "country": "CA"},
            {"id": "unitrans", "name": "Unitrans", "country": "US"},
        ],
        generated_at=GENERATED_AT,
    )
    assert payload == {
        "schema_version": 1,
        "generated_at": GENERATED_AT,
        "fields": ["id", "name", "slug", "place"],
        "agencies": [
            ["barrie-transit", "Barrie Transit (Ontario)", "barrie-transit", "CA"],
            ["unitrans", "Unitrans", "unitrans", "US"],
            ["yolobus", "Yolobus", "yolobus", "California"],
        ],
    }
    assert list(FIELDS) == payload["fields"]


def test_index_drops_rows_that_could_not_be_a_page_link() -> None:
    payload = build_agency_index(
        [
            {"id": "", "name": "No id"},
            {"id": "Has Spaces", "name": "Bad id"},
            {"id": "../escape", "name": "Bad id"},
            {"id": "no-name", "name": "   "},
            {"id": "kept", "name": "Kept"},
            {"id": "kept", "name": "Second record for the same id"},
        ],
        generated_at=GENERATED_AT,
    )
    assert payload["agencies"] == [["kept", "Kept", "kept", ""]]


def test_index_keeps_names_exactly_as_published() -> None:
    # Accents and unusual apostrophes are folded at match time, not here: the
    # index shows the reader the agency's own spelling.
    payload = build_agency_index(
        [{"id": "homage-d-arling-direct", "name": "Homage: D\u02bcArling Direct"}],
        generated_at=GENERATED_AT,
    )
    assert payload["agencies"][0][1] == "Homage: D\u02bcArling Direct"


def test_index_for_the_whole_corpus_stays_small() -> None:
    # Production publishes about 2,500 agencies. Twice that, with long names,
    # must still be a small download next to the 84 MB history index the
    # alerts form used to unpack.
    catalog = [
        {
            "id": f"agency-number-{n:05d}",
            "name": f"Regional Transportation Authority of County Number {n} (RTA{n})",
            "subdivision_name": "Massachusetts",
        }
        for n in range(5000)
    ]
    text = json.dumps(
        build_agency_index(catalog, generated_at=GENERATED_AT),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert len(text.encode()) < 800_000
    assert len(gzip.compress(text.encode())) < 150_000


def test_render_site_writes_the_index_where_the_pickers_read_it() -> None:
    source = (ROOT / "pipeline" / "src" / "scorecard_pipeline" / "render_site.py").read_text()
    assert "build_agency_index(catalog" in source
    picker = (WEB / "src" / "agency-combobox.js").read_text()
    assert f'"/{INDEX_PATH}"' in picker


def test_committed_index_matches_the_committed_catalog() -> None:
    # web/ is committed build output; the index must agree with the catalog
    # beside it, or local and end-to-end runs suggest agencies with no page.
    catalog = json.loads((WEB / "catalog.json").read_text())["agencies"]
    committed = json.loads((WEB / INDEX_PATH).read_text())
    rebuilt = build_agency_index(catalog, generated_at=committed["generated_at"])
    assert committed == rebuilt


# --- the matching, run in Node -------------------------------------------------

_HARNESS = """
import { readFileSync } from "node:fs";
await import("./agency-combobox.js");
const search = globalThis.ScorecardAgencySearch;
const { payload, calls } = JSON.parse(readFileSync(process.argv[2], "utf8"));
const records = search.prepare(payload);
const out = calls.map(([fn, query, limit]) => {
  if (fn === "fold") return search.fold(query);
  if (fn === "rank") {
    const result = search.rank(records, query, limit);
    return { ids: result.matches.map((r) => r.id), total: result.total };
  }
  if (fn === "clear") {
    const record = search.clearMatch(records, query);
    return record ? record.id : null;
  }
  throw new Error("unknown call " + fn);
});
process.stdout.write(JSON.stringify(out));
"""

AGENCIES = [
    {"id": "bay-area-rapid-transit-bart", "name": "Bay Area Rapid Transit (BART)"},
    {
        "id": "berks-area-regional-transportation-authority-barta",
        "name": "Berks Area Regional Transportation Authority (BARTA)",
    },
    {"id": "broome-county-transit-b-c-transit", "name": "Broome County Transit (B.C. Transit)"},
    {"id": "blue-gold-fleet", "name": "Blue & Gold Fleet"},
    {"id": "homage-d-arling-direct", "name": "Homage: D\u02bcArling Direct"},
    {"id": "saint-marys-transit-system", "name": "Saint Mary\u02bcs Transit System"},
    {
        "id": "societe-de-transport-de-montreal",
        "name": "Soci\u00e9t\u00e9 de transport de Montr\u00e9al",
    },
    {"id": "unitrans", "name": "Unitrans (ASUCD / City of Davis)"},
    {"id": "yolobus", "name": "Yolobus (Yolo County Transportation District)"},
    {"id": "annapolis-transit", "name": "Annapolis Transit"},
    {"id": "annapolis-transit-2", "name": "Annapolis Transit"},
    {"id": "abq-ride", "name": "ABQ RIDE"},
]


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("agency-combobox")
    (folder / "package.json").write_text('{"type": "module"}')
    shutil.copy(WEB / "src" / "agency-combobox.js", folder / "agency-combobox.js")
    (folder / "run.mjs").write_text(_HARNESS)
    return folder


def run_js(sandbox: Path, calls: list[list[Any]]) -> list[Any]:
    node = shutil.which("node")
    assert node is not None, "node is required for the web tests"
    payload = build_agency_index(AGENCIES, generated_at=GENERATED_AT)
    cases = sandbox / "cases.json"
    cases.write_text(json.dumps({"payload": payload, "calls": calls}))
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [node, str(sandbox / "run.mjs"), str(cases)],
        check=True,
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def test_folding_ignores_case_accents_apostrophes_and_punctuation(sandbox: Path) -> None:
    assert run_js(
        sandbox,
        [
            ["fold", "  Soci\u00e9t\u00e9 de TRANSPORT  "],
            ["fold", "Saint Mary\u02bcs"],
            ["fold", "saint mary's"],
            ["fold", "SAINT MARY\u2019S"],
            ["fold", "Blue & Gold"],
            ["fold", "B.C. Transit"],
            ["fold", "Homage: D\u02bcArling"],
        ],
    ) == [
        "societe de transport",
        "saint marys",
        "saint marys",
        "saint marys",
        "blue and gold",
        "b c transit",
        "homage darling",
    ]


def test_case_and_accents_do_not_matter(sandbox: Path) -> None:
    rank = run_js(
        sandbox, [["rank", "societe de transport de montreal", 8], ["rank", "ABQ ride", 8]]
    )
    assert rank[0]["ids"] == ["societe-de-transport-de-montreal"]
    assert rank[1]["ids"] == ["abq-ride"]


def test_punctuation_does_not_matter(sandbox: Path) -> None:
    results = run_js(
        sandbox,
        [
            ["rank", "bc transit", 8],
            ["rank", "blue and gold", 8],
            ["rank", "darling", 8],
            ["rank", "saint marys", 8],
        ],
    )
    assert results[0]["ids"][0] == "broome-county-transit-b-c-transit"
    assert results[1]["ids"] == ["blue-gold-fleet"]
    assert results[2]["ids"] == ["homage-d-arling-direct"]
    assert results[3]["ids"] == ["saint-marys-transit-system"]


def test_an_abbreviation_in_the_name_ranks_its_agency_first(sandbox: Path) -> None:
    bart, barta, partial = run_js(
        sandbox, [["rank", "BART", 8], ["rank", "barta", 8], ["rank", "bar", 8]]
    )
    assert bart["ids"][0] == "bay-area-rapid-transit-bart"
    assert "berks-area-regional-transportation-authority-barta" in bart["ids"]
    assert barta["ids"][0] == "berks-area-regional-transportation-authority-barta"
    assert set(partial["ids"]) >= {
        "bay-area-rapid-transit-bart",
        "berks-area-regional-transportation-authority-barta",
    }


def test_words_match_in_any_order_and_by_prefix(sandbox: Path) -> None:
    results = run_js(sandbox, [["rank", "davis unitrans", 8], ["rank", "yolo trans", 8]])
    assert results[0]["ids"] == ["unitrans"]
    assert results[1]["ids"] == ["yolobus"]


def test_the_feed_id_matches_too(sandbox: Path) -> None:
    assert run_js(sandbox, [["rank", "abq-ride", 8]])[0]["ids"] == ["abq-ride"]


def test_rank_reports_the_total_beyond_the_limit(sandbox: Path) -> None:
    result = run_js(sandbox, [["rank", "transit", 2]])[0]
    assert len(result["ids"]) == 2
    assert result["total"] > 2


def test_nothing_matches_an_unknown_name(sandbox: Path) -> None:
    assert run_js(sandbox, [["rank", "zzzz", 8]])[0] == {"ids": [], "total": 0}


def test_clear_match_goes_straight_to_one_agency(sandbox: Path) -> None:
    assert run_js(
        sandbox,
        [
            ["clear", "Unitrans (ASUCD / City of Davis)"],
            ["clear", "unitrans"],
            ["clear", "BART"],
            ["clear", "bay area rapid transit"],
            ["clear", "abq-ride"],
            ["clear", "yolobus"],
            ["clear", "montreal"],
        ],
    ) == [
        "unitrans",
        "unitrans",
        "bay-area-rapid-transit-bart",
        "bay-area-rapid-transit-bart",
        "abq-ride",
        "yolobus",
        "societe-de-transport-de-montreal",
    ]


def test_ambiguous_queries_are_never_a_clear_match(sandbox: Path) -> None:
    assert run_js(
        sandbox,
        [
            # Two feeds share this exact name.
            ["clear", "Annapolis Transit"],
            # Matches many agencies.
            ["clear", "transit"],
            ["clear", "bar"],
            ["clear", ""],
            ["clear", "zzzz"],
        ],
    ) == [None, None, None, None, None]
