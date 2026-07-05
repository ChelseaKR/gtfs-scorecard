// @ts-check
/**
 * GTFS Scorecard web app. No build step, no backend: a hash-routed page
 * that reads the JSON artifacts the pipeline publishes.
 *
 * Routes:  #/                  agency picker
 *          #/agency/<id>       one agency's scorecard
 *          #/programs          portfolio rollups (for liaisons/state staff)
 *          #/program/<id>      one rollup across many agencies
 */

/* Presentation constants shared with the pipeline: grade bands and ranks,
 * category and severity labels, tier words, the fix-guide base URL, and the
 * canonical validator rules page. Generated from the Python definitions
 * (pipeline/src/scorecard_pipeline/constants_export.py) by
 * `scorecard render-constants`, so the app cannot drift from the pipeline;
 * pipeline/tests/test_generated_constants.py guards the generated file. */
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  FIX_DOCS_BASE,
  GRADE_BANDS,
  GRADE_RANK,
  SEVERITY_LABELS,
  TIER_LABELS,
  VALIDATOR_RULES_PAGE,
} from "./generated/constants.js";

/** Candidate locations for published artifacts. A configured CDN base
 *  (web/src/config.js) is tried first, then the deployed-site and repo
 *  layouts, so the same app works on GitHub Pages, behind CloudFront, or
 *  straight from the repository. */
const DATA_BASES = [
  /** @type {any} */ (window).SCORECARD_DATA_BASE,
  "data/artifacts",
  "../data/artifacts",
].filter(Boolean);

/** @type {string | null} */
let resolvedBase = null;

/** Authoritative-rule link for a finding code, or "" if none applies. A
 *  non-"scorecard_" code is a raw validator notice, so the rule link is built
 *  deterministically from it; scorecard-only completeness checks get their rule
 *  link on the fix-guide page instead. */
function ruleRefLink(code) {
  if (!code || String(code).startsWith("scorecard_")) return "";
  const url = `${VALIDATOR_RULES_PAGE}#${encodeURIComponent(code)}-rule`;
  return ` ·
            <a class="rule-ref" href="${esc(url)}" target="_blank" rel="noopener">See the GTFS Validator rule<span aria-hidden="true"> ↗</span><span class="visually-hidden"> (opens on gtfs-validator.mobilitydata.org)</span></a>`;
}

const main = /** @type {HTMLElement} */ (document.getElementById("main"));

/* A "cohort" is a personal list of agencies a liaison follows, kept in this
 * browser and shareable by URL (#/cohort?ids=a,b,c). No account, no backend. */
const COHORT_KEY = "scorecard-cohort";

/** @returns {Set<string>} */
function getCohort() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COHORT_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

/** @param {Set<string>} set */
function saveCohort(set) {
  try {
    localStorage.setItem(COHORT_KEY, JSON.stringify([...set]));
  } catch {
    /* storage disabled; cohort just won't persist */
  }
}

/** @param {string} id @returns {Set<string>} */
function toggleCohort(id) {
  const set = getCohort();
  if (set.has(id)) set.delete(id);
  else set.add(id);
  saveCohort(set);
  return set;
}

// Per-agency private notes for the supporter workspace: call notes a liaison
// keeps next to each agency, in this browser only (no account, no backend).
const NOTES_KEY = "scorecard-notes";

/** @returns {Record<string, string>} */
function getNotes() {
  try {
    return JSON.parse(localStorage.getItem(NOTES_KEY) || "{}");
  } catch {
    return {};
  }
}

/** @param {string} id @param {string} text */
function saveNote(id, text) {
  try {
    const notes = getNotes();
    if (text.trim()) notes[id] = text;
    else delete notes[id];
    localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
  } catch {
    /* storage disabled; notes just won't persist */
  }
}

/** Fetch a published JSON artifact, trying each data base until one serves it
 *  as valid JSON. The first base that works is cached, but any later failure
 *  (a partial CDN deploy, or a 200 HTML fallback that fails to parse) falls
 *  through to the next base rather than stranding the app.
 *  @param {string} path @returns {Promise<any>} */
async function fetchJson(path) {
  const ordered = resolvedBase
    ? [resolvedBase, ...DATA_BASES.filter((b) => b !== resolvedBase)]
    : DATA_BASES;
  /** @type {unknown} */
  let lastError = null;
  for (const base of ordered) {
    try {
      const resp = await fetch(`${base}/${path}`);
      if (!resp.ok) {
        lastError = new Error(`HTTP ${resp.status}`);
        continue;
      }
      const data = await resp.json(); // throws on a non-JSON (e.g. HTML) body
      resolvedBase = base;
      return data;
    } catch (err) {
      lastError = err;
    }
  }
  const detail = lastError instanceof Error ? ` (${lastError.message})` : "";
  throw new Error(`Could not load ${path}${detail}.`);
}

/** Return the URL only if it is http(s); otherwise "#". Blocks javascript:/data:
 *  URLs from feed data or submissions becoming clickable XSS sinks.
 *  @param {string} url @returns {string} */
function safeUrl(url) {
  try {
    const u = new URL(url, location.href);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : "#";
  } catch {
    return "#";
  }
}

/** @param {string} text @returns {string} */
function esc(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/** @param {string} grade @returns {string} */
function gradeClass(grade) {
  return `grade-${grade.toLowerCase()}`;
}

/** @param {string} iso @returns {string} */
function formatDate(iso) {
  const [y, m, d] = String(iso).split("-").map(Number);
  const date = new Date(y, m - 1, d);
  if (Number.isNaN(date.getTime())) return String(iso); // malformed date: show as-is
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function routeRule() {
  const dots = '<span class="stopdot"></span>';
  return `<div class="route-rule" role="presentation">
    <span class="stopdot"></span><span class="seg"></span>${dots}<span class="seg"></span>${dots}<span class="seg"></span><span class="stopdot"></span>
  </div>`;
}

/* ---------------- national overview + directory ---------------- */

/** The directory document, fetched once and reused for the overview and for the
 *  per-agency peer line. @type {Promise<any> | null} */
let directoryPromise = null;

/** @returns {Promise<any>} */
function loadDirectory() {
  if (!directoryPromise) directoryPromise = fetchJson("directory.json");
  return directoryPromise;
}

/** The directory record for one agency, or null if the directory can't be
 *  loaded (the scorecard still renders, just without the peer line).
 *  @param {string} id @returns {Promise<any|null>} */
async function directoryRecord(id) {
  try {
    const dir = await loadDirectory();
    return (dir.agencies || []).find((/** @type {any} */ a) => a.id === id) || null;
  } catch {
    return null;
  }
}

const RESULTS_PAGE = 80; // cards rendered per "show more" step

/** Plain-language peer context for one directory card from its size-peer
 *  percentile. Reads the normalized card record (pct, tier).
 *  @param {{pct: number|null, tier: string}} a @returns {string} */
function peerNote(a) {
  const pct = a.pct;
  if (pct == null || a.tier === "unknown") return "";
  const tier = TIER_LABELS[a.tier] || a.tier;
  return `Better than ${pct}% of ${tier} agencies`;
}

/** The national grade-distribution bar: one labelled segment per grade, sized
 *  by share. Decorative fill, but each segment is a labelled list item so the
 *  same information is available without color. @param {any} dist @param {number} total */
function gradeDistributionBar(dist, total) {
  const order = ["A", "B", "C", "D", "F"];
  const segs = order
    .map((g) => {
      const n = dist[g] || 0;
      const pct = total ? Math.round((n / total) * 100) : 0;
      if (!n) return "";
      return `<li class="grade-seg ${gradeClass(g)}" style="--share:${pct}"
        title="${n} graded ${g} (${pct}%)">
        <span class="seg-fill" aria-hidden="true"></span>
        <span class="seg-label">${g} <span class="seg-n">${n}</span></span>
      </li>`;
    })
    .join("");
  return `<ul class="grade-distribution" aria-label="Grade distribution across all agencies">${segs}</ul>`;
}

/** Five buckets of expired-feed share, for the choropleth's sequential fill.
 *  Color is reinforced by each state's title/aria text, never color alone.
 *  @param {number} share @returns {number} */
function expiredQuintile(share) {
  if (share <= 0) return 0;
  if (share < 0.1) return 1;
  if (share < 0.25) return 2;
  if (share < 0.4) return 3;
  return 4;
}

/** Build the US choropleth SVG from the projected state paths and the per-state
 *  summary rows. States with no tracked agencies render faint and inert.
 *  @param {{viewBox: string, states: Record<string,string>}} mapData
 *  @param {Record<string, any>} byState @returns {string} */
function buildMapSvg(mapData, byState) {
  const paths = Object.entries(mapData.states)
    .map(([name, d]) => {
      const row = byState[name];
      if (!row || !row.agencies) {
        return `<path d="${d}" class="us-state us-empty" aria-hidden="true"></path>`;
      }
      const pct = Math.round((row.expired / row.agencies) * 100);
      const q = expiredQuintile(row.expired / row.agencies);
      const noun = row.agencies === 1 ? "agency" : "agencies";
      const label = `${name}: ${row.agencies} ${noun}, ${pct}% of feeds expired`;
      return `<path d="${d}" class="us-state q${q}" data-state="${esc(name)}"
        tabindex="0" role="button" aria-label="${esc(label)} — filter to this state"><title>${esc(label)}</title></path>`;
    })
    .join("");
  const legend = [
    [0, "none expired"],
    [1, "under 10%"],
    [2, "10–25%"],
    [3, "25–40%"],
    [4, "40% or more"],
  ]
    .map(([q, lab]) => `<span class="map-key"><span class="map-swatch q${q}"></span>${lab}</span>`)
    .join("");
  return `<svg class="us-map-svg" viewBox="${mapData.viewBox}" role="group"
      aria-label="Map of the United States; each state is shaded by the share of its tracked GTFS feeds that have expired, and selecting a state filters the list below. Agencies outside the US are listed next to the map.">
      ${paths}
    </svg>
    <p class="map-legend"><span class="map-key-lab">Share of feeds expired:</span> ${legend}</p>`;
}

/** Places the US choropleth cannot draw (Canada), rendered beside the map as
 *  working filter chips so a non-US agency is visible where eyes actually go,
 *  not only in the browse grid further down.
 *  @param {any[]} states */
function beyondUsMapHtml(states) {
  const beyond = (states || []).filter((r) => r.state === "Canada");
  if (!beyond.length) return "";
  const chips = beyond
    .map(
      (r) =>
        `<button type="button" class="state-chip" data-state="${esc(r.state)}" aria-pressed="false">
        ${esc(r.state)} <span class="state-n">${r.agencies}</span></button>`
    )
    .join(" ");
  return `<p class="map-beyond">Not on this US map: ${chips}</p>`;
}

/** @param {any} directory */
function renderOverview(directory) {
  document.title = "GTFS Scorecard — transit data quality, agency by agency";
  const s = directory.summary;
  const cohort = getCohort();
  // Normalize each agency into a flat record the filter/sort/cards reuse.
  const agencies = directory.agencies
    .map((a) => ({
      id: a.id,
      name: a.name,
      grade: String(a.grade),
      score: Number(a.score),
      state: a.state || (a.country === "CA" ? "Canada" : ""),
      tier: a.size_tier || "unknown",
      expiry: a.expiry_status || "unknown",
      pct: a.peer_percentile,
      date: a.snapshot_date,
      search: `${a.name} ${a.id} ${a.state || ""} ${a.country === "CA" ? "canada" : ""}`.toLowerCase(),
    }))
    .sort((x, y) => x.name.localeCompare(y.name));

  const total = agencies.length;
  const expired = s.expired || { total: 0 };
  const stat = (num, lab) => `<div class="stat"><span class="stat-num">${num}</span><span class="stat-lab">${lab}</span></div>`;

  // Browse-by-state grid, biggest first. Each state is a toggle that filters the
  // results below; "Unlocated" is shown last so it never crowds out real places.
  const stateRows = (s.states || []).filter((r) => r.state !== "Unlocated");
  const unlocated = (s.states || []).find((r) => r.state === "Unlocated");
  const stateChips = stateRows
    .map(
      (r) =>
        `<button type="button" class="state-chip" data-state="${esc(r.state)}" aria-pressed="false">
        ${esc(r.state)} <span class="state-n">${r.agencies}</span></button>`
    )
    .join("");
  const unlocatedChip = unlocated
    ? `<button type="button" class="state-chip state-chip-muted" data-state="Unlocated" aria-pressed="false">
        Unlocated <span class="state-n">${unlocated.agencies}</span></button>`
    : "";

  const facet = (key, label) =>
    `<button type="button" class="facet-chip" data-facet="${key}" aria-pressed="${key === "all"}">${label}</button>`;

  main.innerHTML = `
    <h1 class="page-title reveal">How is the country's transit data doing?</h1>
    <p class="page-lede reveal">Every published
    <dfn><abbr title="General Transit Feed Specification">GTFS</abbr></dfn> feed we track, read
    daily and graded in plain language. Find your agency, or browse a state to see the ones that
    need a call. The same directory exists as
    <a href="/agencies/">plain linkable pages</a>; this view adds live search and filters.</p>

    <section class="overview-summary reveal" aria-labelledby="ov-h">
      <h2 class="visually-hidden" id="ov-h">National summary</h2>
      <div class="summary-stats">
        ${stat(total.toLocaleString(), "agencies tracked")}
        ${stat(s.median_score == null ? "—" : s.median_score, "median score")}
        ${stat(s.expiring_soon || 0, "feeds expiring within 30 days")}
        ${stat(expired.total || 0, "feeds already expired")}
      </div>
      ${gradeDistributionBar(s.grade_distribution || {}, total)}
    </section>

    <div class="picker-controls reveal">
      <label for="agency-search" class="visually-hidden">Search agencies by name or state</label>
      <input id="agency-search" class="agency-search" type="search" autocomplete="off"
        enterkeyhint="search" aria-controls="agency-list"
        placeholder="Find your agency among ${total.toLocaleString()}…">
      <div class="picker-sort">
        <label for="agency-sort">Sort</label>
        <select id="agency-sort">
          <option value="az">Name (A–Z)</option>
          <option value="worst">Lowest score first</option>
          <option value="best">Highest score first</option>
        </select>
      </div>
    </div>
    <div class="picker-facets reveal" role="group" aria-label="Filter agencies by grade, size, or feed status">
      ${facet("all", "All")}
      ${facet("A", "A")}${facet("B", "B")}${facet("C", "C")}${facet("D", "D")}${facet("F", "F")}
      ${facet("small", "Small")}${facet("medium", "Mid-size")}${facet("large", "Large")}
      ${facet("lapsed", "Recently lapsed")}${facet("stale", "Long expired")}
    </div>

    <section class="state-browse reveal" aria-labelledby="states-h">
      <h2 class="section-title" id="states-h">Browse by state</h2>
      <div class="us-map" id="us-map" hidden></div>
      <div class="state-grid" role="group" aria-label="Filter agencies by state">
        ${stateChips}${unlocatedChip}
      </div>
    </section>

    <p class="agency-count" role="status" aria-live="polite"></p>
    <ul class="agency-list" id="agency-list"></ul>
    <p class="results-hint" id="results-hint">Search by name, pick a grade or size, or choose a
      state above to list agencies.</p>
    <p class="no-match" hidden>No agencies match.
      <button type="button" class="linklike" id="clear-search">Clear filters</button></p>
    <div class="show-more-wrap" hidden><button type="button" class="show-more" id="show-more">Show more</button></div>

    <p class="picker-aside reveal"><a href="#/cohort" id="my-agencies">My agencies${cohort.size ? ` (${cohort.size})` : ""}</a> &nbsp;·&nbsp;
    <a href="#/compare">Compare two agencies</a> &nbsp;·&nbsp;
    <a href="/how-to-read/">New to this? How to read a scorecard</a> &nbsp;·&nbsp;
    <a href="/submit.html">Add your agency</a> &nbsp;·&nbsp;
    <a href="/subscribe.html">Get feed-health alerts</a> &nbsp;·&nbsp;
    <a href="#/programs">Supporting a group of agencies? See the program rollup view.</a></p>`;

  setupOverview(agencies, total, s);
}

/** Wire the directory: search, grade/size/expiry facet, state selection (chips
 *  and the choropleth), and sort, composed together. The list renders only when
 *  a filter is active, and in pages, so the national set never paints ~1,200
 *  cards at once.
 *  @param {Array<any>} agencies @param {number} total @param {any} summary */
function setupOverview(agencies, total, summary) {
  const input = /** @type {HTMLInputElement} */ (main.querySelector("#agency-search"));
  const list = /** @type {HTMLElement} */ (main.querySelector("#agency-list"));
  const count = /** @type {HTMLElement} */ (main.querySelector(".agency-count"));
  const hint = /** @type {HTMLElement} */ (main.querySelector("#results-hint"));
  const noMatch = /** @type {HTMLElement} */ (main.querySelector(".no-match"));
  const clear = /** @type {HTMLElement} */ (main.querySelector("#clear-search"));
  const sortSel = /** @type {HTMLSelectElement} */ (main.querySelector("#agency-sort"));
  const moreWrap = /** @type {HTMLElement} */ (main.querySelector(".show-more-wrap"));
  const moreBtn = /** @type {HTMLElement} */ (main.querySelector("#show-more"));
  const facetBtns = /** @type {HTMLElement[]} */ (Array.from(main.querySelectorAll(".facet-chip")));
  const stateBtns = /** @type {HTMLElement[]} */ (Array.from(main.querySelectorAll(".state-chip")));
  const myLink = /** @type {HTMLElement} */ (main.querySelector("#my-agencies"));

  // Deep-linkable filters: restore the view (state, facet, search, sort) from the
  // URL so a filtered list can be shared or bookmarked, and write it back as the
  // filters change. Mirrors the #/cohort route, which already carries its ids.
  const defaultSort = sortSel.value;
  const urlQi = location.hash.indexOf("?");
  const urlParams = new URLSearchParams(urlQi >= 0 ? location.hash.slice(urlQi + 1) : "");
  const facetValues = new Set(facetBtns.map((b) => b.dataset.facet));
  const wantFacet = urlParams.get("facet");
  let facet = facetValues.has(wantFacet) ? wantFacet : "all";
  const stateValues = new Set(stateBtns.map((b) => b.dataset.state));
  const wantState = urlParams.get("state");
  let state = stateValues.has(wantState) ? wantState : "all";
  let shown = 0; // how many of the current matches are painted
  let matches = /** @type {any[]} */ ([]);
  const qParam = urlParams.get("q");
  if (qParam) input.value = qParam;
  const sortParam = urlParams.get("sort");
  if (sortParam && Array.from(sortSel.options).some((o) => o.value === sortParam)) {
    sortSel.value = sortParam;
  }
  for (const b of facetBtns) b.setAttribute("aria-pressed", String(b.dataset.facet === facet));

  // Reflect the live filter state in the URL without reloading the route:
  // replaceState never fires hashchange, so route() is not re-run.
  function syncUrl() {
    const p = new URLSearchParams();
    if (state !== "all") p.set("state", state);
    if (facet !== "all") p.set("facet", facet);
    const q = input.value.trim();
    if (q) p.set("q", q);
    if (sortSel.value !== defaultSort) p.set("sort", sortSel.value);
    const qs = p.toString();
    const next = qs ? `#/?${qs}` : "#/";
    // Some browsers (Safari) throttle replaceState and throw; a failed URL sync
    // must never abort the filtering it is called from.
    if (next !== location.hash) {
      try {
        history.replaceState(null, "", next);
      } catch (_e) {
        /* URL not updated this time; the filter still applied. */
      }
    }
  }

  function matchesFacet(a) {
    if (facet === "all") return true;
    if (facet === "lapsed" || facet === "stale") return a.expiry === facet;
    if (facet === "small" || facet === "medium" || facet === "large") return a.tier === facet;
    return a.grade === facet;
  }

  function cardHtml(a) {
    const cohort = getCohort();
    const followed = cohort.has(a.id);
    const note = peerNote(a);
    const where = a.state ? ` · ${esc(a.state)}` : "";
    return `<li class="agency-card">
      <span class="grade-chip ${gradeClass(a.grade)}">${esc(a.grade)}<span class="visually-hidden"> grade</span></span>
      <div>
        <h2><a href="#/agency/${esc(a.id)}">${esc(a.name)}</a></h2>
        <p class="meta">Overall ${a.score} out of 100${where} · checked ${formatDate(a.date)}</p>
        ${note ? `<p class="peer-note">${esc(note)}</p>` : ""}
      </div>
      <button type="button" class="follow" data-id="${esc(a.id)}" aria-pressed="${followed}">${followed ? "Following" : "Follow"}</button>
    </li>`;
  }

  function sorted(rows) {
    const mode = sortSel.value;
    if (mode === "az") return rows;
    return rows.slice().sort((a, b) => (mode === "best" ? b.score - a.score : a.score - b.score));
  }

  function paintMore() {
    const next = matches.slice(shown, shown + RESULTS_PAGE);
    list.insertAdjacentHTML("beforeend", next.map(cardHtml).join(""));
    shown += next.length;
    moreWrap.hidden = shown >= matches.length;
    if (!moreWrap.hidden) moreBtn.textContent = `Show more (${matches.length - shown} more)`;
  }

  function apply() {
    syncUrl();
    const tokens = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const active = tokens.length || facet !== "all" || state !== "all";
    hint.hidden = active;
    list.innerHTML = "";
    shown = 0;
    if (!active) {
      matches = [];
      count.textContent = "";
      noMatch.hidden = true;
      moreWrap.hidden = true;
      return;
    }
    matches = sorted(
      agencies.filter(
        (a) =>
          tokens.every((t) => a.search.includes(t)) &&
          matchesFacet(a) &&
          (state === "all" || a.state === state)
      )
    );
    const noun = matches.length === 1 ? "agency" : "agencies";
    count.textContent = `${matches.length.toLocaleString()} of ${total.toLocaleString()} ${noun}`;
    noMatch.hidden = matches.length !== 0;
    paintMore();
  }

  input.addEventListener("input", apply);
  sortSel.addEventListener("change", apply);
  moreBtn.addEventListener("click", paintMore);
  for (const btn of facetBtns) {
    btn.addEventListener("click", () => {
      facet = btn.dataset.facet || "all";
      for (const b of facetBtns) b.setAttribute("aria-pressed", String(b === btn));
      apply();
    });
  }
  // State can be picked from a chip or the choropleth; keep both in sync.
  let mapPaths = /** @type {HTMLElement[]} */ ([]);
  function syncStateUI() {
    for (const b of stateBtns) b.setAttribute("aria-pressed", String(b.dataset.state === state));
    for (const p of mapPaths) p.classList.toggle("selected", p.dataset.state === state);
  }
  function selectState(name) {
    state = state === name ? "all" : name; // pick again to clear
    syncStateUI();
    apply();
  }
  for (const btn of stateBtns) {
    btn.addEventListener("click", () => selectState(btn.dataset.state || "all"));
  }
  clear.addEventListener("click", () => {
    input.value = "";
    facet = "all";
    state = "all";
    for (const b of facetBtns) b.setAttribute("aria-pressed", String(b.dataset.facet === "all"));
    syncStateUI();
    apply();
    input.focus();
  });

  // Mount the choropleth as progressive enhancement: the chip grid already
  // covers browse-by-state, so if the geometry asset can't load the map is just
  // omitted. The asset lives at the site root (web/us-states.json), reached
  // relative to /app/ rather than through the data base.
  (async function mountMap() {
    const host = /** @type {HTMLElement} */ (main.querySelector("#us-map"));
    if (!host) return;
    let mapData;
    try {
      const resp = await fetch(new URL("../us-states.json", location.href));
      if (!resp.ok) return;
      mapData = await resp.json();
    } catch {
      return;
    }
    const byState = {};
    for (const r of summary.states || []) byState[r.state] = r;
    host.innerHTML = buildMapSvg(mapData, byState) + beyondUsMapHtml(summary.states);
    host.hidden = false;
    // The beyond-US chips arrive after the initial chip wiring, so wire them
    // here and fold them into stateBtns so aria-pressed stays in sync.
    for (const chip of Array.from(host.querySelectorAll(".state-chip"))) {
      chip.addEventListener("click", () => selectState(chip.dataset.state || "all"));
      stateBtns.push(/** @type {HTMLElement} */ (chip));
    }
    mapPaths = /** @type {HTMLElement[]} */ (Array.from(host.querySelectorAll("path[data-state]")));
    for (const p of mapPaths) {
      p.addEventListener("click", () => selectState(p.dataset.state || "all"));
      p.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectState(p.dataset.state || "all");
        }
      });
    }
    syncStateUI();
  })();

  // Follow / unfollow agencies into the personal cohort.
  list.addEventListener("click", (event) => {
    const btn = /** @type {HTMLElement} */ (event.target).closest(".follow");
    if (!(btn instanceof HTMLElement) || !btn.dataset.id) return;
    const set = toggleCohort(btn.dataset.id);
    const on = set.has(btn.dataset.id);
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Following" : "Follow";
    if (myLink) myLink.textContent = `My agencies${set.size ? ` (${set.size})` : ""}`;
  });

  syncStateUI();
  apply();
}

/* ---------------- program rollups ---------------- */

/** @param {any} index */
function renderPrograms(index) {
  document.title = "Program rollups — GTFS Scorecard";
  const rollups = index.rollups || [];
  const cards = rollups
    .map((r) => {
      const attention = r.needs_attention
        ? `<span class="pill-warn">${r.needs_attention} need attention</span>`
        : `<span class="pill-ok">all in good shape</span>`;
      const avg = r.average_score == null ? "—" : `${r.average_score} avg`;
      return `<li class="agency-card reveal">
        <div>
          <h2><a href="#/program/${esc(r.id)}">${esc(r.name)}</a></h2>
          <p class="meta">${r.agency_count} agencies · ${avg} · ${attention}</p>
        </div>
      </li>`;
    })
    .join("");
  main.innerHTML = `
    <a class="backlink" href="#/">&larr; All agencies</a>
    <h1 class="page-title reveal">Program rollups.</h1>
    <p class="page-lede reveal">A view for the people who support many agencies at once.
    Each rollup lists its agencies worst-first, so the ones that need a call are at the top,
    and surfaces the fixes shared across several feeds.</p>
    <ul class="agency-list">${cards}</ul>`;
}

/** @param {any} rollup */
function renderProgram(rollup) {
  document.title = `${rollup.rollup.name} — GTFS Scorecard`;
  const rows = rollup.members
    .map((m) => {
      const flag = m.needs_attention
        ? ` <span class="pill-warn">${esc(m.attention_reason || "needs attention")}</span>`
        : "";
      const fix = m.top_fix ? `<p class="program-fix">Start with: ${esc(m.top_fix)}</p>` : "";
      return `<li class="program-row">
        <span class="grade-chip ${gradeClass(m.grade)}">${esc(m.grade)}<span class="visually-hidden"> grade</span></span>
        <div>
          <h3><a href="#/agency/${esc(m.id)}">${esc(m.name)}</a>${flag}</h3>
          <p class="meta">${m.score} out of 100 · checked ${formatDate(m.snapshot_date)}</p>
          ${fix}
        </div>
      </li>`;
    })
    .join("");

  const dist = Object.entries(rollup.grade_distribution || {})
    .map(([g, n]) => `<span class="grade-chip ${gradeClass(g)}">${esc(g)}</span> ${n}`)
    .join(" &nbsp; ");

  const common = (rollup.common_fixes || [])
    .map(
      (c) => `<li class="fix-card">
        <p class="fix-action">${esc(c.fix)}</p>
        <p class="fix-why">Affects ${c.agencies} agencies in this group.</p>
      </li>`
    )
    .join("");
  const commonSection = common
    ? `${routeRule()}
       <section aria-labelledby="shared-h" class="reveal">
         <h2 class="section-title" id="shared-h">Fixes shared across the group</h2>
         <p class="page-lede">One export setting can lift several agencies at once.</p>
         <ol class="fixes">${common}</ol>
       </section>`
    : "";

  const avg = rollup.average_score == null ? "—" : `${rollup.average_score} out of 100`;
  const shapes = rollup.shapes_readiness;
  const measured = shapes ? shapes.total - shapes.not_measured : 0;
  const shapesNote =
    shapes && measured > 0
      ? `<p class="snapshot-note">shapes.txt (NTD RY2026): ${shapes.ready} of ${measured} ready</p>`
      : "";
  main.innerHTML = `
    <a class="backlink" href="#/programs">&larr; All rollups</a>
    <div class="score-hero reveal">
      <div>
        <h1 class="page-title">${esc(rollup.rollup.name)}</h1>
        <p class="overall"><strong>${rollup.agency_count} agencies</strong> ·
          ${avg} average · ${rollup.needs_attention} need attention</p>
        <p class="snapshot-note">Grade mix: ${dist || "—"}</p>
        ${shapesNote}
      </div>
    </div>
    ${routeRule()}
    <section aria-labelledby="members-h" class="reveal">
      <h2 class="section-title" id="members-h">Agencies, worst first</h2>
      <ul class="program-list">${rows}</ul>
    </section>
    ${commonSection}`;
}

/* ---------------- my cohort (client-side) ---------------- */

/** Render the follower's personal cohort, worst-first, the same way a program
 *  rollup reads. Membership comes from a shared URL or this browser's saved list.
 *  @param {any} index @param {string[]|null} urlIds */
async function renderCohort(index, urlIds) {
  document.title = "My agencies — GTFS Scorecard";
  const fromUrl = urlIds && urlIds.length ? urlIds : null;
  if (fromUrl) saveCohort(new Set(fromUrl)); // a shared link replaces the saved list
  const ids = (fromUrl || [...getCohort()]).filter((id) => index.agencies[id]);

  if (!ids.length) {
    main.innerHTML = `<a class="backlink" href="#/">&larr; All agencies</a>
      <h1 class="page-title">My agencies</h1>
      <p class="page-lede">You haven't followed any agencies yet. On the
      <a href="#/">directory</a>, use the <strong>Follow</strong> button to build a list you can
      check at a glance and share with a colleague.</p>`;
    return;
  }

  const members = [];
  for (const id of ids) {
    const a = index.agencies[id];
    const hist = a.history || [];
    const last = hist[hist.length - 1] || { score: 0, grade: "F", date: "" };
    let days = null;
    let topFix = null;
    try {
      const art = await fetchJson(`${id}/latest.json`);
      days = art.categories?.freshness?.details?.days_until_expiry ?? null;
      topFix = art.top_fixes && art.top_fixes[0] ? art.top_fixes[0].fix : null;
    } catch {
      /* keep the row from index data even if the artifact is briefly unavailable */
    }
    const prev = hist.length >= 2 ? hist[hist.length - 2] : null;
    const regressed =
      prev &&
      (GRADE_RANK[last.grade] < GRADE_RANK[prev.grade] || prev.score - last.score >= 3);
    let reason = null;
    if (days != null && days <= 0) reason = `Feed expired ${-days} day(s) ago`;
    else if (days != null && days <= 30) reason = `Feed expires in ${days} day(s)`;
    else if (regressed) reason = `Grade slipped to ${last.grade}`;
    const scoreDelta = prev ? Math.round((last.score - prev.score) * 10) / 10 : null;
    members.push({
      id,
      name: a.name,
      score: last.score,
      grade: last.grade,
      date: last.date,
      reason,
      topFix,
      days,
      prevGrade: prev ? prev.grade : null,
      prevDate: prev ? prev.date : null,
      scoreDelta,
      gradeChanged: !!(prev && last.grade !== prev.grade),
    });
  }
  members.sort((m, n) => (!!m.reason === !!n.reason ? m.score - n.score : m.reason ? -1 : 1));

  const notes = getNotes();
  const changed = members.filter((m) => m.gradeChanged);
  // Shared fixes: one export setting that would help several followed agencies.
  const fixCounts = {};
  for (const m of members) if (m.topFix) fixCounts[m.topFix] = (fixCounts[m.topFix] || 0) + 1;
  const sharedFixes = Object.entries(fixCounts)
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1]);

  /** Plain-text call-prep brief for pasting into notes or an email. */
  function callPrep() {
    const stamp = new Date().toISOString().slice(0, 10);
    const lines = [`Call prep — My agencies (${stamp})`, `${members.length} agencies, ${attn} need attention.`, ""];
    for (const m of members) {
      lines.push(`${m.name} — Grade ${m.grade} (${m.score}/100)`);
      if (m.reason) lines.push(`  Status: ${m.reason}`);
      if (m.gradeChanged) lines.push(`  Changed: ${m.prevGrade} -> ${m.grade} since ${m.prevDate}`);
      else if (m.scoreDelta) lines.push(`  Score ${m.scoreDelta > 0 ? "up" : "down"} ${Math.abs(m.scoreDelta)} since ${m.prevDate}`);
      if (m.topFix) lines.push(`  Start with: ${m.topFix}`);
      if (notes[m.id]) lines.push(`  Notes: ${notes[m.id]}`);
      lines.push("");
    }
    return lines.join("\n");
  }

  const attn = members.filter((m) => m.reason).length;
  const shareUrl = `${location.origin}${location.pathname}#/cohort?ids=${ids.join(",")}`;
  const rows = members
    .map((m) => {
      const flag = m.reason ? ` <span class="pill-warn">${esc(m.reason)}</span>` : "";
      const fix = m.topFix ? `<p class="program-fix">Start with: ${esc(m.topFix)}</p>` : "";
      let change = "";
      if (m.gradeChanged)
        change = `<p class="cohort-change">Grade ${esc(m.prevGrade)} &rarr; ${esc(m.grade)} since ${formatDate(m.prevDate)}</p>`;
      else if (m.scoreDelta)
        change = `<p class="cohort-change">Score ${m.scoreDelta > 0 ? "up" : "down"} ${Math.abs(m.scoreDelta)} since ${formatDate(m.prevDate)}</p>`;
      const note = notes[m.id] || "";
      return `<li class="program-row">
        <span class="grade-chip ${gradeClass(m.grade)}">${esc(m.grade)}<span class="visually-hidden"> grade</span></span>
        <div>
          <h3><a href="#/agency/${esc(m.id)}">${esc(m.name)}</a>${flag}</h3>
          <p class="meta">${m.score} out of 100 · checked ${formatDate(m.date)}</p>
          ${change}
          ${fix}
          <details class="cohort-note"${note ? " open" : ""}>
            <summary>Note${note ? " ✓" : ""}</summary>
            <label class="visually-hidden" for="note-${esc(m.id)}">Private note for ${esc(m.name)}</label>
            <textarea id="note-${esc(m.id)}" class="note-input" data-id="${esc(m.id)}"
              rows="2" placeholder="Call notes (saved in this browser only)">${esc(note)}</textarea>
          </details>
        </div>
        <button type="button" class="cohort-remove" data-id="${esc(m.id)}" aria-label="Remove ${esc(m.name)} from my agencies">Remove</button>
      </li>`;
    })
    .join("");

  const sharedHtml = sharedFixes.length
    ? `${routeRule()}
    <section aria-labelledby="shared-h" class="reveal">
      <h2 class="section-title" id="shared-h">Fixes that help several at once</h2>
      <ul class="shared-fixes">${sharedFixes
        .map(([fix, n]) => `<li><strong>${n} agencies:</strong> ${esc(fix)}</li>`)
        .join("")}</ul>
    </section>`
    : "";
  const changedHtml = changed.length
    ? `<p class="cohort-changed-note">${changed.length} changed grade since their last check: ${changed
        .map((m) => `${esc(m.name)} (${esc(m.prevGrade)}&rarr;${esc(m.grade)})`)
        .join(", ")}.</p>`
    : "";

  main.innerHTML = `
    <a class="backlink" href="#/">&larr; All agencies</a>
    <div class="score-hero reveal">
      <div>
        <h1 class="page-title">My agencies</h1>
        <p class="overall"><strong>${members.length} agencies</strong> · ${attn} need attention · ${changed.length} changed</p>
        <p class="snapshot-note">A pre-call view, kept in this browser. Sorted so the calls worth making sit on top.</p>
        ${changedHtml}
      </div>
    </div>
    <p class="picker-aside">
      <button type="button" class="linklike" id="copy-prep">Copy call prep</button> &nbsp;·&nbsp;
      <button type="button" class="linklike" id="print-cohort">Print</button> &nbsp;·&nbsp;
      <button type="button" class="linklike" id="copy-cohort">Copy a shareable link</button>
      <span id="copy-done" role="status"></span></p>
    ${sharedHtml}
    ${routeRule()}
    <section aria-labelledby="cohort-h" class="reveal">
      <h2 class="section-title" id="cohort-h">Agencies, worst first</h2>
      <ul class="program-list">${rows}</ul>
    </section>`;

  const done = /** @type {HTMLElement} */ (main.querySelector("#copy-done"));
  const copy = /** @type {HTMLElement} */ (main.querySelector("#copy-cohort"));
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      done.textContent = " Link copied.";
    } catch {
      done.textContent = ` ${shareUrl}`;
    }
  });
  main.querySelector("#copy-prep")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(callPrep());
      done.textContent = " Call prep copied to clipboard.";
    } catch {
      done.textContent = " Copy failed; select and copy from print view instead.";
    }
  });
  main.querySelector("#print-cohort")?.addEventListener("click", () => window.print());
  for (const ta of main.querySelectorAll(".note-input")) {
    ta.addEventListener("input", (e) => {
      const el = /** @type {HTMLTextAreaElement} */ (e.target);
      saveNote(el.dataset.id || "", el.value);
    });
  }
  for (const btn of main.querySelectorAll(".cohort-remove")) {
    btn.addEventListener("click", () => {
      toggleCohort(/** @type {HTMLElement} */ (btn).dataset.id || "");
      route();
    });
  }
}

/* ---------------- scorecard page ---------------- */

/** @param {any} artifact @param {any} history @param {any} [dirRecord] */
function renderScorecard(artifact, history, dirRecord) {
  const name = artifact.agency.name;
  document.title = `${name} — GTFS Scorecard`;
  const overall = artifact.overall;

  const cats = CATEGORY_ORDER.map((key, i) => categoryCard(key, artifact.categories[key], i)).join("");
  const fixes = topFixes(artifact.top_fixes);
  const findings = collectFindings(artifact);
  const recsHtml = recommendationsSection(artifact);
  const autofixHtml = autofixSection(artifact);
  const ntdHtml = ntdSection(artifact);
  const confHtml = conformanceSection(artifact, artifact.agency.id, artifact.agency.name);
  // Only precede a section with a rule when it has content, so a missing block
  // (an older artifact, or nothing to recommend) leaves no stray divider.
  const sep = (html) => (html ? `${routeRule()}${html}` : "");

  main.innerHTML = `
    <a class="backlink" href="#/">&larr; All agencies</a>
    ${boardHero(name, artifact, history, dirRecord)}
    <p class="disclaimer">A data-quality and completeness lens to help an agency improve its
      <abbr title="General Transit Feed Specification">GTFS</abbr> feed. Not an official compliance
      determination from any transit program.
      <a href="/how-to-read/">New to this? How to read your scorecard.</a></p>

    ${routeRule()}
    <section aria-labelledby="fixes-h" class="reveal">
      <h2 class="section-title" id="fixes-h">Top things to fix</h2>
      ${fixes}
    </section>

    ${routeRule()}
    <section aria-labelledby="cats-h" class="reveal">
      <h2 class="section-title" id="cats-h">Score by category</h2>
      <div class="platforms">${cats}</div>
    </section>

    ${routeRule()}
    ${trendSection(history)}

    ${routeRule()}
    <section aria-labelledby="findings-h" class="reveal">
      <h2 class="section-title" id="findings-h">Everything we checked</h2>
      <div class="filterbar" role="group" aria-label="Filter findings by severity"></div>
      <p class="findings-count" role="status"></p>
      <ul class="findings"></ul>
    </section>
    ${sep(recsHtml)}
    ${sep(autofixHtml)}
    ${sep(ntdHtml)}
    ${sep(confHtml)}

    ${routeRule()}
    ${standardsSection(dirRecord && dirRecord.state)}

    ${routeRule()}
    ${badgeSection(artifact.agency.id)}

    ${routeRule()}
    <section aria-labelledby="feed-h" class="feed-details">
      <h2 class="section-title" id="feed-h">About this data</h2>
      <dl>
        <dt>Feed checked</dt><dd><a href="${esc(safeUrl(artifact.feed.static_url))}">${esc(artifact.feed.static_url)}</a></dd>
        <dt>Snapshot</dt><dd>${esc(artifact.snapshot_date)}${artifact.feed?.sha256 ? ` (<abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr> ${esc(artifact.feed.sha256.slice(0, 12))}…)` : ""}</dd>
        <dt>Validator</dt><dd>MobilityData gtfs-validator ${esc(String(artifact.validator_version ?? artifact.categories.correctness?.details?.validator_version ?? ""))}</dd>
        <dt>Rubric</dt><dd>version ${esc(String(artifact.rubric_version ?? "—"))}; <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/rubric.md">methodology and citations (docs/rubric.md)</a></dd>
      </dl>
    </section>`;

  setupFindings(findings);
}

/** Split-flap grade reel that lands on the agency's grade. @param {string} grade */
function gradeReel(grade) {
  const g = String(grade || "F").toUpperCase().slice(0, 1);
  const idx = GRADE_RANK[g] ?? 0;
  return `<div class="reel" role="img" aria-label="Overall grade ${esc(g)}"
      style="--flap-end: calc(var(--reel-h) * -${idx})">
    <div class="reel-strip"><span>F</span><span>D</span><span>C</span><span>B</span><span>A</span></div>
  </div>`;
}

/** Status chips from the feed's freshness, completeness, and realtime. @param {any} artifact */
function statusChips(artifact) {
  const chips = [];
  const days = artifact.categories?.freshness?.details?.days_until_expiry;
  if (typeof days === "number") {
    if (days <= 0) chips.push('<span class="chip warn">Feed expired</span>');
    else if (days < 30) chips.push(`<span class="chip warn">Expires in ${days} days</span>`);
    else chips.push(`<span class="chip ok">Covers ${days} days</span>`);
  }
  const comp = artifact.categories?.completeness;
  if (comp?.status === "measured" && comp.score < 70)
    chips.push('<span class="chip warn">Accessibility gaps</span>');
  if (artifact.categories?.realtime?.status !== "measured")
    chips.push('<span class="chip">No realtime feed</span>');
  return chips.join("");
}

/** A clean trend line for the board (no leading separator). @param {any[]} history */
function boardTrend(history) {
  if (history.length < 2) return "First scorecard for this agency";
  const prev = history[history.length - 2];
  const cur = history[history.length - 1];
  const d = Math.round((cur.score - prev.score) * 10) / 10;
  if (d > 0)
    return `<span aria-hidden="true">▲</span> up ${d} since ${formatDate(prev.date)} · ${prev.grade} → ${cur.grade}`;
  if (d < 0) return `<span aria-hidden="true">▼</span> down ${Math.abs(d)} since ${formatDate(prev.date)}`;
  return `unchanged since ${formatDate(prev.date)}`;
}

/** Where this agency stands against the national set and its size peers.
 *  Empty when the directory record or its percentiles are unavailable.
 *  @param {any} [dirRecord] */
function peerContext(dirRecord) {
  if (!dirRecord) return "";
  const nat = dirRecord.national_percentile;
  const peer = dirRecord.peer_percentile;
  const tier = TIER_LABELS[dirRecord.size_tier] || dirRecord.size_tier;
  if (nat == null) return "";
  const peerPart =
    peer != null && tier && dirRecord.size_tier !== "unknown"
      ? ` and ${peer}% of ${tier} agencies`
      : "";
  const where = dirRecord.state ? ` Operates in ${esc(dirRecord.state)}.` : "";
  return `<p class="peer-context">Ahead of ${nat}% of all tracked agencies${peerPart}.${where}</p>`;
}

/** @param {string} name @param {any} artifact @param {any[]} history @param {any} [dirRecord] */
function boardHero(name, artifact, history, dirRecord) {
  const o = artifact.overall;
  return `<div class="board-hero reveal">
    <div class="board-inner">
      <p class="board-kicker"><span class="blip" aria-hidden="true"></span>Feed status · checked ${formatDate(artifact.snapshot_date)}</p>
      <h1 class="board-title">${esc(name)}</h1>
      <p class="board-sub">Based on the feed this agency publishes</p>
      <div class="grade-block">
        ${gradeReel(o.grade)}
        <div class="score-block">
          <div><span class="score-big">${o.score}</span><span class="score-of"> / 100</span></div>
          <p class="score-trend">${boardTrend(history)}</p>
          ${peerContext(dirRecord)}
          <div class="chips">${statusChips(artifact)}</div>
        </div>
      </div>
    </div>
  </div>`;
}

/** @param {Array<{date: string, score: number, grade: string}>} history */
function trendNote(history) {
  if (history.length < 2) return " · first scorecard for this agency";
  const prev = history[history.length - 2];
  const cur = history[history.length - 1];
  const delta = Math.round((cur.score - prev.score) * 10) / 10;
  if (delta > 0) return ` · <span aria-hidden="true">▲</span> up ${delta} since ${formatDate(prev.date)}`;
  if (delta < 0) return ` · <span aria-hidden="true">▼</span> down ${Math.abs(delta)} since ${formatDate(prev.date)}`;
  return ` · unchanged since ${formatDate(prev.date)}`;
}

/** Inline SVG line of the overall score across checks, mirroring the static
 *  pages' shared sparkline (_spark_svg in render_site.py): a dot at every
 *  check carries a native hover tooltip (its date and score), the last one
 *  emphasised, and the aria-label carries the full series for screen readers.
 *  The operable equivalent is the "Show the numbers" table below the chart.
 *  @param {any[]} history */
function scoreSparkline(history) {
  const w = 320;
  const h = 64;
  const pad = 8;
  const n = history.length;
  const x = (i) => pad + (n === 1 ? (w - 2 * pad) / 2 : (i * (w - 2 * pad)) / (n - 1));
  const y = (s) => h - pad - (Math.max(0, Math.min(100, Number(s))) / 100) * (h - 2 * pad);
  const pts = history.map((p, i) => `${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const series = history.map((p) => `${formatDate(p.date)} ${p.score}`).join("; ");
  const dots = history
    .map(
      (p, i) =>
        `<circle class="trend-dot" cx="${x(i).toFixed(1)}" cy="${y(p.score).toFixed(1)}"
        r="${i === n - 1 ? 4 : 2.5}" fill="currentColor"><title>${esc(
          `${formatDate(p.date)}: ${p.score}`,
        )}</title></circle>`,
    )
    .join("");
  return `<svg class="trend-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
      role="img" aria-label="Overall score across ${n} checks: ${esc(series)}">
    <polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}
  </svg>`;
}

/** The "Show the numbers" table: the operable, screen-reader equivalent of the
 *  sparkline, mirroring the static pages' trend-table markup. Every check's
 *  date, score, and change from the check before, the change carried in words
 *  and an arrow, never colour alone.
 *  @param {any[]} history */
function trendDataTable(history) {
  const rows = history
    .map((p, i) => {
      let change;
      if (i === 0) {
        change = `<span class="delta delta-flat"><span aria-hidden="true">—</span> first check</span>`;
      } else {
        const d = Math.round((p.score - history[i - 1].score) * 10) / 10;
        const t = d > 0 ? `up ${d}` : d < 0 ? `down ${Math.abs(d)}` : "no change";
        const sym = d > 0 ? "▲" : d < 0 ? "▼" : "—";
        const cls = d > 0 ? "delta-up" : d < 0 ? "delta-down" : "delta-flat";
        change = `<span class="delta ${cls}"><span aria-hidden="true">${sym}</span> ${t}</span>`;
      }
      return `<tr><th scope="row">${esc(formatDate(p.date))}</th>
        <td>${esc(String(p.score))}</td><td>${change}</td></tr>`;
    })
    .join("");
  return `<details class="trend-data"><summary>Show the numbers</summary>
    <table class="trend-table"><caption class="visually-hidden">Overall score by
    check, with the change from the previous check</caption>
    <thead><tr><th scope="col">Check</th><th scope="col">Score</th>
    <th scope="col">Change</th></tr></thead>
    <tbody>${rows}</tbody></table></details>`;
}

/** Per-category change between the two most recent checks. @param {any[]} history */
function sinceLastCheck(history) {
  const cur = history[history.length - 1];
  const prev = history[history.length - 2];
  const rows = CATEGORY_ORDER.map((key) => {
    const a = prev.categories?.[key];
    const b = cur.categories?.[key];
    if (a == null || b == null) return null;
    const d = Math.round((b - a) * 10) / 10;
    const label = CATEGORY_LABELS[key];
    const text = d > 0 ? `up ${d}` : d < 0 ? `down ${Math.abs(d)}` : "no change";
    const sym = d > 0 ? "▲" : d < 0 ? "▼" : "—";
    const cls = d > 0 ? "delta-up" : d < 0 ? "delta-down" : "delta-flat";
    return `<li class="delta-row"><span class="delta-cat">${esc(label)}</span>
      <span class="delta ${cls}"><span aria-hidden="true">${sym}</span> ${text}</span></li>`;
  }).filter(Boolean);
  return rows.length ? `<ul class="delta-list">${rows.join("")}</ul>` : "";
}

/** The "Over time" section: trend line plus what changed since the last check.
 *  @param {any[]} history */
function trendSection(history) {
  if (history.length < 2) {
    return `<section aria-labelledby="trend-h" class="reveal">
      <h2 class="section-title" id="trend-h">Over time</h2>
      <p class="page-lede">This is the first scorecard for this agency. A trend and a
      "what changed" summary appear here once it has been checked more than once.</p>
    </section>`;
  }
  const cur = history[history.length - 1];
  const prev = history[history.length - 2];
  const delta = Math.round((cur.score - prev.score) * 10) / 10;
  const dir = delta > 0 ? `up ${delta}` : delta < 0 ? `down ${Math.abs(delta)}` : "unchanged";
  return `<section aria-labelledby="trend-h" class="reveal">
    <h2 class="section-title" id="trend-h">Over time</h2>
    <p class="page-lede">Overall score across the last ${history.length} checks —
      ${dir} since ${formatDate(prev.date)}.</p>
    <div class="trend-chart">${scoreSparkline(history)}</div>
    ${trendDataTable(history)}
    <h3 class="trend-sub">What changed since your last check</h3>
    ${sinceLastCheck(history)}
  </section>`;
}

/** @param {string} key @param {any} cat */
/** Map a 0-100 score to a grade-band token (a/b/c/d/f): the rubric's own
 *  letter, from the generated GRADE_BANDS (highest floor first).
 *  @param {number} score */
function gradeBand(score) {
  const s = Number(score);
  const band = GRADE_BANDS.find((b) => s >= b.min_score);
  return (band ? band.grade : "F").toLowerCase();
}

/** One category as a departure-board "platform" row. @param {string} key @param {any} cat @param {number} index */
function categoryCard(key, cat, index) {
  const label = CATEGORY_LABELS[/** @type {keyof CATEGORY_LABELS} */ (key)] ?? key;
  const trk = String(index + 1).padStart(2, "0");
  if (!cat || cat.status !== "measured") {
    const note = cat?.summary ?? "Not part of the grade yet. Nothing here counts against you.";
    return `<div class="platform neutral">
      <span class="trk" aria-hidden="true">${trk}</span>
      <div class="pmain">
        <div class="ptop">
          <span class="pname">${esc(label)}</span>
          <span class="pscore">Not yet measured</span>
        </div>
        <p class="pstat">${esc(note)}</p>
      </div>
    </div>`;
  }
  const score = Number(cat.score);
  const band = gradeBand(score);
  const w = Math.max(2, Math.min(100, score));
  return `<div class="platform">
    <span class="trk" aria-hidden="true">${trk}</span>
    <div class="pmain">
      <div class="ptop">
        <span class="pname">${esc(label)}</span>
        <span class="pscore">${score}<span class="outof"> / 100</span></span>
      </div>
      <div class="pbar" role="meter" aria-valuenow="${score}" aria-valuemin="0"
           aria-valuemax="100" aria-label="${esc(label)} score">
        <span style="width:${w}%;background:var(--grade-${band})"></span>
      </div>
      <p class="pstat">${esc(cat.summary)}</p>
    </div>
  </div>`;
}

/** Top fixes as prioritized "service alerts". @param {any[]} fixes */
function topFixes(fixes) {
  if (!fixes.length) {
    return `<p class="all-clear">Nothing urgent. This feed passed every check we
    translate into fixes — keep publishing on schedule.</p>`;
  }
  return `<div class="alerts">${fixes
    .map((f, i) => {
      const sev = String(f.severity || "").toUpperCase();
      const cls = sev === "WARNING" ? " sev-warning" : sev === "INFO" ? " sev-info" : "";
      const rank = String(i + 1).padStart(2, "0");
      const worth =
        typeof f.points === "number" && f.points >= 1
          ? `<span class="aworth">worth about +${Math.round(f.points)} points</span>`
          : "";
      const owner = f.owner ? `<span class="aowner">${esc(f.owner)}</span>` : "";
      return `<div class="alert">
        <span class="badge${cls}">Fix ${rank}</span>
        <div>
          <p class="afix">${esc(f.fix)}${owner}</p>
          <p class="awhy">${esc(f.what)} ${esc(f.why)}</p>
          <p class="aeta">⏱ ${esc(f.effort)}${worth}</p>
        </div>
      </div>`;
    })
    .join("")}</div>`;
}

/** @param {any} artifact @returns {any[]} */
function collectFindings(artifact) {
  const all = [];
  for (const key of CATEGORY_ORDER) {
    const cat = artifact.categories[key];
    if (cat?.status === "measured") {
      for (const f of cat.findings) all.push({ ...f, category: key });
    }
  }
  const rank = { ERROR: 0, WARNING: 1, INFO: 2 };
  const r = (s) => (s in rank ? rank[s] : 3);
  all.sort((a, b) => r(a.severity) - r(b.severity) || (b.count || 0) - (a.count || 0));
  return all;
}

/** @param {any[]} findings */
function setupFindings(findings) {
  const bar = /** @type {HTMLElement} */ (main.querySelector(".filterbar"));
  const list = /** @type {HTMLElement} */ (main.querySelector(".findings"));
  const countEl = /** @type {HTMLElement} */ (main.querySelector(".findings-count"));

  const counts = { ALL: findings.length, ERROR: 0, WARNING: 0, INFO: 0 };
  for (const f of findings) {
    const sev = f.severity in counts ? f.severity : "INFO";
    counts[sev] += 1;
  }

  const filters = [
    ["ALL", `All (${counts.ALL})`],
    ["ERROR", `Errors (${counts.ERROR})`],
    ["WARNING", `Warnings (${counts.WARNING})`],
    ["INFO", `Info (${counts.INFO})`],
  ];
  bar.innerHTML = filters
    .map(
      ([key, label], i) =>
        `<button type="button" data-filter="${key}" aria-pressed="${i === 0}">${label}</button>`
    )
    .join("");

  /** @param {string} filter */
  function apply(filter) {
    for (const btn of bar.querySelectorAll("button")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.filter === filter));
    }
    const visible = filter === "ALL" ? findings : findings.filter((f) => f.severity === filter);
    countEl.textContent =
      visible.length === 1 ? "Showing 1 finding." : `Showing ${visible.length} findings.`;
    list.innerHTML = visible
      .map(
        (f) => `<li class="finding">
          <div class="finding-head">
            <span class="sev sev-${String(f.severity || "info").toLowerCase()}">${SEVERITY_LABELS[f.severity] || esc(f.severity || "Info")}</span>
            <span class="count">${f.count === 1 ? "1 instance" : `${f.count} instances`}</span>
          </div>
          <p class="what">${esc(f.what)}</p>
          <p class="why">${esc(f.why)}</p>
          <p class="how"><strong>Fix:</strong> ${esc(f.fix)} <em>(${esc(f.effort)})</em></p>
          <p class="code">Validator rule: ${esc(f.code)} ·
            <a class="fix-guide" href="${esc(FIX_DOCS_BASE + encodeURIComponent(f.code))}.md"
               target="_blank" rel="noopener">Read the fix guide<span aria-hidden="true"> ↗</span><span class="visually-hidden"> (opens on GitHub)</span></a>${ruleRefLink(f.code)}</p>
        </li>`
      )
      .join("");
    if (!visible.length) {
      list.innerHTML = `<li class="finding"><p class="what">No findings at this severity.</p></li>`;
    }
  }

  bar.addEventListener("click", (event) => {
    const btn = /** @type {HTMLElement} */ (event.target).closest("button");
    if (btn?.dataset.filter) apply(btn.dataset.filter);
  });
  apply("ALL");
}

/** A state's own GTFS guideline or program, shown to agencies in that state.
 *  `kind` keeps it honest: "guideline" is a quality rubric the score maps to
 *  (California only); "program" is a state support resource. Mirror of
 *  STATE_STANDARDS in render_site.py. */
const STATE_STANDARDS = {
  California: { kind: "guideline", name: "California Transit Data Guidelines",
    url: "https://dot.ca.gov/cal-itp/california-transit-data-guidelines",
    note: "Caltrans' published quality guidelines and compliance checklist." },
  Colorado: { kind: "program", name: "CDOT Digital Transit Mobility",
    url: "https://www.codot.gov/programs/innovativemobility/mobility-technology/digital-transit-mobility",
    note: "Colorado's program coordinating GTFS data across transit providers." },
  Michigan: { kind: "program", name: "Michigan Public Transit Open Data Program",
    url: "https://miruralmobility.org/",
    note: "MDOT's program helping agencies produce and maintain GTFS and GTFS-Flex." },
  Minnesota: { kind: "program", name: "MnDOT Transit",
    url: "https://www.dot.state.mn.us/transit/",
    note: "Minnesota's statewide transit program and data resources." },
  Oregon: { kind: "program", name: "Oregon ODOT Public Transportation",
    url: "https://www.oregon.gov/odot/rptd/pages/index.aspx",
    note: "ODOT's Public Transportation Division, which supports statewide GTFS." },
  Washington: { kind: "program", name: "WSDOT Transportation Data",
    url: "https://wsdot.wa.gov/about/transportation-data",
    note: "WSDOT builds and publishes GTFS for Washington transit agencies." },
};

// Status labels for the NTD / conformance blocks. The text label carries the
// meaning; the color class only reinforces it, never the sole cue. Mirrors the
// static page (pipeline/src/scorecard_pipeline/render_site.py) so the SPA card
// and the prerendered /agency/<id>/ page read the same.
const NTD_LABELS = { ready: "Ready", at_risk: "Needs attention", not_ready: "Not ready" };
const NTD_PILLAR_NAMES = { published: "Published", valid: "Valid", current: "Current" };
const NTD_ALIGN_LABELS = {
  aligned: "Aligned",
  mismatch: "Needs attention",
  missing: "Needs attention",
  unknown: "Not checked yet",
};
const NTD_ALIGN_CLASSES = {
  aligned: "ntd-ready",
  mismatch: "ntd-at_risk",
  missing: "ntd-at_risk",
  unknown: "ntd-unknown",
};
const CONFORMANCE_NAMES = { valid: "Valid", current: "Current", accessible: "Accessible" };

/** The NTD ID alignment line: whether the feed's agency_id matches the agency's
 *  NTD ID (FTA RY2025/26). Reads the stored `ntd_id_alignment` block; "" if the
 *  artifact predates the check. Framed as a fix, carries no score.
 *  @param {any} artifact */
function ntdAlignmentRow(artifact) {
  const align = artifact.ntd_id_alignment;
  if (!align) return "";
  const status = String(align.status || "unknown");
  const label = NTD_ALIGN_LABELS[status] || status;
  const cls = NTD_ALIGN_CLASSES[status] || "ntd-unknown";
  let body = esc(String(align.detail || ""));
  if (align.fix) body += " " + esc(String(align.fix));
  return `<dl class="standards-list">
      <dt>agency_id matches your NTD ID <span class="ntd-status ${cls}">${esc(label)}</span></dt>
      <dd>${body}</dd></dl>`;
}

/** NTD certification readiness: three pillars (published, valid, current) plus
 *  the agency_id alignment line. Reads the precomputed `ntd_readiness`; renders
 *  whatever is present and is "" only when both are absent (older artifacts).
 *  @param {any} artifact */
function ntdSection(artifact) {
  const r = artifact.ntd_readiness;
  const alignRow = ntdAlignmentRow(artifact);
  if (!r && !alignRow) return "";
  let pillars = "";
  let summary = "";
  let head = '<abbr title="National Transit Database">NTD</abbr> certification readiness';
  if (r) {
    const headStatus = String(r.status || "unknown");
    const overall = NTD_LABELS[headStatus] || headStatus;
    head = `<abbr title="National Transit Database">NTD</abbr> certification readiness <span class="ntd-status ntd-${esc(headStatus)}">${esc(overall)}</span>`;
    summary = String(r.summary || "");
    pillars = (r.pillars || [])
      .map((p) => {
        const label = NTD_LABELS[p.status] || p.status;
        const name = NTD_PILLAR_NAMES[p.key] || p.key;
        return `<dt>${esc(name)} <span class="ntd-status ntd-${esc(String(p.status))}">${esc(label)}</span></dt><dd>${esc(String(p.detail || ""))}</dd>`;
      })
      .join("");
  }
  return `<section aria-labelledby="ntd-h" class="feed-details reveal">
    <h2 class="section-title" id="ntd-h">${head}</h2>
    ${summary ? `<p class="page-lede">${esc(summary)}</p>` : ""}
    ${pillars ? `<dl class="standards-list">${pillars}</dl>` : ""}
    ${alignRow}
    <p class="plain-summary"><strong>In plain words:</strong> if you report to the federal transit
      database, you have to publish a working, up-to-date feed and confirm it once a year. This box
      is a heads-up on whether yours looks ready; it is not the official sign-off.</p>
    <p class="fineprint">A readiness signal mapping this feed to the
      <a href="https://www.transit.dot.gov/ntd"><abbr title="Federal Transit Administration">FTA</abbr> National Transit Database</a> GTFS
      requirement (Report Year 2023 onward: a public, valid, current feed, certified
      annually on the <abbr title="FTA NTD certification form D-10">D-10</abbr>). From <a href="https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026">report
      year 2025</a> (2026 for reduced, rural, and tribal reporters), FTA also asks that
      agency_id equal your NTD ID. Not an official determination; your certification is
      the official check.</p>
  </section>`;
}

/** Conformance mark: a pass/not-yet credential over the checks the grade uses.
 *  Reads the stored `conformance` block; "" if absent. Criteria are labelled in
 *  text, never by color alone.
 *  @param {any} artifact @param {string} agencyId @param {string} agencyName */
function conformanceSection(artifact, agencyId, agencyName) {
  const mark = artifact.conformance;
  if (!mark) return "";
  const rows = (mark.criteria || [])
    .map((c) => {
      const name = CONFORMANCE_NAMES[c.key] || c.key;
      const status = c.met ? "ntd-ready" : "ntd-not_ready";
      const label = c.met ? "Met" : "Not yet";
      return `<dt>${esc(name)} <span class="ntd-status ${status}">${label}</span></dt><dd>${esc(String(c.detail || ""))}</dd>`;
    })
    .join("");
  const headStatus = mark.awarded ? "ntd-ready" : "ntd-not_ready";
  const headLabel = mark.awarded ? "Awarded" : "Not yet";
  const seal = mark.awarded
    ? `<p><img src="${esc(safeUrl(`/data/artifacts/${agencyId}/mark.svg`))}" alt="GTFS conformance mark for ${esc(agencyName)}"></p>`
    : "";
  return `<section aria-labelledby="mark-h" class="feed-details reveal">
    <h2 class="section-title" id="mark-h">Conformance mark <span class="ntd-status ${headStatus}">${headLabel}</span></h2>
    ${mark.summary ? `<p class="page-lede">${esc(String(mark.summary))}</p>` : ""}
    ${seal}
    <dl class="standards-list">${rows}</dl>
    <p class="plain-summary"><strong>In plain words:</strong> earn this mark when your feed passes
      validation, has not expired, and says whether nearly every stop and trip is wheelchair
      accessible.</p>
    <p class="fineprint">A pass credential for a feed that is valid, current, and states
      wheelchair access on nearly every stop and trip. Accessibility here measures what the
      feed publishes, not whether a stop is physically usable.
      <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/conformance.md">How the conformance mark works.</a></p>
  </section>`;
}

/** Beyond-the-grade opportunities (fares, on-demand service, deeper accessibility)
 *  attached at score time. Reads the stored `recommendations`; "" when empty.
 *  @param {any} artifact */
function recommendationsSection(artifact) {
  const recs = artifact.recommendations || [];
  if (!recs.length) return "";
  const items = recs
    .map(
      (rec) =>
        `<li class="rec"><p class="rec-what">${esc(String(rec.what || ""))}</p>` +
        `<p class="rec-fix"><strong>Consider:</strong> ${esc(String(rec.fix || ""))}</p></li>`,
    )
    .join("");
  return `<section aria-labelledby="recs-h" class="reveal">
    <h2 class="section-title" id="recs-h">Beyond the grade</h2>
    <p class="page-lede">Opportunities that do not change your grade today: fare detail,
      on-demand service, and deeper accessibility data.</p>
    <ul class="recs">${items}</ul>
  </section>`;
}

/** The safe mechanical subset of fixes, offered as a corrected feed. Renders
 *  only the precomputed artifact.autofix block: each fix label and count with an
 *  example, plus a download button when a download_url was attached at score
 *  time, otherwise a one-line CLI hint. Empty when no autofix block is present
 *  or it found nothing to change. */
function autofixSection(artifact) {
  const autofix = artifact.autofix;
  if (!autofix || !autofix.available) return "";
  const items = (autofix.fixes || [])
    .map((fix) => {
      const count = Number(fix.count) || 0;
      const noun = count === 1 ? "change" : "changes";
      const examples = fix.examples || [];
      const example = examples.length
        ? `<p class="autofix-example">For example: ${esc(String(examples[0]))}</p>`
        : "";
      return (
        `<li class="autofix-item"><p class="autofix-label">${esc(String(fix.label || ""))} ` +
        `<span class="count">${count} ${noun}</span></p>${example}</li>`
      );
    })
    .join("");
  const action = autofix.download_url
    ? `<p class="autofix-action"><a class="download-btn" href="${esc(safeUrl(autofix.download_url))}" download>Download corrected feed</a></p>`
    : `<p class="autofix-cli">Run it yourself on your own copy of the feed: ` +
      `<code>scorecard autofix &lt;feed.zip&gt; --out corrected.zip</code></p>`;
  return `<section aria-labelledby="autofix-h" class="reveal">
    <h2 class="section-title" id="autofix-h">Some fixes we can make for you</h2>
    <p class="page-lede">These are the safe mechanical fixes, applied to a copy of your feed.
      They change only what is certain and leave everything else untouched. Review the diff
      before you publish.</p>
    <ul class="autofix-list">${items}</ul>${action}
  </section>`;
}

/** How each category relates to the standards an agency is held to: the FTA NTD
 *  GTFS requirement, the MobilityData grading scheme, the Google Transit gate,
 *  plus the agency's state guideline when its state has one. docs/crosswalk.md. */
function standardsSection(state) {
  const CW = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/crosswalk.md";
  const NTD = "https://www.transit.dot.gov/ntd";
  const MD = "https://github.com/MobilityData/gtfs-grading-scheme";
  const rows = [
    ["Correctness", "GTFS Schedule best practices via the MobilityData validator. MobilityData grading: stop locations, route names and colors."],
    ["Freshness", "The FTA National Transit Database expectation of a valid, current feed. An expired calendar drops the agency from Google Maps."],
    ["Rider experience", "GTFS Best Practices for rider-facing fields. MobilityData grading: stop names and headsigns."],
    ["Realtime quality", "GTFS-Realtime best practices: a stable URL, high uptime, and frequent updates."],
  ]
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`)
    .join("");
  const std = STATE_STANDARDS[state];
  const lead = std && std.kind === "guideline"
    ? `In ${esc(state)}, the published guideline is `
    : "Your state runs a transit-data program that can help: ";
  const stateHtml = std
    ? `<p class="page-lede">${lead}<a href="${esc(std.url)}">${esc(std.name)}</a>. ${esc(std.note)}</p>`
    : "";
  return `<section aria-labelledby="standards-h" class="feed-details reveal">
    <h2 class="section-title" id="standards-h">How this maps to the standards</h2>
    <p class="page-lede">A data-quality lens, not a compliance determination. Each category
    relates to the <a href="${NTD}"><abbr title="Federal Transit Administration">FTA</abbr> National Transit Database</a> GTFS requirement, the
    <a href="${MD}">MobilityData grading scheme</a>, and the Google Transit gate.
    Read the full standards crosswalk: <a href="${CW}">standards crosswalk (docs/crosswalk.md)</a>.</p>
    ${stateHtml}
    <dl>${rows}</dl>
  </section>`;
}

/** @param {string} agencyId */
function badgeSection(agencyId) {
  // Embed the canonical public domain, not the viewer's origin or the CDN, so a
  // badge an agency copies always points at gtfsscorecard.org and its crawlable
  // scorecard page.
  const SITE = "https://gtfsscorecard.org";
  const badgeUrl = `${SITE}/data/artifacts/${agencyId}/badge.svg`;
  const pageUrl = `${SITE}/agency/${agencyId}/`;
  const markdown = `[![GTFS quality](${badgeUrl})](${pageUrl})`;
  return `<section aria-labelledby="badge-h" class="badge-section reveal">
    <h2 class="section-title" id="badge-h">Show your grade</h2>
    <p class="page-lede">Put the current grade on your own developer page. The badge
    updates automatically each day and links back to this scorecard.</p>
    <p><img src="${esc(safeUrl(badgeUrl))}" alt="Current GTFS quality grade badge"></p>
    <label class="badge-embed-label" for="badge-embed">Markdown to embed</label>
    <input id="badge-embed" class="badge-embed" type="text" readonly
      value="${esc(markdown)}">
  </section>`;
}

/* ---------------- router ---------------- */

/** @param {string} message */
function renderError(message) {
  main.innerHTML = `<div class="error-box" role="alert">
    <p><strong>Something went wrong loading the scorecard.</strong></p>
    <p>${esc(message)}</p>
    <p><a href="#/">Back to all agencies</a></p>
  </div>`;
}

/** @param {string} agencyId */
function renderNotFound(agencyId) {
  document.title = "Agency not found — GTFS Scorecard";
  main.innerHTML = `<div class="error-box" role="alert">
    <p><strong>No scorecard for “${esc(agencyId)}”.</strong></p>
    <p>That agency isn't tracked yet, or the link is out of date.</p>
    <p><a href="#/">Back to all agencies</a></p>
  </div>`;
}

/** Two agencies side by side as an accessible comparison table, shareable via
 *  #/compare?a=<id>&b=<id>. No new dependency: a data table, not a map, so it
 *  works with a keyboard and a screen reader out of the box. When either id is
 *  missing or unknown, a picker chooses two agencies and navigates to the URL.
 *  @param {string|null} aId @param {string|null} bId */
async function renderCompare(aId, bId) {
  document.title = "Compare agencies — GTFS Scorecard";
  const dir = await loadDirectory();
  const agencies = (dir.agencies || []).slice().sort((x, y) => x.name.localeCompare(y.name));
  const byId = new Map(agencies.map((a) => [a.id, a]));
  const valid = (id) => !!id && byId.has(id);

  if (!valid(aId) || !valid(bId)) {
    const options = (selected) =>
      agencies
        .map((a) => `<option value="${esc(a.id)}"${a.id === selected ? " selected" : ""}>${esc(a.name)}</option>`)
        .join("");
    main.innerHTML = `
      <a class="backlink" href="#/">&larr; All agencies</a>
      <h1 class="page-title">Compare two agencies</h1>
      <p class="page-lede">Put two scorecards side by side to benchmark one feed against another. The result has a shareable link.</p>
      <form id="compare-pick" class="compare-pick">
        <p><label for="cmp-a">First agency</label>
          <select id="cmp-a" name="a">${options(aId)}</select></p>
        <p><label for="cmp-b">Second agency</label>
          <select id="cmp-b" name="b">${options(bId)}</select></p>
        <p><button type="submit" class="compare-go">Compare</button></p>
      </form>`;
    const form = /** @type {HTMLFormElement} */ (main.querySelector("#compare-pick"));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const a = /** @type {HTMLSelectElement} */ (form.querySelector("#cmp-a")).value;
      const b = /** @type {HTMLSelectElement} */ (form.querySelector("#cmp-b")).value;
      location.hash = `#/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`;
    });
    return;
  }

  main.innerHTML = `<p class="loading" role="status">Loading…</p>`;
  const [aArt, bArt] = await Promise.all([
    fetchJson(`${aId}/latest.json`),
    fetchJson(`${bId}/latest.json`),
  ]);

  const gradeCell = (art) => {
    const o = art.overall || {};
    return `<span class="grade-chip ${gradeClass(o.grade)}">${esc(o.grade)}<span class="visually-hidden"> grade</span></span> ${esc(String(o.score ?? "—"))}<span class="outof"> / 100</span>`;
  };
  const catCell = (art, key) => {
    const c = (art.categories || {})[key];
    if (!c || c.status !== "measured") return `<span class="cmp-na">Not yet measured</span>`;
    const s = Number(c.score);
    const w = Math.max(2, Math.min(100, s));
    const band = gradeBand(s);
    return `<div class="pbar cmp-bar" role="meter" aria-valuenow="${s}" aria-valuemin="0" aria-valuemax="100" aria-label="${esc(CATEGORY_LABELS[key])} score for ${esc(art.agency.name)}"><span style="width:${w}%;background:var(--grade-${band})"></span></div><span class="cmp-num">${s} / 100</span>`;
  };
  const fixesCell = (art) => {
    const fixes = (art.top_fixes || []).slice(0, 3);
    if (!fixes.length) return `<span class="cmp-na">No priority fixes</span>`;
    return `<ol class="cmp-fixes">${fixes.map((f) => `<li>${esc(f.fix)}</li>`).join("")}</ol>`;
  };

  const aName = aArt.agency.name;
  const bName = bArt.agency.name;
  const catRows = CATEGORY_ORDER.map(
    (key) =>
      `<tr><th scope="row">${esc(CATEGORY_LABELS[key])}</th><td>${catCell(aArt, key)}</td><td>${catCell(bArt, key)}</td></tr>`
  ).join("");

  main.innerHTML = `
    <a class="backlink" href="#/compare">&larr; Choose different agencies</a>
    <h1 class="page-title">${esc(aName)} vs ${esc(bName)}</h1>
    <p class="page-lede">Two scorecards side by side. Each column links to its full page.</p>
    <div class="table-wrap"><table class="compare-table">
      <caption class="visually-hidden">Data-quality comparison of ${esc(aName)} and ${esc(bName)}</caption>
      <thead><tr>
        <td></td>
        <th scope="col"><a href="#/agency/${esc(aId)}">${esc(aName)}</a></th>
        <th scope="col"><a href="#/agency/${esc(bId)}">${esc(bName)}</a></th>
      </tr></thead>
      <tbody>
        <tr><th scope="row">Overall grade</th><td>${gradeCell(aArt)}</td><td>${gradeCell(bArt)}</td></tr>
        ${catRows}
        <tr><th scope="row">Top things to fix</th><td>${fixesCell(aArt)}</td><td>${fixesCell(bArt)}</td></tr>
      </tbody>
    </table></div>`;
}

async function route() {
  const hash = location.hash || "#/";
  main.innerHTML = `<p class="loading" role="status">Loading…</p>`;
  try {
    if (hash === "#/programs") {
      renderPrograms(await fetchJson("rollups/index.json"));
      main.focus({ preventScroll: true });
      return;
    }
    const program = hash.match(/^#\/program\/([a-z0-9_-]+)$/);
    if (program) {
      renderProgram(await fetchJson(`rollups/${program[1]}.json`));
      main.focus({ preventScroll: true });
      return;
    }
    if (hash === "#/cohort" || hash.startsWith("#/cohort?")) {
      const index = await fetchJson("index.json");
      const qi = hash.indexOf("?");
      const params = new URLSearchParams(qi >= 0 ? hash.slice(qi + 1) : "");
      const idsParam = params.get("ids");
      await renderCohort(index, idsParam ? idsParam.split(",").filter(Boolean) : null);
      main.focus({ preventScroll: true });
      return;
    }
    if (hash === "#/compare" || hash.startsWith("#/compare?")) {
      const qi = hash.indexOf("?");
      const params = new URLSearchParams(qi >= 0 ? hash.slice(qi + 1) : "");
      await renderCompare(params.get("a"), params.get("b"));
      main.focus({ preventScroll: true });
      return;
    }
    const match = hash.match(/^#\/agency\/([a-z0-9_-]+)$/);
    if (match) {
      const index = await fetchJson("index.json");
      if (index.agencies[match[1]]) {
        const artifact = await fetchJson(`${match[1]}/latest.json`);
        const dirRecord = await directoryRecord(match[1]);
        renderScorecard(artifact, index.agencies[match[1]].history, dirRecord);
      } else {
        renderNotFound(match[1]);
      }
    } else {
      // Home: the slim directory drives the national overview, so the front door
      // never loads the full per-agency history index.
      renderOverview(await loadDirectory());
    }
  } catch (err) {
    renderError(err instanceof Error ? err.message : String(err));
  }
  main.focus({ preventScroll: true });
}

window.addEventListener("hashchange", route);
route();
