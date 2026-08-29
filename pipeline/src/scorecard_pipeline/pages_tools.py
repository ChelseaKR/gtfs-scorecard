"""The self-serve tool pages: /compare/, /query/, and /check/.

Extracted from render_site.py: these three pages share a shape (client-side
tools over published data, plain semantic HTML with the work announced via a
status region) and none of them reads artifacts at render time — compare gets
the catalog it lists, query and check are pure. See each docstring for the
page's accessibility and no-shaming rules.
"""

# ruff: noqa: E501  (long inline-HTML lines, matching render_site)
from __future__ import annotations

import json
from typing import Any

from .site_shell import BASE_URL, CATEGORY_LABELS, CATEGORY_ORDER, _breadcrumb, _page, esc

# Where the compare page reads the rest of its picker list from, and how many
# agencies its two <select>s carry in the document itself.
#
# Both pickers used to inline the whole catalog, so the document carried every
# agency twice and grew by about 190 bytes with each one added: at 2,100
# records that is a ~430 KB HTML document whose parse cost showed up directly
# in the page's largest contentful paint. The list is data, not chrome, so it
# is published once as JSON and fetched the first time someone reaches for a
# picker, which is the same shape /map/ uses for its complete list. The
# document now weighs the same at 2,000 agencies as at 20.
_COMPARE_PICKER_URL = "/compare/agencies.json"
_COMPARE_PICKER_INITIAL_OPTIONS = 50


def _compare_picker_order(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The catalog in the order both compare pickers list it: by name."""
    return sorted(catalog, key=lambda r: str(r["name"]).lower())


def _render_compare_picker_data(catalog: list[dict[str, Any]]) -> str:
    """The compare page's picker list, published as its own small JSON.

    One row per feed record, already in the order the pickers show it, holding
    only what an option needs: the id it submits, the name it reads, and the
    state that disambiguates the many agencies sharing a name. Positional rows
    keyed by ``fields`` rather than repeated object keys, because this file is
    fetched by a picker rather than read by a person; the public dataset with
    every column stays at /api/v1/agencies.json and /catalog.json."""
    rows = [
        [str(r["id"]), str(r["name"]), str(r.get("state") or "")]
        for r in _compare_picker_order(catalog)
    ]
    return (
        json.dumps(
            {"schema_version": 1, "fields": ["id", "name", "state"], "agencies": rows},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _render_compare_page(catalog: list[dict[str, Any]]) -> str:
    """The side-by-side compare page (/compare/?a=<id>&b=<id>).

    Two agencies' latest artifacts, loaded client-side and rendered as one
    accessible table only when rubric, scoring profile, validator, and measured
    category set match and the feed hashes are distinct. Otherwise the page explains why the grades are kept separate
    and links to both scorecards. The pickers are
    plain selects submitted as a GET form, so every comparison has a shareable
    URL; only the result table itself needs JS, and the noscript path says so.
    The pickers start with the first
    ``_COMPARE_PICKER_INITIAL_OPTIONS`` agencies and take the rest from
    _render_compare_picker_data on first contact with the form or on request,
    announced in a status region and recoverable with a retry button, so the
    document stops growing with the registry. An unmeasured
    realtime category renders as "Not yet published", never as a zero
    (docs/SIDE_BY_SIDE_COMPARE_DESIGN.md)."""
    ordered = _compare_picker_order(catalog)
    total = len(ordered)
    initial = ordered[:_COMPARE_PICKER_INITIAL_OPTIONS]
    shown = len(initial)
    needs_load = total > shown
    options = "".join(
        f'<option value="{esc(r["id"])}">{esc(r["name"])}'
        + (f" &mdash; {esc(r['state'])}" if r.get("state") else "")
        + "</option>"
        for r in initial
    )
    picker_status = (
        f"Both lists start with {shown} of {total} agencies. The rest arrive when you "
        "reach for a picker, or load them now."
        if needs_load
        else f"Both lists hold all {total} agencies."
    )
    load_button_hidden = "" if needs_load else " hidden"
    loaded_initial = str(not needs_load).lower()
    noscript = (
        f"""Building the comparison table needs JavaScript, and so does the rest of the
    agency list: without it the pickers hold the first {shown} of {total} agencies. Every
    scorecard is listed in the <a href="/agencies/">agency directory</a>, and each
    scorecard has a Compare link that fills in the first agency for you."""
        if needs_load
        else """Building the comparison table needs JavaScript. The pickers above still
    work: choose two agencies to get a shareable link, or open each scorecard from the
    <a href="/agencies/">agency directory</a>."""
    )
    labels = json.dumps(
        [[key, CATEGORY_LABELS[key]] for key in CATEGORY_ORDER], separators=(",", ":")
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Compare agencies", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Compare two agencies.</h1>
    <p class="page-lede">Choose two scorecards to check whether they use the same rubric,
    scoring profile, validator, and measured category set, and come from distinct feed bytes.
    Like-for-like results can appear in one table; otherwise the page keeps the grades
    separate and links to both full scorecards.</p>
    <form id="compare-form" class="map-filters" action="/compare/" method="get" aria-label="Choose two agencies to compare">
      <div class="map-filter-row">
        <label for="compare-a-filter">First agency</label>
        <input id="compare-a-filter" class="agency-search compare-filter" type="search"
          autocomplete="off" aria-controls="compare-a" aria-describedby="compare-picker-status"
          placeholder="Type a name to filter">
        <label class="visually-hidden" for="compare-a">Choose the first agency from the matches</label>
        <select id="compare-a" name="a" aria-describedby="compare-picker-status" required>
          <option value="">Choose an agency</option>{options}
        </select>
      </div>
      <div class="map-filter-row">
        <label for="compare-b-filter">Second agency</label>
        <input id="compare-b-filter" class="agency-search compare-filter" type="search"
          autocomplete="off" aria-controls="compare-b" aria-describedby="compare-picker-status"
          placeholder="Type a name to filter">
        <label class="visually-hidden" for="compare-b">Choose the second agency from the matches</label>
        <select id="compare-b" name="b" aria-describedby="compare-picker-status" required>
          <option value="">Choose an agency</option>{options}
        </select>
      </div>
      <div class="map-filter-row">
        <button type="submit" class="copy-btn">Compare</button>
      </div>
    </form>
    <div class="map-load-panel">
      <button type="button" class="button button-secondary" id="compare-load"{load_button_hidden}>
        Load every agency
      </button>
      <p id="compare-picker-status" class="fineprint" role="status">{esc(picker_status)}
        <a href="/agencies/">Browse the paginated agency directory.</a></p>
    </div>
    <p id="compare-status" role="status"></p>
    <div id="compare-result"></div>
    <noscript><p>{noscript}</p></noscript>
    <p class="fineprint">Category scores measure published data quality, not service
    quality, and a missing realtime feed is shown as not yet published, never as a
    failure. <a href="/how-to-read/">How to read a scorecard.</a></p>
    <script>
      (function () {{
        var CATS = {labels};
        var PICKER_URL = "{_COMPARE_PICKER_URL}";
        var SHOWN = {shown};
        var selA = document.getElementById("compare-a");
        var selB = document.getElementById("compare-b");
        var formEl = document.getElementById("compare-form");
        var loadEl = document.getElementById("compare-load");
        var pickerStatusEl = document.getElementById("compare-picker-status");
        var statusEl = document.getElementById("compare-status");
        var result = document.getElementById("compare-result");
        var pickers = [];
        // Fill one picker from its current choices and its filter box, keeping
        // the chosen agency selected when it survives the filter.
        function refresh(picker) {{
          var query = picker.input.value.trim().toLocaleLowerCase();
          var selected = picker.select.value;
          var matches = query
            ? picker.choices.filter(function (choice) {{
                return (choice.text + " " + choice.value).toLocaleLowerCase().includes(query);
              }}).slice(0, 100)
            : picker.choices;
          var batch = document.createDocumentFragment();
          batch.appendChild(new Option(
            query && !matches.length ? "No matching agencies" : "Choose an agency", ""
          ));
          matches.forEach(function (choice) {{
            batch.appendChild(new Option(choice.text, choice.value));
          }});
          picker.select.textContent = "";
          picker.select.appendChild(batch);
          if (matches.some(function (choice) {{ return choice.value === selected; }}))
            picker.select.value = selected;
        }}
        function installFilter(inputId, select) {{
          var picker = {{
            input: document.getElementById(inputId),
            select: select,
            choices: Array.from(select.options).slice(1).map(function (option) {{
              return {{ value: option.value, text: option.textContent || option.value }};
            }})
          }};
          picker.input.addEventListener("input", function () {{ refresh(picker); }});
          pickers.push(picker);
        }}
        installFilter("compare-a-filter", selA);
        installFilter("compare-b-filter", selB);

        // The rest of the agency list is one published JSON, fetched the first
        // time someone reaches for a picker (or asks for it outright) rather
        // than shipped inside this document. Both states are announced, and a
        // failed fetch leaves the opening options and a retry in place.
        var listLoaded = {loaded_initial};
        var listLoading = false;
        var listPromise = null;
        function hydratePickers(requested) {{
          if (listLoaded || listLoading) return;
          listLoading = true;
          if (loadEl) {{
            loadEl.setAttribute("aria-disabled", "true");
            loadEl.textContent = "Loading every agency\\u2026";
          }}
          pickerStatusEl.textContent = "Loading the complete agency list.";
          if (!listPromise) {{
            listPromise = fetch(PICKER_URL).then(function (r) {{
              if (!r.ok) throw new Error("agency list");
              return r.json();
            }});
          }}
          listPromise.then(function (data) {{
            var rows = (data && data.agencies) || [];
            var choices = rows.map(function (row) {{
              return {{
                value: row[0],
                text: row[1] + (row[2] ? " \\u2014 " + row[2] : "")
              }};
            }});
            pickers.forEach(function (picker) {{
              picker.choices = choices;
              refresh(picker);
            }});
            listLoaded = true;
            listLoading = false;
            // The load control has done its job and goes away. Focus follows it
            // to the first picker whenever it was the thing being used, whether
            // that is the click that asked or a keyboard already resting on it
            // while a load started from the form. Focus is never moved out from
            // under someone working elsewhere on the page.
            var held = loadEl && (requested || document.activeElement === loadEl);
            if (loadEl) loadEl.hidden = true;
            pickerStatusEl.textContent =
              "Both lists now hold all " + rows.length + " agencies.";
            if (held && pickers.length) pickers[0].input.focus();
          }}).catch(function () {{
            listLoading = false;
            listPromise = null;
            if (loadEl) {{
              loadEl.hidden = false;
              loadEl.removeAttribute("aria-disabled");
              loadEl.textContent = "Try loading every agency again";
            }}
            pickerStatusEl.textContent = "The complete agency list could not load. Both " +
              "pickers still hold the first " + SHOWN + " agencies, and the agency " +
              "directory links every scorecard.";
          }});
        }}
        if (loadEl) loadEl.addEventListener("click", function () {{
          if (loadEl.getAttribute("aria-disabled") !== "true") hydratePickers(true);
        }});
        ["focusin", "pointerenter"].forEach(function (name) {{
          formEl.addEventListener(name, function () {{ hydratePickers(false); }});
        }});

        // Show the agency a shared link asked for even before the full list is
        // in, so the pickers always read back what the page is comparing.
        function showChoice(select, id, name) {{
          var known = Array.prototype.some.call(select.options, function (option) {{
            return option.value === id;
          }});
          if (!known) select.add(new Option(name, id), select.options[1] || null);
          select.value = id;
        }}
        var params = new URLSearchParams(window.location.search);
        var a = params.get("a"), b = params.get("b");
        if (!a || !b) return;
        if (a === b) {{
          statusEl.textContent = "Pick two different agencies to compare.";
          return;
        }}
        statusEl.textContent = "Loading both scorecards\\u2026";
        function fetchArtifact(id) {{
          return fetch("/data/artifacts/" + encodeURIComponent(id) + "/latest.json")
            .then(function (r) {{
              if (!r.ok) throw new Error(id);
              return r.json();
            }});
        }}
        function el(tag, text) {{
          var e = document.createElement(tag);
          if (text !== undefined) e.textContent = text;
          return e;
        }}
        // A score cell; when this side is measured, higher, and the gap is real,
        // the number is emphasised with a text note, never colour alone.
        function scoreCell(mine, theirs) {{
          var td = el("td");
          if (mine === null) {{ td.textContent = "Not yet published"; return td; }}
          if (theirs !== null && mine > theirs) {{
            var strong = el("strong", String(mine));
            td.appendChild(strong);
            var sr = el("span", " (higher)");
            sr.className = "visually-hidden";
            td.appendChild(sr);
          }} else {{
            td.textContent = String(mine);
          }}
          td.appendChild(el("span")).textContent = " / 100";
          return td;
        }}
        function catScore(art, key) {{
          var cat = (art.categories || {{}})[key] || {{}};
          return cat.status === "measured" ? cat.score : null;
        }}
        function flag(v) {{ return v ? "Yes" : "Not yet"; }}
        function detail(art) {{
          var comp = ((art.categories || {{}}).completeness || {{}}).details || {{}};
          var fresh = ((art.categories || {{}}).freshness || {{}}).details || {{}};
          return {{
            days: typeof fresh.days_until_expiry === "number" ? fresh.days_until_expiry : null,
            fares: !!comp.has_fares,
            flex: !!(comp.flex && comp.flex.has_flex),
            pathways: !!(comp.pathways && comp.pathways.has_pathways)
          }};
        }}
        function readerArchiveProfile(art) {{
          var fetchBlock = art.fetch && typeof art.fetch === "object" ? art.fetch : {{}};
          var direct = Object.prototype.hasOwnProperty.call(art, "reader_archive_profile");
          var embedded = Object.prototype.hasOwnProperty.call(
            fetchBlock, "reader_archive_profile");
          var owner = direct ? art : fetchBlock;
          var profile = Object.prototype.hasOwnProperty.call(owner, "reader_archive_profile")
            ? owner.reader_archive_profile : null;
          function valid(value) {{
            return value === "raw-v1" || value === "flat-single-root-v1";
          }}
          if ((direct && !valid(art.reader_archive_profile)) ||
              (embedded && !valid(fetchBlock.reader_archive_profile))) return "";
          if (direct && embedded &&
              art.reader_archive_profile !== fetchBlock.reader_archive_profile) return "";
          var normalizedPresent = Object.prototype.hasOwnProperty.call(
            fetchBlock, "reader_archive_normalized");
          var normalized = fetchBlock.reader_archive_normalized;
          if (normalizedPresent && typeof normalized !== "boolean") return "";
          var implied = normalized === true ? "flat-single-root-v1" : "raw-v1";
          if (direct || embedded) {{
            return normalizedPresent && profile !== implied ? "" : profile;
          }}
          return implied;
        }}
        function comparisonContract(art) {{
          var profile = art.scoring_profile || {{}};
          return {{
            rubric: String(art.rubric_version || ""),
            profile: String(profile.id || ""),
            profileRubric: String(profile.rubric_version || ""),
            validator: String(art.validator_version || ""),
            readerArchive: readerArchiveProfile(art),
            feedHash: String(((art.feed || {{}}).sha256) || ""),
            measured: CATS.filter(function (c) {{
              return ((art.categories || {{}})[c[0]] || {{}}).status === "measured";
            }}).map(function (c) {{ return c[0]; }})
          }};
        }}
        Promise.all([fetchArtifact(a), fetchArtifact(b)]).then(function (arts) {{
          var artA = arts[0], artB = arts[1];
          var nameA = artA.agency.name, nameB = artB.agency.name;
          showChoice(selA, a, nameA);
          showChoice(selB, b, nameB);
          var contractA = comparisonContract(artA), contractB = comparisonContract(artB);
          var likeForLike = contractA.rubric && contractA.profile && contractA.validator &&
            contractA.readerArchive && contractB.readerArchive &&
            contractA.feedHash && contractB.feedHash &&
            contractA.feedHash !== contractB.feedHash &&
            contractA.profileRubric === contractA.rubric &&
            contractB.profileRubric === contractB.rubric &&
            contractA.rubric === contractB.rubric &&
            contractA.profile === contractB.profile &&
            contractA.validator === contractB.validator &&
            contractA.readerArchive === contractB.readerArchive &&
            JSON.stringify(contractA.measured) === JSON.stringify(contractB.measured);
          if (!likeForLike) {{
            result.textContent = "";
            var warning = el("div");
            warning.className = "error-box";
            warning.setAttribute("role", "status");
            warning.appendChild(el("h2", "These scorecards are not like-for-like."));
            warning.appendChild(el("p", nameA + " and " + nameB +
              " do not have distinct feed bytes under the same verified scoring profile, " +
              "rubric, validator, reader archive profile, and measured category set. " +
              "Their grades stay separate so " +
              "a duplicate record, methodology, or realtime-coverage difference is not " +
              "presented as a feed-quality difference."));
            var links = el("p");
            [[nameA, a], [nameB, b]].forEach(function (pair, index) {{
              if (index) links.appendChild(document.createTextNode(" \u00b7 "));
              var link = el("a", "Open " + pair[0]);
              link.href = "/agency/" + encodeURIComponent(pair[1]) + "/";
              links.appendChild(link);
            }});
            warning.appendChild(links);
            result.appendChild(warning);
            statusEl.textContent = "Scorecards kept separate: " + nameA + " and " + nameB +
              " are not like-for-like.";
            return;
          }}
          var table = el("table");
          table.className = "leaderboard compare-static-table";
          var caption = el("caption", "Side-by-side scorecard comparison of " +
            nameA + " and " + nameB + ".");
          caption.className = "visually-hidden";
          table.appendChild(caption);
          var thead = el("thead"), hr = el("tr");
          hr.appendChild(el("th", "Measure")).setAttribute("scope", "col");
          [[nameA, a], [nameB, b]].forEach(function (pair) {{
            var th = el("th");
            th.setAttribute("scope", "col");
            var link = el("a", pair[0]);
            link.href = "/agency/" + encodeURIComponent(pair[1]) + "/";
            th.appendChild(link);
            hr.appendChild(th);
          }});
          thead.appendChild(hr);
          table.appendChild(thead);
          var tbody = el("tbody");
          function row(label, cellA, cellB) {{
            var tr = el("tr");
            tr.appendChild(el("th", label)).setAttribute("scope", "row");
            tr.appendChild(cellA);
            tr.appendChild(cellB);
            tbody.appendChild(tr);
          }}
          row("Overall grade",
              el("td", artA.overall.grade + " (" + artA.overall.score + " / 100)"),
              el("td", artB.overall.grade + " (" + artB.overall.score + " / 100)"));
          CATS.forEach(function (c) {{
            var sa = catScore(artA, c[0]), sb = catScore(artB, c[0]);
            row(c[1], scoreCell(sa, sb), scoreCell(sb, sa));
          }});
          var dA = detail(artA), dB = detail(artB);
          function daysText(d) {{
            if (d === null) return "\\u2014";
            return d < 0 ? "Expired" : d + " days";
          }}
          row("Days of service left", el("td", daysText(dA.days)), el("td", daysText(dB.days)));
          row("Fare data published", el("td", flag(dA.fares)), el("td", flag(dB.fares)));
          row("GTFS-Flex (demand-responsive)", el("td", flag(dA.flex)), el("td", flag(dB.flex)));
          row("Pathways (station wayfinding)", el("td", flag(dA.pathways)), el("td", flag(dB.pathways)));
          table.appendChild(tbody);
          result.textContent = "";
          var scrollHint = el("p", "Swipe the table sideways to see both agencies.");
          scrollHint.className = "table-scroll-hint";
          result.appendChild(scrollHint);
          var tableWrap = el("div");
          tableWrap.className = "table-wrap";
          tableWrap.appendChild(table);
          result.appendChild(tableWrap);
          statusEl.textContent = "Comparing " + nameA + " and " + nameB + ".";
        }}).catch(function (err) {{
          statusEl.textContent = "We couldn't load a scorecard for \\"" + err.message +
            "\\". It may not be tracked yet; pick from the lists above.";
        }});
      }})();
    </script>"""  # noqa: S608 - static HTML template text ("Compare agencies" page), never executed as SQL
    return _page(
        title="Compare two agencies side by side — GTFS Scorecard",
        description=(
            "Check whether two transit agencies' GTFS scorecards are like-for-like "
            "before showing their grades and category scores side by side."
        ),
        canonical=f"{BASE_URL}/compare/",
        body=body,
    )


_DUCKDB_WASM_VERSION = "1.29.0"

_QUERY_EXAMPLES = [
    (
        "Expiry support worklist",
        "SELECT id, name, date, days_until_expiry\nFROM agencies\n"
        "WHERE days_until_expiry BETWEEN -365 AND 60\n"
        "ORDER BY days_until_expiry, name\nLIMIT 50",
    ),
    (
        "Rows outside the comparison cohort",
        "SELECT id, name, date, rubric_version, scoring_profile_id, validator_version,\n"
        "       reader_archive_profile\n"
        "FROM agencies\nWHERE comparison_eligible = false\nORDER BY name\nLIMIT 50",
    ),
    (
        "Producer provenance",
        "SELECT rubric_version, scoring_profile_id, validator_version,\n"
        "       reader_archive_profile,\n"
        "       count(*) AS feed_records\nFROM agencies\n"
        "GROUP BY rubric_version, scoring_profile_id, validator_version,\n"
        "         reader_archive_profile\n"
        "ORDER BY rubric_version, scoring_profile_id, validator_version,\n"
        "         reader_archive_profile",
    ),
]


def _render_query_page() -> str:
    """The in-browser SQL page (/query/): DuckDB-WASM over the published
    parquet, so an analyst or journalist can run SQL against the covered
    dataset with no backend added and nothing installed
    (docs/expansion-ideation-2026-07.md, section C).

    The engine and the data load only on the first Run, keeping page load
    light; queries run entirely in the visitor's browser against the same
    agencies.parquet any consumer can download. The textarea, buttons, and
    result table are plain semantic HTML; run state is announced via a status
    region."""
    example_buttons = "".join(
        f'<button type="button" class="copy-btn query-example" data-sql="{esc(sql)}">'
        f"{esc(label)}</button>"
        for label, sql in _QUERY_EXAMPLES
    )
    default_sql = _QUERY_EXAMPLES[0][1]
    body = f"""    {_breadcrumb([("Home", "/"), ("Query the dataset", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Query the dataset.</h1>
    <p class="page-lede">Run SQL against the covered scorecard dataset, right here in your
    browser. One table, <code>agencies</code>, holds every published feed record's latest snapshot:
    <code>id</code>, <code>name</code>, <code>date</code>, <code>grade</code>,
    <code>score</code>, <code>days_until_expiry</code>, producer-version fields,
    <code>comparison_eligible</code>, and the
    <code>correctness</code>, <code>freshness</code>, <code>completeness</code>, and
    <code>realtime</code> category scores. Nothing is sent to a server: the engine
    (DuckDB) and the data load into the page and the query runs on your machine.</p>
    <p class="page-lede">Prefer a file? The same data is
    <a href="/api/v1/agencies.parquet">agencies.parquet</a>,
    <a href="/catalog.csv">catalog.csv</a>, and the JSON described in the
    <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/api.md">data
    dictionary</a>.</p>
    <p><strong>Comparison warning:</strong> the table includes old-methodology,
    duplicate-identity, and otherwise non-comparable rows so the public record stays complete.
    Do not compare or average scores unless you filter
    <code>comparison_eligible = true</code> and inspect the current contract in
    <a href="/api/v1/agencies.json">agencies.json</a>. The examples below are support
    worklists and provenance checks, not rankings.</p>
    <form aria-label="SQL query" class="query-form">
      <label for="query-sql">SQL to run against the <code>agencies</code> table</label>
      <textarea id="query-sql" class="outreach-text" rows="6"
        spellcheck="false">{esc(default_sql)}</textarea>
      <div class="map-filter-row">
        <button type="submit" class="copy-btn" id="query-run">Run</button>
        {example_buttons}
      </div>
    </form>
    <p id="query-status" role="status">The query engine (about 6&nbsp;MB) downloads the
    first time you press Run.</p>
    <div id="query-result"></div>
    <noscript><p>Running SQL in the page needs JavaScript. The downloads above carry the
    same data.</p></noscript>
    <p class="fineprint">Remember the sampling frame: this is the covered set of feeds,
    not the universe of agencies, and absence means not covered, never failing.
    Data CC BY 4.0.</p>
    <script>
      (function () {{
        var form = document.querySelector(".query-form");
        var sqlEl = document.getElementById("query-sql");
        var statusEl = document.getElementById("query-status");
        var result = document.getElementById("query-result");
        var conn = null;
        document.querySelectorAll(".query-example").forEach(function (btn) {{
          btn.addEventListener("click", function () {{
            sqlEl.value = btn.getAttribute("data-sql");
            sqlEl.focus();
          }});
        }});
        function el(tag, text) {{
          var e = document.createElement(tag);
          if (text !== undefined) e.textContent = text;
          return e;
        }}
        async function ensureEngine() {{
          if (conn) return conn;
          statusEl.textContent = "Loading the query engine\\u2026";
          var duckdb = await import(
            "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@{_DUCKDB_WASM_VERSION}/+esm");
          var bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
          var workerUrl = URL.createObjectURL(new Blob(
            ['importScripts("' + bundle.mainWorker + '");'],
            {{ type: "text/javascript" }}));
          var db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
          await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
          URL.revokeObjectURL(workerUrl);
          statusEl.textContent = "Loading the dataset\\u2026";
          var buf = new Uint8Array(
            await (await fetch("/api/v1/agencies.parquet")).arrayBuffer());
          await db.registerFileBuffer("agencies.parquet", buf);
          conn = await db.connect();
          await conn.query(
            "CREATE VIEW agencies AS SELECT * FROM read_parquet('agencies.parquet')");
          return conn;
        }}
        async function run(sql) {{
          var c = await ensureEngine();
          statusEl.textContent = "Running\\u2026";
          var res = await c.query(sql);
          var cols = res.schema.fields.map(function (f) {{ return f.name; }});
          var rows = res.toArray();
          var table = el("table");
          table.className = "leaderboard";
          table.appendChild(el("caption", "Query result: " + rows.length + " row" +
            (rows.length === 1 ? "" : "s") + "."));
          var thead = el("thead"), hr = el("tr");
          cols.forEach(function (cname) {{
            hr.appendChild(el("th", cname)).setAttribute("scope", "col");
          }});
          thead.appendChild(hr);
          table.appendChild(thead);
          var tbody = el("tbody");
          rows.slice(0, 500).forEach(function (row) {{
            var tr = el("tr");
            cols.forEach(function (cname) {{
              var v = row[cname];
              tr.appendChild(el("td", v === null || v === undefined ? "" : String(v)));
            }});
            tbody.appendChild(tr);
          }});
          table.appendChild(tbody);
          result.textContent = "";
          result.appendChild(table);
          statusEl.textContent = rows.length > 500
            ? rows.length + " rows; showing the first 500."
            : rows.length + " row" + (rows.length === 1 ? "" : "s") + ".";
        }}
        form.addEventListener("submit", function (ev) {{
          ev.preventDefault();
          run(sqlEl.value).catch(function (err) {{
            statusEl.textContent = "That query did not run: " + err.message;
          }});
        }});
      }})();
    </script>"""  # noqa: S608 - static HTML template text (the client-side SQL query page), never executed server-side as SQL
    return _page(
        title="Query the dataset in your browser — GTFS Scorecard",
        description=(
            "Run SQL against the covered GTFS quality dataset in your browser with "
            "DuckDB: grades, category scores, and freshness for every tracked feed record."
        ),
        canonical=f"{BASE_URL}/query/",
        body=body,
    )


_FFLATE_VERSION = "0.8.2"

# The check page's logic, kept out of the f-string so braces stay readable.
# The five questions mirror the rubric's plain-language framing; every status
# is carried in text ("Looks good" / "Needs attention" / "Can't tell yet"),
# never colour. See _render_check_page for the page around it.
_CHECK_PAGE_SCRIPT = r"""    <script>
      (function () {
        var input = document.getElementById("check-file");
        var zone = document.getElementById("check-drop");
        var statusEl = document.getElementById("check-status");
        var result = document.getElementById("check-result");

        function el(tag, text) {
          var e = document.createElement(tag);
          if (text !== undefined) e.textContent = text;
          return e;
        }

        // A small CSV reader: quoted fields, embedded commas/newlines, CRLF,
        // BOM. Returns row objects keyed by the header line.
        function parseCsv(text, maxRows) {
          if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
          var rows = [], field = "", row = [], inQ = false, i = 0, n = text.length;
          while (i < n) {
            var ch = text[i];
            if (inQ) {
              if (ch === '"') {
                if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
                inQ = false; i++; continue;
              }
              field += ch; i++; continue;
            }
            if (ch === '"') { inQ = true; i++; continue; }
            if (ch === ",") { row.push(field); field = ""; i++; continue; }
            if (ch === "\n" || ch === "\r") {
              if (ch === "\r" && text[i + 1] === "\n") i++;
              row.push(field); field = "";
              if (row.length > 1 || row[0] !== "") rows.push(row);
              row = []; i++;
              if (maxRows && rows.length > maxRows) break;
              continue;
            }
            field += ch; i++;
          }
          if (field !== "" || row.length) { row.push(field); rows.push(row); }
          if (!rows.length) return [];
          var header = rows[0].map(function (h) { return h.trim(); });
          return rows.slice(1).map(function (r) {
            var o = {};
            header.forEach(function (h, j) { o[h] = (r[j] || "").trim(); });
            return o;
          });
        }

        function ymd(s) {
          if (!/^\d{8}$/.test(s)) return null;
          return new Date(Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)));
        }

        function daysFromToday(d) {
          var today = new Date();
          var t = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
          return Math.round((d.getTime() - t) / 86400000);
        }

        // The five pre-publish questions, each {q, status, note}; status is
        // "good", "attention", or "unknown" and is always rendered as text.
        function assess(files) {
          var out = [];
          var names = Object.keys(files);
          function has(f) { return names.indexOf(f) >= 0; }
          function read(f, maxRows) {
            return has(f)
              ? parseCsv(new TextDecoder("utf-8").decode(files[f]), maxRows)
              : [];
          }

          var required = ["agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"];
          var missing = required.filter(function (f) { return !has(f); });
          var hasCal = has("calendar.txt") || has("calendar_dates.txt");
          if (!missing.length && hasCal) {
            out.push({ q: "Does it have the required files?", status: "good",
              note: "All required files are present, including a service calendar." });
          } else {
            var what = missing.slice();
            if (!hasCal) what.push("calendar.txt or calendar_dates.txt");
            out.push({ q: "Does it have the required files?", status: "attention",
              note: "Missing: " + what.join(", ") +
                ". Trip planners cannot load the feed without these." });
          }

          var end = null, source = "";
          read("feed_info.txt", 5).forEach(function (r) {
            var d = ymd(r.feed_end_date || "");
            if (d && (!end || d > end)) { end = d; source = "feed_info.txt"; }
          });
          if (!end) {
            read("calendar.txt", 5000).forEach(function (r) {
              var d = ymd(r.end_date || "");
              if (d && (!end || d > end)) { end = d; source = "calendar.txt"; }
            });
          }
          if (!end) {
            read("calendar_dates.txt", 200000).forEach(function (r) {
              var d = ymd(r.date || "");
              if (d && (!end || d > end)) { end = d; source = "calendar_dates.txt"; }
            });
          }
          if (!end) {
            out.push({ q: "When does the service data run out?", status: "unknown",
              note: "No end date could be read. Add feed_info.txt with a feed_end_date " +
                "so consumers can tell." });
          } else {
            var days = daysFromToday(end);
            if (days < 0) {
              out.push({ q: "When does the service data run out?", status: "attention",
                note: "The " + source + " end date passed " + (-days) + " days ago. Trip " +
                  "planners treat this feed as expired; re-export with current dates " +
                  "before publishing." });
            } else if (days < 30) {
              out.push({ q: "When does the service data run out?", status: "attention",
                note: "Only " + days + " days of service left (" + source + "). Extend the " +
                  "calendar before publishing; consumers want weeks of future coverage." });
            } else {
              out.push({ q: "When does the service data run out?", status: "good",
                note: days + " days of service ahead (" + source + ")." });
            }
          }

          var stops = read("stops.txt", 200000);
          if (!stops.length) {
            out.push({ q: "Do stops state wheelchair accessibility?", status: "unknown",
              note: "stops.txt could not be read." });
          } else {
            var stated = stops.filter(function (r) {
              return r.wheelchair_boarding === "1" || r.wheelchair_boarding === "2";
            }).length;
            var pct = Math.round(stated / stops.length * 100);
            out.push({
              q: "Do stops state wheelchair accessibility?",
              status: stated ? "good" : "attention",
              note: stated
                ? pct + "% of " + stops.length + " stops state wheelchair_boarding. This " +
                  "states what is published, not whether a stop is physically usable."
                : "No stop states wheelchair_boarding. Riders using wheelchairs cannot " +
                  "tell from apps which stops work for them; this data usually lives in " +
                  "your scheduling software already."
            });
          }

          if (has("fare_products.txt") || has("fare_leg_rules.txt")) {
            out.push({ q: "Is fare data included?", status: "good",
              note: "Fares v2 files are present." });
          } else if (has("fare_attributes.txt")) {
            out.push({ q: "Is fare data included?", status: "good",
              note: "Fares v1 files are present." });
          } else {
            out.push({ q: "Is fare data included?", status: "attention",
              note: "No fare files. Riders cannot see what a trip costs; if the service " +
                "is fare-free, saying so in fare data is still worth it." });
          }

          if (stops.length) {
            var named = stops.filter(function (r) { return (r.stop_name || "").length > 0; });
            var mixed = named.filter(function (r) { return /[a-z]/.test(r.stop_name); });
            if (named.length < stops.length) {
              out.push({ q: "Are stop names readable?", status: "attention",
                note: (stops.length - named.length) + " stops have no name at all." });
            } else if (mixed.length < named.length / 2) {
              out.push({ q: "Are stop names readable?", status: "attention",
                note: "Most stop names are ALL CAPS. Mixed case reads better in apps and " +
                  "for screen readers; usually one export setting." });
            } else {
              out.push({ q: "Are stop names readable?", status: "good",
                note: "Stops are named in readable mixed case." });
            }
          } else {
            out.push({ q: "Are stop names readable?", status: "unknown",
              note: "stops.txt could not be read." });
          }
          return out;
        }

        var LABELS = { good: "Looks good", attention: "Needs attention", unknown: "Can't tell yet" };

        function render(checks, fileName) {
          var table = el("table");
          table.className = "leaderboard";
          table.appendChild(el("caption", "Pre-publish check of " + fileName + "."));
          var thead = el("thead"), hr = el("tr");
          ["Question", "Status", "What we saw"].forEach(function (h) {
            hr.appendChild(el("th", h)).setAttribute("scope", "col");
          });
          thead.appendChild(hr);
          table.appendChild(thead);
          var tbody = el("tbody");
          checks.forEach(function (c) {
            var tr = el("tr");
            tr.appendChild(el("th", c.q)).setAttribute("scope", "row");
            tr.appendChild(el("td", LABELS[c.status] || c.status));
            tr.appendChild(el("td", c.note));
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          result.textContent = "";
          result.appendChild(table);
          var next = el("p");
          next.appendChild(document.createTextNode(
            "This previews five things, not everything. "));
          var a = el("a", "Get the full scorecard");
          a.href = "/try.html";
          next.appendChild(a);
          next.appendChild(document.createTextNode(
            " to run the canonical MobilityData validator over the whole feed."));
          result.appendChild(next);
          var attention = checks.filter(function (c) { return c.status === "attention"; }).length;
          statusEl.textContent = attention
            ? "Checked " + fileName + ": " + attention + " of " + checks.length +
              " questions need attention."
            : "Checked " + fileName + ": all " + checks.length + " questions look good.";
        }

        async function handle(file) {
          if (!file) return;
          if (file.size > 300 * 1024 * 1024) {
            statusEl.textContent =
              "That file is over 300 MB; this preview is built for small-agency feeds.";
            return;
          }
          statusEl.textContent = "Reading " + file.name + " in your browser…";
          try {
            if (!window.fflate) {
              await new Promise(function (resolve, reject) {
                var s = document.createElement("script");
                s.src = "https://cdn.jsdelivr.net/npm/fflate@__FFLATE__/umd/index.js";
                s.onload = resolve;
                s.onerror = function () {
                  reject(new Error("could not load the unzip library"));
                };
                document.head.appendChild(s);
              });
            }
            var buf = new Uint8Array(await file.arrayBuffer());
            var files = window.fflate.unzipSync(buf);
            // Feeds are sometimes zipped inside a folder; flatten one level.
            var flat = {};
            Object.keys(files).forEach(function (k) {
              var base = k.split("/").pop();
              if (base && base.slice(-4) === ".txt" && !(base in flat)) flat[base] = files[k];
            });
            render(assess(flat), file.name);
          } catch (err) {
            statusEl.textContent = "That zip could not be read: " + err.message +
              ". Is it the GTFS zip your scheduling software exported?";
          }
        }

        input.addEventListener("change", function () { handle(input.files[0]); });
        if (zone) {
          ["dragover", "dragenter"].forEach(function (evName) {
            zone.addEventListener(evName, function (ev) { ev.preventDefault(); });
          });
          zone.addEventListener("drop", function (ev) {
            ev.preventDefault();
            var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
            handle(f);
          });
        }
      })();
    </script>"""


def _render_check_page() -> str:
    """The pre-publish check (/check/): drag a GTFS zip in, get the five
    questions that matter answered before publishing, entirely in the browser
    (docs/expansion-ideation-2026-07.md, section A).

    The person exporting a feed from scheduling software does not run CI; this
    meets them at the moment of export. The zip never leaves the page (fflate
    unzips it client-side, loaded only when a file arrives), the five answers
    are framed as fixes with a text status never colour, and the page is loud
    that the canonical validator remains the authority: it links try.html for
    the full scorecard. The file input is the accessible primary; the drop
    zone is an enhancement."""
    body = f"""    {_breadcrumb([("Home", "/"), ("Check a feed before you publish", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Check a feed before you publish.</h1>
    <p class="page-lede">About to publish a GTFS export? Drop the zip here first and get
    the five questions that matter answered in seconds: required files, expiry,
    wheelchair fields, fares, and stop names. Your feed never leaves this page; it is
    read entirely in your browser and nothing is uploaded anywhere.</p>
    <div id="check-drop" class="feed-details">
      <label for="check-file"><strong>Choose your GTFS zip</strong> (or drag it onto this
        box)</label>
      <p><input type="file" id="check-file" accept=".zip,application/zip"></p>
    </div>
    <p id="check-status" role="status"></p>
    <div id="check-result"></div>
    <noscript><p>Reading a zip in the page needs JavaScript. You can run the full check
    instead: <a href="/try.html">request a full score</a>.</p></noscript>
    <p class="fineprint">A preview, not the full validation. The canonical
    <a href="https://github.com/MobilityData/gtfs-validator">MobilityData validator</a>
    stays the authority; <a href="/try.html">request a full score</a> to run it over the whole
    feed, and <a href="/subscribe.html">subscribe</a> to hear before a published feed
    expires.</p>
{_CHECK_PAGE_SCRIPT.replace("__FFLATE__", _FFLATE_VERSION)}"""
    return _page(
        title="Check a GTFS feed before you publish — GTFS Scorecard",
        description=(
            "Drop a GTFS zip in and answer the five pre-publish questions: required "
            "files, expiry, wheelchair fields, fares, and stop names. Nothing is uploaded."
        ),
        canonical=f"{BASE_URL}/check/",
        body=body,
    )


# Every self-serve tool, one entry each: (href, name, one-sentence what-for).
_TOOLS = [
    (
        "/app/",
        "Interactive app",
        "Browse every scorecard with live search, filters, and the state grid.",
    ),
    (
        "/compare/",
        "Compare two agencies",
        "Check whether two scorecards are like-for-like before showing them side by side.",
    ),
    (
        "/check/",
        "Check a feed before you publish",
        "Drop your GTFS zip in and get the five pre-publish questions answered; the file never leaves your browser.",
    ),
    (
        "/try.html",
        "Request a one-off score",
        "Submit a published feed URL through the GitHub-backed request path, or run the scorer locally; hosted instant scoring is not enabled.",
    ),
    ("/query/", "Query the dataset", "Run SQL over the covered dataset, right in the page."),
    (
        "/subscribe.html",
        "Feed-health alerts",
        "Get an email before a feed expires or when its grade changes.",
    ),
    ("/submit.html", "Add your agency", "Track a new feed on this site in about ten minutes."),
    (
        "/agency/unitrans/brief/",
        "Call-prep briefs",
        "Every agency has a printable one-page brief for a check-in call (this links an example; find yours from its scorecard).",
    ),
    (
        "/agency/unitrans/board/",
        "Board-ready one-pagers",
        "Open a printable board summary for each agency (this links the Unitrans example).",
    ),
    (
        "/procurement/",
        "For agencies: procurement",
        "Contract and acceptance-test language for holding a GTFS vendor to the same bar.",
    ),
    (
        "/data/",
        "Open data",
        "Download the covered dataset, CC BY 4.0, with a versioned public API.",
    ),
]


def _render_tools_page() -> str:
    """The tools index (/tools/): every self-serve tool on one page, one line
    each, so nothing depends on a visitor discovering the footer. Linked from
    the primary nav."""
    items = "".join(
        f'<li class="finding"><p class="what"><a href="{esc(href)}">{esc(name)}</a> '
        f'<span class="availability">{"GitHub account" if href == "/try.html" else "No account"}</span></p>'
        f'<p class="why">{esc(what)}</p></li>'
        for href, name, what in _TOOLS
    )
    body = f"""    {_breadcrumb([("Home", "/"), ("Tools", None)])}
    <a class="backlink" href="/">&larr; Home</a>
    <h1 class="page-title">Tools.</h1>
    <p class="page-lede">Everything on this site you can act with, not just read: check a
    feed, request a full score, compare agencies, query the data, and get alerts. Most work
    without an account; the one-off request is clearly marked because it uses GitHub.</p>
    <ul class="findings">{items}</ul>
    <p class="fineprint">All of it is open source; the
    <a href="https://github.com/ChelseaKR/gtfs-scorecard">repository</a> has the CLI and
    CI-action versions of these tools.</p>"""
    return _page(
        title="Tools — GTFS Scorecard",
        description=(
            "Every self-serve GTFS Scorecard tool: pre-publish checks, ad-hoc scoring, "
            "side-by-side comparison, SQL over the dataset, and feed-health alerts."
        ),
        canonical=f"{BASE_URL}/tools/",
        body=body,
    )
