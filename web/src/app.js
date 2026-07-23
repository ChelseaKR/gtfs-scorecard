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
 * category and severity labels, the fix-guide base URL, and the
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
  JURISDICTION_GUIDANCE,
  SERVICE_HORIZON_REVIEW_YEARS,
  SUPPORT_RESOURCES,
  UNIVERSAL_GUIDANCE,
  US_NTD_GUIDANCE,
  US_STATE_SUBDIVISION_CODES,
  VALIDATOR_RULES_PAGE,
} from "./generated/constants.js";
import { compareText, formatDate, formatLanguageName, formatNumber } from "./locale.js";
import { initStrings, t } from "./i18n.js";

/** Candidate locations for published artifacts. A configured CDN base
 *  (web/src/config.js) is tried first, then the deployed-site and repo
 *  layouts, so the same app works on GitHub Pages, behind CloudFront, or
 *  straight from the repository. */
const DATA_BASES = [
  /** @type {any} */ (window).SCORECARD_DATA_BASE,
  "data/artifacts",
  "../data/artifacts",
].filter(Boolean);

/** Product questions that can be answered from existing, ungraded GTFS
 *  capability evidence. Presets only compose the public filters; they do not
 *  certify implementation quality or physical accessibility.
 *  @type {Record<string, {labelKey: string, features: string[], mode: string,
 *    stops: string, trips: string, ferryBikes?: string}>} */
const FEATURE_USE_CASES = {
  "accessibility-metadata": {
    labelKey: "feature_use_case_accessibility",
    features: ["accessibility"],
    mode: "",
    stops: "95",
    trips: "95",
  },
  "multilingual-rider-info": {
    labelKey: "feature_use_case_multilingual",
    features: ["translations"],
    mode: "",
    stops: "",
    trips: "",
  },
  "fare-aware-planning": {
    labelKey: "feature_use_case_fares",
    features: ["fares"],
    mode: "",
    stops: "",
    trips: "",
  },
  "modern-fare-model-integration": {
    labelKey: "feature_use_case_fares_v2",
    features: ["fares_v2"],
    mode: "",
    stops: "",
    trips: "",
  },
  "flexible-service-discovery": {
    labelKey: "feature_use_case_flexible_service",
    features: ["flex"],
    mode: "",
    stops: "",
    trips: "",
  },
  "contactless-payment-metadata": {
    labelKey: "feature_use_case_contactless",
    features: ["cemv"],
    mode: "",
    stops: "",
    trips: "",
  },
  "step-free-stations": {
    labelKey: "feature_use_case_step_free",
    features: ["pathways", "step_free"],
    mode: "",
    stops: "",
    trips: "",
  },
  "ferry-service-discovery": {
    labelKey: "feature_use_case_ferry",
    features: [],
    mode: "ferry",
    stops: "",
    trips: "",
  },
  "bicycle-aware-ferry-planning": {
    labelKey: "feature_use_case_ferry_bicycle",
    features: [],
    mode: "ferry",
    stops: "",
    trips: "",
    ferryBikes: "95",
  },
};

/** Reviewed localized label for a feature-finder preset. @param {string} key */
function featureUseCaseLabel(key) {
  const labelKey = FEATURE_USE_CASES[key]?.labelKey;
  return labelKey ? t(labelKey) : "";
}

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
            <a class="rule-ref" href="${escAttr(url)}" target="_blank" rel="noopener">See the GTFS Validator rule<span aria-hidden="true"> ↗</span><span class="visually-hidden"> (opens on gtfs-validator.mobilitydata.org)</span></a>`;
}

const main = /** @type {HTMLElement} */ (document.getElementById("main"));

/** Artifact severities cross a public JSON boundary. Keep both the label and
 *  CSS token on a closed allowlist; an unknown value is informational rather
 *  than becoming markup. @param {unknown} value */
function findingSeverity(value) {
  switch (String(value || "").toUpperCase()) {
    case "ERROR":
      return { key: "ERROR", className: "sev-error", label: SEVERITY_LABELS.ERROR };
    case "WARNING":
      return { key: "WARNING", className: "sev-warning", label: SEVERITY_LABELS.WARNING };
    default:
      return { key: "INFO", className: "sev-info", label: SEVERITY_LABELS.INFO };
  }
}

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
  throw new Error(t("app_fetch_error", { path, detail }));
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

/** Encode untrusted text for a quoted HTML attribute. `esc` deliberately
 *  targets element text and therefore leaves quotes alone. @param {string} text */
function escAttr(text) {
  return esc(text).replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

/** @param {string} grade @returns {string} */
function gradeClass(grade) {
  const normalized = String(grade || "F").toUpperCase();
  return `grade-${["A", "B", "C", "D", "F"].includes(normalized) ? normalized.toLowerCase() : "f"}`;
}

function routeRule() {
  const dots = '<span class="stopdot"></span>';
  return `<div class="route-rule" role="presentation">
    <span class="stopdot"></span><span class="seg"></span>${dots}<span class="seg"></span>${dots}<span class="seg"></span><span class="stopdot"></span>
  </div>`;
}

/** Human-readable producer contract behind a cross-feed aggregate. @param {any} comparison */
function comparisonContractText(comparison) {
  const contract = comparison || {};
  const categories = Array.isArray(contract.required_measured_categories)
    ? contract.required_measured_categories.map(
        (category) => CATEGORY_LABELS[category] || String(category),
      )
    : [];
  const measured = categories.length
    ? categories.map((category) => esc(category)).join(", ")
    : "one shared measured-category set";
  return (
    `rubric ${esc(String(contract.required_rubric_version || "current"))}, ` +
    `scoring profile ${esc(String(contract.required_scoring_profile_id || "current"))}, ` +
    `MobilityData gtfs-validator ${esc(String(contract.required_validator_version || "current"))}, ` +
    `reader archive profile ${esc(String(contract.required_reader_archive_profile || "raw-v1"))}, ` +
    `and measured categories ${measured}`
  );
}

/** Resolve the versioned reader view without treating an explicit unknown as legacy raw.
 *  @param {any} record @returns {string} */
function readerArchiveProfile(record) {
  const value = record && typeof record === "object" ? record : {};
  const fetchBlock = value.fetch && typeof value.fetch === "object" ? value.fetch : {};
  const direct = Object.prototype.hasOwnProperty.call(value, "reader_archive_profile");
  const embedded = Object.prototype.hasOwnProperty.call(fetchBlock, "reader_archive_profile");
  const directProfile = value.reader_archive_profile;
  const embeddedProfile = fetchBlock.reader_archive_profile;
  const valid = (profile) => profile === "raw-v1" || profile === "flat-single-root-v1";
  if ((direct && !valid(directProfile)) || (embedded && !valid(embeddedProfile))) return "";
  if (direct && embedded && directProfile !== embeddedProfile) return "";

  const normalizedPresent = Object.prototype.hasOwnProperty.call(
    fetchBlock,
    "reader_archive_normalized",
  );
  const normalized = fetchBlock.reader_archive_normalized;
  if (normalizedPresent && typeof normalized !== "boolean") return "";
  const implied = normalized === true ? "flat-single-root-v1" : "raw-v1";
  if (direct || embedded) {
    const profile = direct ? directProfile : embeddedProfile;
    return normalizedPresent && profile !== implied ? "" : profile;
  }
  return implied;
}

/* ---------------- national overview + directory ---------------- */

/** The directory document, fetched once and reused for the overview and for
 *  per-scorecard location context. @type {Promise<any> | null} */
let directoryPromise = null;

/** @returns {Promise<any>} */
function loadDirectory() {
  if (!directoryPromise) {
    directoryPromise = fetchJson("directory.json").then((directory) => {
      const names = Object.fromEntries(
        (directory.summary?.countries || []).map((country) => [
          country.country_code || "",
          country.country_name || country.country_code || "",
        ])
      );
      directory.agencies = (directory.agencies || []).map((agency) => ({
        ...agency,
        country_name: names[agency.country || ""] || agency.country || "",
      }));
      return directory;
    });
  }
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
const UNLOCATED_SUBDIVISION = "UNLOCATED";

/** Portable practitioner-facing location. U.S. records retain their familiar
 * state-only label; other records include the country so an ambiguous
 * subdivision name never stands alone. @param {any} row @returns {string} */
function placeLabel(row) {
  const country = String(row?.country || "US").toUpperCase();
  const countryLabel = String(row?.countryName || row?.country_name || country);
  const subdivision = String(
    row?.subdivisionName || row?.subdivision_name || (country === "US" ? row?.state || "" : "")
  );
  if (country === "US") return subdivision || row?.state || countryLabel;
  return subdivision ? `${subdivision}, ${countryLabel}` : countryLabel || row?.state || "";
}

/** A finite public-JSON number, or null without coercing null to zero.
 * @param {unknown} value @returns {number|null} */
function optionalNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** A public-JSON boolean, or null when the producer did not measure it.
 * @param {unknown} value @returns {boolean|null} */
function optionalBoolean(value) {
  return typeof value === "boolean" ? value : null;
}

/** Clean string-array values at the public JSON boundary.
 * @param {unknown} value @returns {string[]} */
function stringArray(value) {
  return Array.isArray(value)
    ? [
        ...new Set(
          value
            .filter((item) => typeof item === "string" && item.trim())
            .map((item) => item.trim())
        ),
      ]
    : [];
}

const MODE_LABELS = {
  tram: "Tram / light rail",
  subway: "Subway / metro",
  rail: "Rail",
  bus: "Bus",
  ferry: "Ferry",
  cable_tram: "Cable tram",
  aerial_lift: "Aerial lift",
  funicular: "Funicular",
  trolleybus: "Trolleybus",
  monorail: "Monorail",
  other: "Other / unclassified",
};

/** Public mode key to a stable rider-facing label. @param {string} value */
function formatModeName(value) {
  return MODE_LABELS[value] || value.replaceAll("_", " ");
}

/** Keep the persistent app-shell navigation aligned with the current hash view.
 * @param {boolean} featureMode */
function setAppNav(featureMode) {
  const featureNav = /** @type {HTMLAnchorElement | null} */ (
    document.querySelector('.nav-stop[href="/app/#/?view=features"]')
  );
  const agencyNav = /** @type {HTMLAnchorElement | null} */ (
    document.querySelector('.nav-stop[href="/agencies/"]')
  );
  if (featureMode) {
    agencyNav?.removeAttribute("aria-current");
    featureNav?.setAttribute("aria-current", "page");
  } else {
    featureNav?.removeAttribute("aria-current");
    agencyNav?.setAttribute("aria-current", "page");
  }
}

/** RFC 4180-safe CSV cell. Null represents unknown and stays blank.
 * @param {unknown} value @returns {string} */
function csvCell(value) {
  if (value === null || value === undefined) return "";
  const raw = String(value);
  // Quoting does not stop spreadsheet formula execution. Treat public names,
  // ids, and URLs as text when a spreadsheet would parse their first byte.
  const text = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${text.replaceAll('"', '""')}"`;
}

/** The exact consumer-facing rows behind the current shortlist. Repeating the
 *  export context on each row keeps the file rectangular and machine-readable.
 *  @param {Array<any>} rows
 *  @param {{useCase: string, coverageScope: string, coverageDenominator: number,
 *    matchingRecords: number, filterUrl: string}} context
 *  @returns {string} */
function featureCsv(rows, context) {
  const columns = [
    ["shortlist_use_case", () => context.useCase],
    ["coverage_scope", () => context.coverageScope],
    ["coverage_denominator", () => context.coverageDenominator],
    ["matching_record_count", () => context.matchingRecords],
    ["filter_url", () => context.filterUrl],
    ["feed_id", (row) => row.id],
    ["feed_name", (row) => row.name],
    ["country_code", (row) => row.country],
    ["country_name", (row) => row.countryName],
    ["subdivision_code", (row) => row.subdivision === UNLOCATED_SUBDIVISION ? "" : row.subdivision],
    ["subdivision_name", (row) => row.subdivisionName],
    ["grade", (row) => row.grade],
    ["score", (row) => row.score],
    ["comparison_eligible", (row) => row.featureComparable],
    ["capabilities_measured", (row) => row.capabilitiesMeasured],
    ["accessibility_measured", (row) => row.accessibilityMeasured],
    ["accessibility_fields", (row) => row.hasAccessibility],
    ["wheelchair_stops_pct", (row) => row.wheelchairStops],
    ["wheelchair_trips_pct", (row) => row.wheelchairTrips],
    ["accessibility_band", (row) => row.accessibilityBand],
    ["flex", (row) => row.hasFlex],
    ["fares", (row) => row.hasFares],
    ["fare_model", (row) => row.fareModel],
    ["fares_v2", (row) => row.hasFaresV2],
    ["pathways", (row) => row.hasPathways],
    ["step_free_paths", (row) => row.hasStepFree],
    ["cemv", (row) => row.hasCemv],
    ["translations_measured", (row) => row.translationsMeasured],
    ["translations", (row) => row.hasTranslations],
    ["translation_count", (row) => row.translationCount],
    ["translation_languages", (row) => row.translationLanguages.join("|")],
    ["translated_tables", (row) => row.translatedTables.join("|")],
    ["feed_language", (row) => row.feedLang],
    ["modes_measured", (row) => row.modesMeasured],
    ["primary_mode", (row) => row.primaryMode],
    ["modes", (row) => row.modes.join("|")],
    ["has_ferry", (row) => row.hasFerry],
    ["ferry_only", (row) => row.ferryOnly],
    ["ferry_profile_measured", (row) => row.ferryProfileMeasured],
    ["ferry_bikes_stated_pct", (row) => row.ferryBikesStated],
    ["ferry_bikes_allowed_pct", (row) => row.ferryBikesAllowed],
    ["scorecard_url", (row) => row.scorecardUrl],
    ["feed_url", (row) => row.feedUrl],
  ];
  const lines = [columns.map(([label]) => csvCell(label)).join(",")];
  for (const row of rows) {
    lines.push(columns.map(([, read]) => csvCell(read(row))).join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

/** Download the current client-side shortlist without sending it anywhere.
 * @param {Array<any>} rows
 * @param {{useCase: string, coverageScope: string, coverageDenominator: number,
 *   matchingRecords: number, filterUrl: string}} context */
function downloadFeatureCsv(rows, context) {
  const blob = new Blob([featureCsv(rows, context)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `gtfs-scorecard-feature-matches-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** A grade-distribution bar: one labelled segment per grade, sized
 *  by share. Decorative fill, but each segment is a labelled list item so the
 *  same information is available without color. @param {any} dist @param {number} total
 *  @param {string} [label] */
function gradeDistributionBar(dist, total, label = "Grade distribution across comparable scorecards") {
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
  return `<ul class="grade-distribution" aria-label="${escAttr(label)}">${segs}</ul>`;
}

/** Fail-closed validation for a guarded score aggregate. A stale payload must
 *  not display an old median/average beside a zero or missing comparison cohort.
 *  @param {any} payload @param {any} center */
function guardedAggregateState(payload, center) {
  const rawCount = payload?.comparison?.eligible_count;
  const count = Number.isInteger(rawCount) && rawCount > 0 ? rawCount : 0;
  const distribution = payload?.grade_distribution || {};
  const distributionTotal = ["A", "B", "C", "D", "F"].reduce((total, grade) => {
    const value = distribution[grade];
    return total + (Number.isInteger(value) && value >= 0 ? value : 0);
  }, 0);
  return {
    count,
    distribution,
    valid:
      count > 0 &&
      typeof center === "number" &&
      Number.isFinite(center) &&
      distributionTotal === count,
  };
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

/** Plain-language coverage label for one choropleth area: how many feeds it
 *  covers and how many have expired, carried in text so neither count depends
 *  on the fill color. Reads "Osaka: 3 feeds, 1 expired (33%)", or
 *  "Osaka: 3 feeds, none expired" when every feed is current. The state, world,
 *  and subdivision maps share it, so the fill shows the expired share while the
 *  label always states the raw counts the color cannot.
 *  @param {string} name @param {number} agencies @param {number} expired
 *  @returns {string} */
function coverageLabel(name, agencies, expired) {
  const noun = agencies === 1 ? "feed" : "feeds";
  if (!expired) return `${name}: ${agencies} ${noun}, none expired`;
  const pct = Math.round((expired / agencies) * 100);
  return `${name}: ${agencies} ${noun}, ${expired} expired (${pct}%)`;
}

/** Build the US choropleth SVG from the projected state paths and the per-state
 *  summary rows. States with no published feed records render faint and inert.
 *  @param {{viewBox: string, states: Record<string,string>}} mapData
 *  @param {Record<string, any>} byState @returns {string} */
function buildMapSvg(mapData, byState, subdivisionCodes = {}, portableLocations = false) {
  const paths = Object.entries(mapData.states)
    .map(([name, d]) => {
      const row = byState[name];
      if (!row || !row.agencies) {
        return `<path d="${d}" class="us-state us-empty" aria-hidden="true"></path>`;
      }
      const q = expiredQuintile(row.expired / row.agencies);
      const label = coverageLabel(name, row.agencies, row.expired);
      const subdivision = subdivisionCodes[name] || "";
      if (portableLocations && !subdivision) {
        return `<path d="${escAttr(d)}" class="us-state q${q}" aria-hidden="true"><title>${esc(label)}</title></path>`;
      }
      return `<path d="${escAttr(d)}" class="us-state q${q}" data-country="US" data-state="${escAttr(name)}"
        data-subdivision="${escAttr(subdivision)}" data-subdivision-name="${escAttr(name)}"
        tabindex="0" role="button" aria-pressed="false"
        aria-label="${escAttr(label)} — filter to this state"><title>${esc(label)}</title></path>`;
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
      aria-label="Map of the United States; each state is shaded by the share of its tracked GTFS feeds that have expired, and selecting a state filters the list below.">
      ${paths}
    </svg>
    <p class="map-legend"><span class="map-key-lab">Share of feeds expired:</span> ${legend}</p>`;
}

/** Build the world choropleth SVG from projected country paths and the summary
 *  country rows. Reuses the state-map fill classes and quintiles, so the same
 *  contrast-gated tokens and text legend carry the meaning; countries with no
 *  feed records render faint and inert.
 *  @param {{viewBox: string, countries: Record<string,string>}} mapData
 *  @param {Record<string, any>} byCountry @returns {string} */
function buildWorldMapSvg(mapData, byCountry) {
  const paths = Object.entries(mapData.countries)
    .map(([code, d]) => {
      const row = byCountry[code];
      if (!row || !row.agencies) {
        return `<path d="${d}" class="us-state us-empty" aria-hidden="true"></path>`;
      }
      const q = expiredQuintile(row.expired / row.agencies);
      const label = coverageLabel(row.country_name || code, row.agencies, row.expired);
      return `<path d="${escAttr(d)}" class="us-state q${q}" data-map-country="${escAttr(code)}"
        tabindex="0" role="button" aria-pressed="false"
        aria-label="${escAttr(label)} — filter to this country"><title>${esc(label)}</title></path>`;
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
      aria-label="World map; each country with tracked GTFS feeds is shaded by the share of those feeds that have expired, and selecting a country filters the list below.">
      ${paths}
    </svg>
    <p class="map-legend"><span class="map-key-lab">Share of feeds expired:</span> ${legend}</p>`;
}

/** The shared five-bucket legend markup for any coverage choropleth. */
function expiredLegendHtml() {
  const legend = [
    [0, "none expired"],
    [1, "under 10%"],
    [2, "10–25%"],
    [3, "25–40%"],
    [4, "40% or more"],
  ]
    .map(([q, lab]) => `<span class="map-key"><span class="map-swatch q${q}"></span>${lab}</span>`)
    .join("");
  return `<p class="map-legend"><span class="map-key-lab">Share of feeds expired:</span> ${legend}</p>`;
}

/** Build a country's subdivision choropleth, the drill-down level below the
 *  world map. Each subdivision is shaded by its expired-feed share exactly like
 *  the country and state maps, announces its counts in text, and filters the
 *  list on selection. A back control returns to the world view. Subdivisions
 *  with no tracked feeds (or with no matching geometry) render faint and inert,
 *  so a partial geometry match degrades gracefully rather than hiding the level.
 *  @param {{viewBox: string, country: string, subdivisions: Record<string,string>}} mapData
 *  @param {any[]} subRows @param {string} countryName @returns {string} */
function buildSubdivisionMapSvg(mapData, subRows, countryName) {
  const byCode = {};
  for (const row of subRows) byCode[row.subdivision_code] = row;
  let shadedAreas = 0;
  let shadedFeeds = 0;
  const paths = Object.entries(mapData.subdivisions)
    .map(([code, d]) => {
      const row = byCode[code];
      if (!row || !row.agencies) {
        return `<path d="${escAttr(d)}" class="us-state us-empty" aria-hidden="true"></path>`;
      }
      shadedAreas += 1;
      shadedFeeds += Number(row.agencies) || 0;
      const q = expiredQuintile(row.expired / row.agencies);
      const name = row.subdivision_name || code;
      const label = coverageLabel(name, row.agencies, row.expired);
      return `<path d="${escAttr(d)}" class="us-state q${q}"
        data-map-subdivision="${escAttr(code)}" data-map-country="${escAttr(mapData.country)}"
        tabindex="0" role="button" aria-pressed="false"
        aria-label="${escAttr(label)} — filter to this area"><title>${esc(label)}</title></path>`;
    })
    .join("");
  // A visible coverage readout beside the country name: how many feeds this
  // drill-down covers and across how many areas, so the depth of coverage is
  // legible without hovering a path or reading the shading. Omitted when the
  // committed geometry shades nothing, which keeps a bare "0 feeds" off-screen.
  const feedNoun = shadedFeeds === 1 ? "feed" : "feeds";
  const areaNoun = shadedAreas === 1 ? "area" : "areas";
  const coverageReadout = shadedAreas
    ? `<span class="map-drill-count">${shadedFeeds} ${feedNoun} in ${shadedAreas} ${areaNoun}</span>`
    : "";
  return `<div class="map-drill-head">
      <button type="button" class="map-back" data-map-back="1" aria-label="Back to the world map">
        <span aria-hidden="true">←</span> World</button>
      <span class="map-drill-title"><bdi>${esc(countryName)}</bdi></span>
      ${coverageReadout}
    </div>
    <svg class="us-map-svg" viewBox="${mapData.viewBox}" role="group"
      aria-label="Map of ${escAttr(countryName)}; each area is shaded by the share of its tracked GTFS feeds that have expired, and selecting an area filters the list below.">
      ${paths}
    </svg>
    ${expiredLegendHtml()}
    <p class="map-note">Color shows the share of feeds in an area that have expired. Each area lists its feed count in its label, and areas with no tracked feed stay unshaded.</p>`;
}

/** Portable country controls when the directory exposes the location contract.
 *  The selected country's subdivision controls are mounted on demand by
 *  setupOverview, after the optional U.S. map in source order. Older directory
 *  documents retain their state controls.
 *  @param {any[]} countries @param {any[]} states @returns {string} */
function locationControlsHtml(countries, states) {
  if (!(countries || []).length) {
    const rows = (states || []).filter((row) => row.state !== "Unlocated");
    const unlocated = (states || []).find((row) => row.state === "Unlocated");
    const chips = rows
      .map(
        (row) => `<button type="button" class="state-chip legacy-location"
          data-state="${escAttr(row.state)}" aria-pressed="false"><bdi>${esc(row.state)}</bdi>
          <span class="state-n">${row.agencies}</span></button>`
      )
      .join("");
    const unknown = unlocated
      ? `<button type="button" class="state-chip state-chip-muted legacy-location"
          data-state="Unlocated" aria-pressed="false">Unlocated
          <span class="state-n">${unlocated.agencies}</span></button>`
      : "";
    return `<div class="state-grid" role="group" aria-label="Filter scorecards by state">
      ${chips}${unknown}</div><div class="us-map" id="us-map" hidden></div>`;
  }

  const countryChips = countries
    .map(
      (country) => `<button type="button" class="state-chip location-country"
        data-country="${escAttr(country.country_code || "")}" aria-pressed="false">
        <bdi>${esc(country.country_name)}</bdi> <span class="state-n">${country.agencies}</span></button>`
    )
    .join("");
  return `<div class="country-grid" role="group" aria-label="Filter scorecards by country">
      ${countryChips}</div><div class="us-map" id="world-map"></div>
      <div class="us-map" id="us-map" hidden></div>
      <div class="location-groups"></div>`;
}

/** Append the evidence-gated European denominator beside the feature filters.
 *  The base coverage warning remains useful if the additive endpoint is absent
 *  during a partial deploy. Endpoint values are inserted as text nodes so an
 *  evidence record can never become markup in the application.
 *  @returns {Promise<void>} */
async function hydrateGlobalCoverageDisclosure() {
  const target = document.getElementById("global-coverage-disclosure");
  if (!target) return;
  try {
    const response = await fetch("/api/v1/global-coverage.json");
    if (!response.ok) return;
    const payload = await response.json();
    const cohort = payload?.cohort || {};
    const featureFinder = payload?.feature_finder || {};
    const criteria = Array.isArray(payload?.criteria) ? payload.criteria : [];
    const reviewed = Number(cohort.feed_record_count);
    const countries = Number(cohort.country_count);
    const finderRows = Number(featureFinder.reviewed_europe_feature_record_count);
    const recordGate = criteria.find((criterion) => criterion?.key === "reviewed_feed_records");
    const countryGate = criteria.find((criterion) => criterion?.key === "countries");
    const requiredRecords = Number(recordGate?.threshold);
    const requiredCountries = Number(countryGate?.threshold);
    if (
      ![reviewed, countries, finderRows, requiredRecords, requiredCountries].every(
        Number.isFinite
      )
    )
      return;

    const status = payload.ready === true ? "Ready" : "Not ready";
    target.append(
      document.createTextNode(
        ` European GTFS beta gate: ${formatNumber(reviewed)} reviewed feed records across ` +
          `${formatNumber(countries)} countries; ${formatNumber(finderRows)} are represented ` +
          `in this finder. Status: ${status}. The gate requires at least ` +
          `${formatNumber(requiredRecords)} reviewed records across ` +
          `${formatNumber(requiredCountries)} countries plus its published evidence checks. `
      )
    );
    const link = document.createElement("a");
    link.href = "/status/#global-coverage";
    link.textContent = "See the gate and limitations.";
    target.append(link);
  } catch {
    // Keep the generic coverage disclosure during a partial or offline deploy.
  }
}

/** @param {any} directory */
function renderOverview(directory) {
  document.title = "GTFS Scorecard — transit data quality, agency by agency";
  const s = directory.summary;
  const cohort = getCohort();
  const countries = Array.isArray(s.countries) ? s.countries : [];
  const countryNames = Object.fromEntries(
    countries.map((country) => [country.country_code || "", country.country_name])
  );
  // Normalize each agency into a flat record the filter/sort/cards reuse.
  const agencies = directory.agencies
    .map((a) => ({
      id: a.id,
      name: a.name,
      grade: String(a.grade),
      score: Number(a.score),
      state: a.state || "",
      country: a.country || "",
      countryName: countryNames[a.country || ""] || (a.country === "US" ? "United States" : a.country === "CA" ? "Canada" : ""),
      subdivision: a.subdivision_code || UNLOCATED_SUBDIVISION,
      subdivisionName: a.subdivision_name || a.state || "",
      tier: a.size_tier || "unknown",
      expiry: a.expiry_status || "unknown",
      date: a.snapshot_date,
      scorecardUrl: a.scorecard_url || new URL(`../agency/${encodeURIComponent(a.id)}/`, location.href).href,
      feedUrl: a.feed_url || "",
      featureComparable: a.comparison_eligible === true,
      capabilitiesMeasured: a.capabilities_measured === true,
      accessibilityMeasured: a.accessibility_measured === true,
      hasAccessibility: optionalBoolean(a.has_accessibility),
      wheelchairStops: optionalNumber(a.wheelchair_boarding_pct),
      wheelchairTrips: optionalNumber(a.wheelchair_accessible_pct),
      accessibilityBand: a.accessibility_band || "",
      hasFlex: optionalBoolean(a.has_flex),
      hasFares: optionalBoolean(a.has_fares),
      hasFaresV2: optionalBoolean(a.has_fares_v2),
      fareModel: a.fare_model || "",
      hasPathways: optionalBoolean(a.has_pathways),
      hasStepFree: optionalBoolean(a.has_step_free),
      hasCemv: optionalBoolean(a.has_cemv),
      translationsMeasured: a.translations_measured === true,
      hasTranslations: optionalBoolean(a.has_translations),
      translationCount: optionalNumber(a.translation_count),
      translationLanguages: stringArray(a.translation_languages),
      translatedTables: stringArray(a.translated_tables),
      feedLang: typeof a.feed_lang === "string" ? a.feed_lang : "",
      modesMeasured: a.modes_measured === true,
      primaryMode: typeof a.primary_mode === "string" ? a.primary_mode : "",
      modes: stringArray(a.modes),
      hasFerry: optionalBoolean(a.has_ferry),
      ferryOnly: optionalBoolean(a.ferry_only),
      ferryProfileMeasured: a.ferry_profile_measured === true,
      ferryBikesStated: optionalNumber(a.ferry_bikes_stated_pct),
      ferryBikesAllowed: optionalNumber(a.ferry_bikes_allowed_pct),
      search: `${a.name} ${a.id} ${a.country || ""} ${countryNames[a.country || ""] || ""} ${a.subdivision_code || ""} ${a.subdivision_name || ""} ${a.state || ""}`.toLowerCase(),
    }))
    .sort((x, y) => compareText(x.name, y.name));

  const total = agencies.length;
  const expired = s.expired || { total: 0 };
  const aggregate = guardedAggregateState(s, s.median_score);
  const comparableCount = aggregate.count;
  const capabilityMeasuredCount = agencies.filter((agency) => agency.capabilitiesMeasured).length;
  const accessibilityMeasuredCount = agencies.filter(
    (agency) => agency.accessibilityMeasured
  ).length;
  const translationMeasuredCount = agencies.filter(
    (agency) => agency.translationsMeasured
  ).length;
  const modeMeasuredCount = agencies.filter((agency) => agency.modesMeasured).length;
  const ferryProfileMeasuredCount = agencies.filter(
    (agency) => agency.ferryProfileMeasured
  ).length;
  const availableModes = [...new Set(agencies.flatMap((agency) => agency.modes))]
    .sort((left, right) => compareText(formatModeName(left), formatModeName(right)));
  const modeOptions = availableModes
    .map((mode) => `<option value="${escAttr(mode)}">${esc(formatModeName(mode))}</option>`)
    .join("");
  const translationLanguages = [...new Set(agencies.flatMap((agency) => agency.translationLanguages))]
    .map((code) => ({ code, label: formatLanguageName(code) }))
    .sort((left, right) => compareText(left.label, right.label));
  const translationLanguageOptions = translationLanguages
    .map(({ code, label }) => `<option value="${escAttr(code)}">${esc(label)}</option>`)
    .join("");
  const featureUseCaseOptions = Object.entries(FEATURE_USE_CASES)
    .map(([key]) => `<option value="${escAttr(key)}">${esc(featureUseCaseLabel(key))}</option>`)
    .join("");
  const usCoverage = countries.find((country) => country.country_code === "US");
  const usFeedCount = Number(usCoverage?.feed_records ?? usCoverage?.agencies ?? 0);
  const coverageLimit = usFeedCount > 0
    ? `Coverage is not a census of any country or region. The United States currently represents
      ${formatNumber(usFeedCount)} of ${formatNumber(total)} tracked feed records; other countries are
      small canary sets while regional source and licence review continues.`
    : `Coverage is not a census of any country or region. Country counts describe only the feeds
      currently tracked here.`;
  const comparisonContract = comparisonContractText(s.comparison);
  const comparisonNote = aggregate.valid
    ? `The median and grade distribution use ${formatNumber(comparableCount)} of
      ${formatNumber(total)} feed scorecards: canonical, active, non-duplicate records under
      one producer contract, ${comparisonContract}.`
    : `The cross-feed median and grade distribution are unavailable until the directory has
      a complete guarded summary under ${comparisonContract}. All ${formatNumber(total)}
      feed scorecards remain searchable.`;
  const stat = (num, lab) => `<div class="stat"><span class="stat-num">${num}</span><span class="stat-lab">${lab}</span></div>`;

  const facet = (key, label) =>
    `<button type="button" class="facet-chip" data-facet="${key}" aria-pressed="${key === "all"}">${label}</button>`;

  main.innerHTML = `
    <h1 class="page-title reveal">Find an agency scorecard.</h1>
    <p class="page-lede reveal">Search every published
    <dfn><abbr title="General Transit Feed Specification">GTFS</abbr></dfn> feed we track, read
    on a scheduled cadence and graded in plain language. Or browse a location to find the ones that need a call.
    The same directory exists as
    <a href="/agencies/">plain linkable pages</a>; this view adds live search and filters.</p>

    <div class="picker-controls reveal">
      <label for="agency-search" class="visually-hidden">Search scorecards by agency name, country, or subdivision</label>
      <input id="agency-search" class="agency-search" type="search" autocomplete="off"
        enterkeyhint="search" aria-controls="agency-list"
        placeholder="Find your agency among ${formatNumber(total)}…">
      <div class="picker-sort">
        <label for="agency-sort">Sort</label>
        <select id="agency-sort">
          <option value="az">Name (A–Z)</option>
          <option value="za">Name (Z–A)</option>
        </select>
      </div>
    </div>

    <section class="overview-summary reveal" aria-labelledby="ov-h">
      <h2 class="visually-hidden" id="ov-h">Directory summary</h2>
      <div class="summary-stats">
        ${stat(formatNumber(total), "scorecards available")}
        ${stat(aggregate.valid ? s.median_score : "—", "median score")}
        ${stat(s.expiring_soon || 0, "feeds expiring within 30 days")}
        ${stat(expired.total || 0, "feeds already expired")}
      </div>
      ${aggregate.valid ? gradeDistributionBar(aggregate.distribution, comparableCount) : ""}
      <p class="fineprint">${comparisonNote}</p>
    </section>
    <div class="picker-facets reveal" role="group" aria-label="Filter scorecards by grade, size, or feed status">
      ${facet("all", "All")}
      ${facet("A", "A")}${facet("B", "B")}${facet("C", "C")}${facet("D", "D")}${facet("F", "F")}
      ${facet("small", "Small")}${facet("medium", "Mid-size")}${facet("large", "Large")}
      ${facet("lapsed", "Recently lapsed")}${facet("stale", "Long expired")}
    </div>

    <section class="feature-explorer reveal" id="feature-finder" aria-labelledby="feature-filter-h" tabindex="-1">
      <div class="feature-explorer-head">
        <p class="feature-eyebrow">Consumer feature finder</p>
        <h2 class="section-title" id="feature-filter-h">Filter by what feeds publish</h2>
        <p>Select every feature your product needs. A feed must meet all selected conditions.
        Accessibility percentages describe published GTFS fields, not verified physical access.
        Location controls below narrow the same shortlist.</p>
      </div>
      <div class="feature-filter-grid">
        <fieldset class="feature-fieldset use-case-filters">
          <legend>${esc(t("feature_use_case_legend"))}</legend>
          <p class="fineprint">${esc(t("feature_use_case_hint"))}</p>
          <label for="feature-use-case">${esc(t("feature_use_case_label"))}</label>
          <select id="feature-use-case">
            <option value="">${esc(t("feature_use_case_placeholder"))}</option>
            ${featureUseCaseOptions}
          </select>
        </fieldset>
        <fieldset class="feature-fieldset required-feature-filters">
          <legend>Required features</legend>
          <p class="fineprint">Unknown measurements do not match a selected feature.</p>
          <div class="required-feature-options">
            <label><input class="feature-check" type="checkbox" value="accessibility"> Accessibility fields</label>
            <label><input class="feature-check" type="checkbox" value="fares"> Fare data</label>
            <label><input class="feature-check" type="checkbox" value="fares_v2"> Fares v2</label>
            <label><input class="feature-check" type="checkbox" value="flex"> Flexible service</label>
            <label><input class="feature-check" type="checkbox" value="pathways"> Station pathways</label>
            <label><input class="feature-check" type="checkbox" value="step_free"> Step-free paths</label>
            <label><input class="feature-check" type="checkbox" value="cemv"> Contactless fare payments</label>
            <label><input class="feature-check" type="checkbox" value="translations"> Translated rider information</label>
          </div>
        </fieldset>
        <fieldset class="feature-fieldset mode-filters">
          <legend>Service mode</legend>
          <p class="fineprint">Require at least one route of this type. Mixed-mode feeds can match more than one mode.</p>
          <label for="service-mode">Published mode</label>
          <select id="service-mode"${availableModes.length ? "" : " disabled"}>
            <option value="">Any service mode</option>
            ${modeOptions}
          </select>
        </fieldset>
        <fieldset class="feature-fieldset ferry-profile-filters">
          <legend>${esc(t("feature_ferry_bicycle_legend"))}</legend>
          <p class="fineprint">${esc(t("feature_ferry_bicycle_hint"))}</p>
          <label for="ferry-bikes-min">${esc(t("feature_ferry_bicycle_label"))}</label>
          <select id="ferry-bikes-min"${ferryProfileMeasuredCount ? "" : " disabled"}>
            <option value="">${esc(t("feature_ferry_bicycle_no_minimum"))}</option>
            <option value="any">${esc(t("feature_ferry_bicycle_any"))}</option>
            <option value="50">${esc(t("feature_ferry_bicycle_half"))}</option>
            <option value="95">${esc(t("feature_ferry_bicycle_most"))}</option>
            <option value="100">${esc(t("feature_ferry_bicycle_all"))}</option>
          </select>
        </fieldset>
        <fieldset class="feature-fieldset translation-filters">
          <legend>Translation language</legend>
          <p class="fineprint">Choose a language to require it in <code>translations.txt</code>.</p>
          <label for="translation-language">Published language</label>
          <select id="translation-language"${translationLanguages.length ? "" : " disabled"}>
            <option value="">Any translated language</option>
            ${translationLanguageOptions}
          </select>
          ${translationLanguages.length ? "" : '<p class="fineprint">Language choices will appear after current feeds have been measured.</p>'}
        </fieldset>
        <fieldset class="feature-fieldset accessibility-thresholds">
          <legend>Accessibility completeness</legend>
          <p class="fineprint">Set either minimum, or use both to require complete trip-planning data.</p>
          <label for="wheelchair-stops-min">Stops stating wheelchair access</label>
          <select id="wheelchair-stops-min">
            <option value="">No minimum</option>
            <option value="any">More than 0%</option>
            <option value="50">At least 50%</option>
            <option value="95">At least 95%</option>
            <option value="100">100%</option>
          </select>
          <label for="wheelchair-trips-min">Trips stating wheelchair access</label>
          <select id="wheelchair-trips-min">
            <option value="">No minimum</option>
            <option value="any">More than 0%</option>
            <option value="50">At least 50%</option>
            <option value="95">At least 95%</option>
            <option value="100">100%</option>
          </select>
        </fieldset>
      </div>
      <p class="fineprint">Capability flags are measured for ${formatNumber(capabilityMeasuredCount)} of
      ${formatNumber(total)} feed records; wheelchair completeness is measured for
      ${formatNumber(accessibilityMeasuredCount)}; translations are measured for
      ${formatNumber(translationMeasuredCount)}; service modes are measured for
      ${formatNumber(modeMeasuredCount)}; ferry bicycle policy is measured for
      ${formatNumber(ferryProfileMeasuredCount)}. Selecting a field excludes records where that field is unknown.
      The score-comparison cohort above is a separate contract.</p>
      <p class="coverage-limit" id="global-coverage-disclosure">${coverageLimit}</p>
    </section>

    <section class="state-browse reveal" aria-labelledby="locations-h">
      <h2 class="section-title" id="locations-h">Browse by location</h2>
      ${locationControlsHtml(countries, s.states || [])}
      <p class="region-coverage fineprint" id="region-coverage" role="status" aria-live="polite" hidden></p>
    </section>

    <section class="feature-match-board reveal" aria-labelledby="feature-match-h" data-active="false">
      <h2 class="feature-match-kicker" id="feature-match-h">Consumer shortlist</h2>
      <p class="agency-count" role="status" aria-live="polite">Choose a filter to build a shortlist.</p>
      <div class="feature-match-actions">
        <button type="button" class="feature-download-btn" id="download-feature-results" disabled>Download matching feeds (CSV)</button>
        <button type="button" class="feature-clear-btn" id="clear-feature-results" disabled>Clear shortlist</button>
        <a href="/api/v1/features.json">Open the feature API</a>
      </div>
    </section>
    <ul class="agency-list" id="agency-list"></ul>
    <p class="results-hint" id="results-hint">Search by name, select a feature or completeness
      threshold, pick a grade or size, or choose a location above to list scorecards.</p>
    <p class="no-match" hidden>No scorecards match.
      <button type="button" class="linklike" id="clear-search">Clear filters</button></p>
    <div class="show-more-wrap" hidden><button type="button" class="show-more" id="show-more">Show more</button></div>

    <p class="picker-aside reveal"><a href="#/cohort" id="my-agencies">My agencies${cohort.size ? ` (${cohort.size})` : ""}</a> &nbsp;·&nbsp;
    <a href="#/compare">Compare two agencies</a> &nbsp;·&nbsp;
    <a href="/how-to-read/">New to this? How to read a scorecard</a> &nbsp;·&nbsp;
    <a href="/submit.html">Add your agency</a> &nbsp;·&nbsp;
    <a href="/subscribe.html">Get feed-health alerts</a> &nbsp;·&nbsp;
    <a href="#/programs">Supporting a group of agencies? See the program rollup view.</a></p>`;

  setupOverview(agencies, total, s);
  void hydrateGlobalCoverageDisclosure();
}

/** Wire the directory: search, grade/size/expiry facet, portable location
 *  selection (controls and the US choropleth), and sort, composed together. The list renders only when
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
  const featureChecks = /** @type {HTMLInputElement[]} */ (
    Array.from(main.querySelectorAll(".feature-check"))
  );
  const stopsMin = /** @type {HTMLSelectElement} */ (
    main.querySelector("#wheelchair-stops-min")
  );
  const tripsMin = /** @type {HTMLSelectElement} */ (
    main.querySelector("#wheelchair-trips-min")
  );
  const ferryBikesMin = /** @type {HTMLSelectElement} */ (
    main.querySelector("#ferry-bikes-min")
  );
  const translationLanguage = /** @type {HTMLSelectElement} */ (
    main.querySelector("#translation-language")
  );
  const serviceMode = /** @type {HTMLSelectElement} */ (main.querySelector("#service-mode"));
  const useCase = /** @type {HTMLSelectElement} */ (main.querySelector("#feature-use-case"));
  const exportBtn = /** @type {HTMLButtonElement} */ (
    main.querySelector("#download-feature-results")
  );
  const resetBtn = /** @type {HTMLButtonElement} */ (
    main.querySelector("#clear-feature-results")
  );
  const matchBoard = /** @type {HTMLElement} */ (
    main.querySelector(".feature-match-board")
  );
  const moreWrap = /** @type {HTMLElement} */ (main.querySelector(".show-more-wrap"));
  const moreBtn = /** @type {HTMLElement} */ (main.querySelector("#show-more"));
  const facetBtns = /** @type {HTMLElement[]} */ (Array.from(main.querySelectorAll(".facet-chip")));
  const countryBtns = /** @type {HTMLElement[]} */ (Array.from(main.querySelectorAll(".location-country")));
  let subdivisionBtns = /** @type {HTMLElement[]} */ ([]);
  const legacyStateBtns = /** @type {HTMLElement[]} */ (Array.from(main.querySelectorAll(".legacy-location")));
  const locationGroups = /** @type {HTMLElement | null} */ (main.querySelector(".location-groups"));
  const mapHost = /** @type {HTMLElement | null} */ (main.querySelector("#us-map"));
  const regionCoverage = /** @type {HTMLElement | null} */ (main.querySelector("#region-coverage"));
  let lastRegionHtml = "";
  const myLink = /** @type {HTMLElement} */ (main.querySelector("#my-agencies"));

  // Deep-linkable filters: prefer portable country/subdivision keys while still
  // accepting the former ?state= links. An old bookmark is left byte-for-byte
  // alone until the visitor changes a control, when it is canonicalized.
  const defaultSort = sortSel.value;
  const urlQi = location.hash.indexOf("?");
  const urlParams = new URLSearchParams(urlQi >= 0 ? location.hash.slice(urlQi + 1) : "");
  const facetValues = new Set(facetBtns.map((b) => b.dataset.facet));
  const wantFacet = urlParams.get("facet");
  let facet = facetValues.has(wantFacet) ? wantFacet : "all";
  const portableLocations = countryBtns.length > 0;
  const countries = Array.isArray(summary.countries) ? summary.countries : [];
  const countryValues = new Set(countryBtns.map((button) => button.dataset.country || ""));
  const subdivisions = countries.flatMap((country) =>
    (country.subdivisions || []).map((row) => ({
      code: row.subdivision_code || UNLOCATED_SUBDIVISION,
      country: country.country_code || "",
      name: row.subdivision_name || "Unlocated",
    }))
  );
  const legacyStateValues = new Set(legacyStateBtns.map((button) => button.dataset.state));
  const locationFilter = { country: "all", subdivision: "all", legacyState: "all" };
  const wantCountry = urlParams.get("country")?.toUpperCase() || null;
  const wantSubdivision = urlParams.get("subdivision")?.toUpperCase() || null;
  const subdivisionLocation =
    wantSubdivision === null
      ? null
      : subdivisions.find(
          (row) =>
            row.code === wantSubdivision &&
            (wantSubdivision !== UNLOCATED_SUBDIVISION || row.country === wantCountry)
        );
  // A globally unique ISO 3166-2 subdivision is the strongest location key and
  // determines its parent. Otherwise retain a valid country and discard an
  // inconsistent child. Only then consult the legacy state parameter.
  if (portableLocations && subdivisionLocation) {
    locationFilter.country = subdivisionLocation.country;
    locationFilter.subdivision = wantSubdivision || "all";
  } else if (portableLocations && wantCountry !== null && countryValues.has(wantCountry)) {
    locationFilter.country = wantCountry;
  } else if (portableLocations && urlParams.has("state")) {
    const oldState = urlParams.get("state") || "";
    const usMatch = subdivisions.find(
      (row) => row.country === "US" && row.name === oldState
    );
    if (usMatch) {
      locationFilter.country = "US";
      locationFilter.subdivision = usMatch.code || "all";
    } else if (oldState === "Canada" && countryValues.has("CA")) {
      locationFilter.country = "CA";
    } else if (
      oldState === "Unlocated" &&
      subdivisions.some(
        (row) => row.country === "US" && row.code === UNLOCATED_SUBDIVISION
      )
    ) {
      locationFilter.country = "US";
      locationFilter.subdivision = UNLOCATED_SUBDIVISION;
    }
  } else if (!portableLocations) {
    const wantState = urlParams.get("state");
    locationFilter.legacyState = legacyStateValues.has(wantState) ? wantState : "all";
  }
  let shown = 0; // how many of the current matches are painted
  let matches = /** @type {any[]} */ ([]);
  const qParam = urlParams.get("q");
  if (qParam) input.value = qParam;
  const sortParam = urlParams.get("sort");
  if (sortParam && Array.from(sortSel.options).some((o) => o.value === sortParam)) {
    sortSel.value = sortParam;
  }
  /** @type {Record<string, string>} */
  const featureProperties = {
    accessibility: "hasAccessibility",
    fares: "hasFares",
    fares_v2: "hasFaresV2",
    flex: "hasFlex",
    pathways: "hasPathways",
    step_free: "hasStepFree",
    cemv: "hasCemv",
    translations: "hasTranslations",
  };
  const featureLabels = {
    fares: "Fare data",
    fares_v2: "Fares v2",
    flex: "Flexible service",
    pathways: "Station pathways",
    step_free: "Step-free paths",
    cemv: "Contactless fare payments",
    translations: "Translated rider information",
  };
  const featureValues = new Set(featureChecks.map((control) => control.value));
  const thresholdValues = new Set(["any", "50", "95", "100"]);
  const selectedFeatures = new Set(
    (urlParams.get("features") || "")
      .split(",")
      .filter((value) => featureValues.has(value))
  );
  const wantedStops = urlParams.get("stops") || "";
  const wantedTrips = urlParams.get("trips") || "";
  const wantedFerryBikes = urlParams.get("ferry_bikes") || "";
  stopsMin.value = thresholdValues.has(wantedStops) ? wantedStops : "";
  tripsMin.value = thresholdValues.has(wantedTrips) ? wantedTrips : "";
  ferryBikesMin.value = thresholdValues.has(wantedFerryBikes) ? wantedFerryBikes : "";
  const languageValues = new Set(Array.from(translationLanguage.options).map((option) => option.value));
  const wantedLanguage = (urlParams.get("lang") || "").toLocaleLowerCase();
  translationLanguage.value = languageValues.has(wantedLanguage) ? wantedLanguage : "";
  const modeValues = new Set(Array.from(serviceMode.options).map((option) => option.value));
  const wantedMode = (urlParams.get("mode") || "").toLocaleLowerCase();
  serviceMode.value = modeValues.has(wantedMode) ? wantedMode : "";
  const wantedUseCase = urlParams.get("usecase") || "";
  useCase.value = Object.hasOwn(FEATURE_USE_CASES, wantedUseCase) ? wantedUseCase : "";
  const hasExplicitFeatureFilters = [
    "features",
    "stops",
    "trips",
    "ferry_bikes",
    "lang",
    "mode",
  ].some(
    (key) => urlParams.has(key)
  );
  if (useCase.value && !hasExplicitFeatureFilters) {
    const preset = FEATURE_USE_CASES[useCase.value];
    selectedFeatures.clear();
    for (const feature of preset.features) selectedFeatures.add(feature);
    serviceMode.value = preset.mode;
    stopsMin.value = preset.stops;
    tripsMin.value = preset.trips;
    ferryBikesMin.value = preset.ferryBikes || "";
  }
  function useCaseMatches(key) {
    const preset = FEATURE_USE_CASES[key];
    return Boolean(
      preset &&
      selectedFeatures.size === preset.features.length &&
      preset.features.every((feature) => selectedFeatures.has(feature)) &&
      serviceMode.value === preset.mode &&
      stopsMin.value === preset.stops &&
      tripsMin.value === preset.trips &&
      ferryBikesMin.value === (preset.ferryBikes || "") &&
      !translationLanguage.value
    );
  }
  if (useCase.value && !useCaseMatches(useCase.value)) useCase.value = "";
  for (const control of featureChecks) control.checked = selectedFeatures.has(control.value);
  const featureView = urlParams.get("view") === "features";
  for (const b of facetBtns) b.setAttribute("aria-pressed", String(b.dataset.facet === facet));

  // Reflect the live filter state in the URL without reloading the route:
  // replaceState never fires hashchange, so route() is not re-run.
  let userInteracted = false;
  function syncUrl() {
    if (!userInteracted) return;
    const p = new URLSearchParams();
    if (portableLocations) {
      if (locationFilter.country !== "all") p.set("country", locationFilter.country);
      if (locationFilter.subdivision !== "all") p.set("subdivision", locationFilter.subdivision);
    } else if (locationFilter.legacyState !== "all") {
      p.set("state", locationFilter.legacyState);
    }
    if (facet !== "all") p.set("facet", facet);
    const q = input.value.trim();
    if (q) p.set("q", q);
    if (sortSel.value !== defaultSort) p.set("sort", sortSel.value);
    if (useCase.value) p.set("usecase", useCase.value);
    if (selectedFeatures.size) p.set("features", [...selectedFeatures].join(","));
    if (featureView || useCase.value || selectedFeatures.size || serviceMode.value || translationLanguage.value || stopsMin.value || tripsMin.value || ferryBikesMin.value) {
      p.set("view", "features");
    }
    if (serviceMode.value) p.set("mode", serviceMode.value);
    if (translationLanguage.value) p.set("lang", translationLanguage.value);
    if (stopsMin.value) p.set("stops", stopsMin.value);
    if (tripsMin.value) p.set("trips", tripsMin.value);
    if (ferryBikesMin.value) p.set("ferry_bikes", ferryBikesMin.value);
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

  function meetsMinimum(value, minimum) {
    if (!minimum) return true;
    if (value === null) return false;
    return minimum === "any" ? value > 0 : value >= Number(minimum);
  }

  function matchesFeatures(a) {
    if (!selectedFeatures.size && !serviceMode.value && !translationLanguage.value && !stopsMin.value && !tripsMin.value && !ferryBikesMin.value) return true;
    for (const feature of selectedFeatures) {
      if (a[featureProperties[feature]] !== true) return false;
    }
    if (serviceMode.value && (!a.modesMeasured || !a.modes.includes(serviceMode.value))) {
      return false;
    }
    if (
      translationLanguage.value &&
      !a.translationLanguages.some(
        (language) => language.toLocaleLowerCase() === translationLanguage.value
      )
    ) return false;
    if ((stopsMin.value || tripsMin.value) && !a.accessibilityMeasured) return false;
    if (ferryBikesMin.value && !a.ferryProfileMeasured) return false;
    return (
      meetsMinimum(a.wheelchairStops, stopsMin.value) &&
      meetsMinimum(a.wheelchairTrips, tripsMin.value) &&
      meetsMinimum(a.ferryBikesStated, ferryBikesMin.value)
    );
  }

  function featureEvidence(a) {
    const evidence = [];
    if (serviceMode.value) evidence.push(`Mode: ${formatModeName(serviceMode.value)}`);
    if (
      (selectedFeatures.has("accessibility") || stopsMin.value || tripsMin.value) &&
      a.accessibilityMeasured
    ) {
      const stops = a.wheelchairStops === null ? "unknown stops" : `${a.wheelchairStops}% stops`;
      const trips = a.wheelchairTrips === null ? "unknown trips" : `${a.wheelchairTrips}% trips`;
      evidence.push(`Accessibility: ${stops}, ${trips}`);
    }
    for (const feature of selectedFeatures) {
      if (feature === "translations") {
        const languages = a.translationLanguages.slice(0, 3).map((code) => formatLanguageName(code));
        const remaining = a.translationLanguages.length - languages.length;
        evidence.push(`Translations: ${languages.join(", ")}${remaining > 0 ? `, plus ${remaining} more` : ""}`);
      } else if (feature !== "accessibility" && featureLabels[feature]) {
        evidence.push(featureLabels[feature]);
      }
    }
    if (translationLanguage.value && !selectedFeatures.has("translations")) {
      evidence.push(`Translations: ${formatLanguageName(translationLanguage.value)}`);
    }
    if (ferryBikesMin.value && a.ferryProfileMeasured) {
      evidence.push(t("feature_ferry_bicycle_evidence", { percent: a.ferryBikesStated }));
    }
    return evidence.length
      ? `<p class="feature-evidence"><span class="visually-hidden">Matched features: </span>${evidence.map(esc).join(" · ")}</p>`
      : "";
  }

  function cardHtml(a) {
    const cohort = getCohort();
    const followed = cohort.has(a.id);
    const place = placeLabel(a);
    return `<li class="agency-card">
      <span class="grade-chip ${escAttr(gradeClass(a.grade))}">${esc(a.grade)}<span class="visually-hidden"> grade</span></span>
      <div>
        <h2><a href="#/agency/${escAttr(a.id)}"><bdi>${esc(a.name)}</bdi></a></h2>
        <p class="meta">Overall ${a.score} out of 100${place ? ` · <bdi>${esc(place)}</bdi>` : ""} · checked ${formatDate(a.date)}</p>
        ${featureEvidence(a)}
      </div>
      <button type="button" class="follow" data-id="${escAttr(a.id)}" aria-pressed="${followed}">${followed ? "Following" : "Follow"}</button>
    </li>`;
  }

  function sorted(rows) {
    const mode = sortSel.value;
    if (mode === "az") return rows;
    return rows.slice().sort((a, b) => compareText(b.name, a.name));
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
    const active = Boolean(
      tokens.length ||
      facet !== "all" ||
      selectedFeatures.size ||
      serviceMode.value ||
      translationLanguage.value ||
      stopsMin.value ||
      tripsMin.value ||
      ferryBikesMin.value ||
      locationFilter.country !== "all" ||
      locationFilter.subdivision !== "all" ||
      locationFilter.legacyState !== "all"
    );
    setAppNav(
      featureView ||
      Boolean(
        selectedFeatures.size ||
          serviceMode.value ||
          translationLanguage.value ||
          stopsMin.value ||
          tripsMin.value ||
          ferryBikesMin.value
      )
    );
    matchBoard.dataset.active = String(active);
    hint.hidden = active;
    list.innerHTML = "";
    shown = 0;
    if (!active) {
      matches = [];
      count.textContent = "Choose a filter to build a shortlist.";
      exportBtn.disabled = true;
      exportBtn.textContent = "Download matching feeds (CSV)";
      resetBtn.disabled = true;
      noMatch.hidden = true;
      moreWrap.hidden = true;
      return;
    }
    matches = sorted(
      agencies.filter(
        (a) =>
          tokens.every((t) => a.search.includes(t)) &&
          matchesFacet(a) &&
          matchesFeatures(a) &&
          (locationFilter.country === "all" || a.country === locationFilter.country) &&
          (locationFilter.subdivision === "all" || a.subdivision === locationFilter.subdivision) &&
          (locationFilter.legacyState === "all" ||
            a.state === locationFilter.legacyState ||
            (locationFilter.legacyState === "Canada" && a.country === "CA"))
      )
    );
    const noun = matches.length === 1 ? "scorecard" : "scorecards";
    count.textContent = `${formatNumber(matches.length)} of ${formatNumber(total)} ${noun}`;
    exportBtn.disabled = matches.length === 0;
    resetBtn.disabled = false;
    const feedNoun = matches.length === 1 ? "feed" : "feeds";
    exportBtn.textContent = `Download ${formatNumber(matches.length)} matching ${feedNoun} (CSV)`;
    noMatch.hidden = matches.length !== 0;
    paintMore();
  }

  input.addEventListener("input", () => {
    userInteracted = true;
    apply();
  });
  sortSel.addEventListener("change", () => {
    userInteracted = true;
    apply();
  });
  for (const control of featureChecks) {
    control.addEventListener("change", () => {
      userInteracted = true;
      useCase.value = "";
      if (control.checked) selectedFeatures.add(control.value);
      else selectedFeatures.delete(control.value);
      apply();
    });
  }
  for (const control of [stopsMin, tripsMin, ferryBikesMin]) {
    control.addEventListener("change", () => {
      userInteracted = true;
      useCase.value = "";
      apply();
    });
  }
  translationLanguage.addEventListener("change", () => {
    userInteracted = true;
    useCase.value = "";
    apply();
  });
  serviceMode.addEventListener("change", () => {
    userInteracted = true;
    useCase.value = "";
    apply();
  });
  useCase.addEventListener("change", () => {
    userInteracted = true;
    const preset = FEATURE_USE_CASES[useCase.value];
    if (preset) {
      selectedFeatures.clear();
      for (const feature of preset.features) selectedFeatures.add(feature);
      for (const control of featureChecks) {
        control.checked = selectedFeatures.has(control.value);
      }
      stopsMin.value = preset.stops;
      tripsMin.value = preset.trips;
      ferryBikesMin.value = preset.ferryBikes || "";
      translationLanguage.value = "";
      serviceMode.value = preset.mode;
    }
    apply();
  });
  exportBtn.addEventListener("click", () => {
    if (!matches.length) return;
    const coverage = regionCoverageContext();
    downloadFeatureCsv(matches, {
      useCase: featureUseCaseLabel(useCase.value),
      coverageScope: coverage.scope,
      coverageDenominator: coverage.denominator,
      matchingRecords: matches.length,
      filterUrl: location.href,
    });
  });
  moreBtn.addEventListener("click", paintMore);
  for (const btn of facetBtns) {
    btn.addEventListener("click", () => {
      userInteracted = true;
      facet = btn.dataset.facet || "all";
      for (const b of facetBtns) b.setAttribute("aria-pressed", String(b === btn));
      apply();
    });
  }
  // Location can be picked from a chip or the choropleth; keep duplicates and
  // native button pressed states in sync. Only the selected country's
  // subdivision buttons are mounted, keeping the worldwide directory compact.
  let mapPaths = /** @type {HTMLElement[]} */ ([]);
  let worldPaths = /** @type {HTMLElement[]} */ ([]);
  let renderedSubdivisionCountry = "";
  function renderSelectedCountrySubdivisions() {
    if (!locationGroups || !portableLocations) return;
    const code = locationFilter.country === "all" ? "" : locationFilter.country;
    if (code === renderedSubdivisionCountry) return;
    renderedSubdivisionCountry = code;
    locationGroups.innerHTML = "";
    subdivisionBtns = [];
    if (!code) return;
    const country = countries.find((row) => row.country_code === code);
    const rows = country?.subdivisions || [];
    if (!country || !rows.length) return;
    const nameCounts = rows.reduce((counts, row) => {
      const name = String(row.subdivision_name || "Unlocated");
      counts[name] = (counts[name] || 0) + 1;
      return counts;
    }, {});
    const chips = rows
      .map((row) => {
        const name = row.subdivision_name || "Unlocated";
        const subdivision = row.subdivision_code || UNLOCATED_SUBDIVISION;
        const duplicateCode =
          nameCounts[String(name)] > 1 && row.subdivision_code
            ? ` <span class="hint">(${esc(row.subdivision_code)})</span>`
            : "";
        return `<button type="button" class="state-chip location-subdivision"
          data-country="${escAttr(code)}" data-subdivision="${escAttr(subdivision)}"
          data-subdivision-name="${escAttr(name)}" aria-pressed="false">
          <bdi>${esc(name)}</bdi>${duplicateCode}
          <span class="state-n">${row.agencies}</span></button>`;
      })
      .join("");
    locationGroups.innerHTML = `<section class="location-group"
      data-location-group="${escAttr(code)}" aria-labelledby="location-${escAttr(code)}">
      <h3 id="location-${escAttr(code)}"><bdi>${esc(country.country_name)}</bdi></h3>
      <div class="state-grid" role="group"
        aria-label="Filter by ${escAttr(country.country_name)} subdivision">${chips}</div>
      </section>`;
    subdivisionBtns = /** @type {HTMLElement[]} */ (
      Array.from(locationGroups.querySelectorAll(".location-subdivision"))
    );
    for (const button of subdivisionBtns) {
      button.addEventListener("click", () =>
        selectSubdivision(button.dataset.subdivision || "", button.dataset.country || "")
      );
    }
  }
  // The reviewed-cohort size for the selected country or subdivision, disclosed
  // beside the location filter so no regional cohort is read as a census. The
  // count is the tracked feed records for that place (directory.summary carries
  // it), never a claim of complete coverage. "" when no country is selected.
  function regionCoverageContext() {
    if (locationFilter.country === "all") {
      return { scope: t("feature_scope_all_tracked"), denominator: total, selected: false };
    }
    const country = countries.find((row) => (row.country_code || "") === locationFilter.country);
    if (!country) {
      return { scope: t("feature_scope_all_tracked"), denominator: total, selected: false };
    }
    const countryName = country.country_name || locationFilter.country;
    let count = Number(country.agencies) || 0;
    let place = countryName;
    let selectedScopeKey = "feature_scope_country";
    if (locationFilter.subdivision !== "all") {
      const sub = (country.subdivisions || []).find(
        (row) => (row.subdivision_code || UNLOCATED_SUBDIVISION) === locationFilter.subdivision
      );
      if (!sub) return { scope: countryName, denominator: count, selected: true };
      count = Number(sub.agencies) || 0;
      place = `${sub.subdivision_name || "Unlocated"}, ${countryName}`;
      selectedScopeKey = "feature_scope_area";
    }
    return { scope: place, denominator: count, selected: true, selectedScopeKey };
  }
  function regionCoverageHtml() {
    const coverage = regionCoverageContext();
    if (!coverage.selected) return "";
    const { denominator: count, scope: place, selectedScopeKey } = coverage;
    return t(
      count === 1 ? "feature_scope_disclosure_single" : "feature_scope_disclosure_plural",
      {
        count: formatNumber(count),
        place: `<bdi>${esc(place)}</bdi>`,
        selectedScope: t(selectedScopeKey),
      }
    );
  }
  function updateRegionCoverage() {
    if (!regionCoverage) return;
    const html = regionCoverageHtml();
    if (html !== lastRegionHtml) {
      lastRegionHtml = html;
      regionCoverage.innerHTML = html;
    }
    regionCoverage.hidden = !html;
  }
  function syncLocationUI() {
    renderSelectedCountrySubdivisions();
    updateRegionCoverage();
    for (const button of countryBtns) {
      button.setAttribute("aria-pressed", String(button.dataset.country === locationFilter.country));
    }
    for (const button of subdivisionBtns) {
      button.setAttribute(
        "aria-pressed",
        String(
          locationFilter.subdivision !== "all" &&
            button.dataset.subdivision === locationFilter.subdivision &&
            button.dataset.country === locationFilter.country
        )
      );
    }
    for (const button of legacyStateBtns) {
      button.setAttribute("aria-pressed", String(button.dataset.state === locationFilter.legacyState));
    }
    if (mapHost?.dataset.loaded === "true") {
      mapHost.hidden = portableLocations && locationFilter.country !== "US";
    }
    for (const path of worldPaths) {
      const selected = path.dataset.mapSubdivision
        ? locationFilter.subdivision !== "all" &&
          path.dataset.mapSubdivision === locationFilter.subdivision &&
          path.dataset.mapCountry === locationFilter.country
        : path.dataset.mapCountry === locationFilter.country;
      path.classList.toggle("selected", selected);
      path.setAttribute("aria-pressed", String(selected));
    }
    for (const path of mapPaths) {
      const selected = portableLocations
        ? locationFilter.subdivision !== "all" &&
          path.dataset.country === locationFilter.country &&
          path.dataset.subdivision === locationFilter.subdivision
        : path.dataset.state === locationFilter.legacyState;
      path.classList.toggle("selected", selected);
      path.setAttribute(
        "aria-pressed",
        String(selected)
      );
    }
  }
  function selectCountry(code) {
    userInteracted = true;
    if (locationFilter.country === code && locationFilter.subdivision === "all") {
      locationFilter.country = "all";
    } else {
      locationFilter.country = code;
    }
    locationFilter.subdivision = "all";
    syncLocationUI();
    apply();
  }
  function selectSubdivision(code, parentCountry) {
    userInteracted = true;
    if (
      locationFilter.subdivision === code &&
      locationFilter.country === parentCountry
    ) {
      locationFilter.subdivision = "all";
    } else {
      locationFilter.country = parentCountry;
      locationFilter.subdivision = code;
    }
    syncLocationUI();
    apply();
  }
  function selectLegacyState(name) {
    userInteracted = true;
    locationFilter.legacyState = locationFilter.legacyState === name ? "all" : name;
    syncLocationUI();
    apply();
  }
  for (const button of countryBtns) {
    button.addEventListener("click", () => selectCountry(button.dataset.country || ""));
  }
  for (const button of legacyStateBtns) {
    button.addEventListener("click", () => selectLegacyState(button.dataset.state || "all"));
  }
  function resetFilters() {
    userInteracted = true;
    input.value = "";
    facet = "all";
    selectedFeatures.clear();
    for (const control of featureChecks) control.checked = false;
    stopsMin.value = "";
    tripsMin.value = "";
    ferryBikesMin.value = "";
    translationLanguage.value = "";
    serviceMode.value = "";
    useCase.value = "";
    locationFilter.country = "all";
    locationFilter.subdivision = "all";
    locationFilter.legacyState = "all";
    for (const b of facetBtns) b.setAttribute("aria-pressed", String(b.dataset.facet === "all"));
    syncLocationUI();
    apply();
    input.focus();
  }
  clear.addEventListener("click", resetFilters);
  resetBtn.addEventListener("click", resetFilters);

  // Mount the world choropleth as progressive enhancement over the country
  // chips (omitted when web/world-countries.json can't load), and let a country
  // that has committed subdivision geometry drill down into its states or
  // provinces. Selecting a country filters exactly like its chip; drilling in is
  // an additional view, and a Back control returns to the world. Cities are the
  // agencies themselves, reached through the filtered list and the /map/ page.
  (async function mountWorldMap() {
    const host = /** @type {HTMLElement | null} */ (main.querySelector("#world-map"));
    if (!host || !portableLocations) return;
    let worldData;
    try {
      const resp = await fetch(new URL("../world-countries.json", location.href));
      if (!resp.ok) return;
      worldData = await resp.json();
    } catch {
      return;
    }
    const byCountry = {};
    for (const row of countries) byCountry[row.country_code || ""] = row;
    const subGeoCache = /** @type {Record<string, any>} */ ({});

    /** Load a country's subdivision geometry once, or null if it has none. */
    async function subdivisionGeometry(code) {
      const cc = (code || "").toLowerCase();
      if (cc in subGeoCache) return subGeoCache[cc];
      let geo = null;
      try {
        const resp = await fetch(new URL(`../subdivisions/${cc}.json`, location.href));
        if (resp.ok) geo = await resp.json();
      } catch {
        geo = null;
      }
      subGeoCache[cc] = geo;
      return geo;
    }

    function wireWorldPaths() {
      worldPaths = /** @type {HTMLElement[]} */ (
        Array.from(host.querySelectorAll("path[data-map-country]"))
      );
      for (const p of worldPaths) {
        const go = () => enterCountry(p.dataset.mapCountry || "");
        p.addEventListener("click", go);
        p.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            go();
          }
        });
      }
    }

    function renderWorld() {
      host.innerHTML = buildWorldMapSvg(worldData, byCountry);
      wireWorldPaths();
      syncLocationUI();
    }

    function renderCountry(cc, geo, countryRow) {
      const rows = (countryRow && countryRow.subdivisions) || [];
      host.innerHTML = buildSubdivisionMapSvg(geo, rows, (countryRow && countryRow.country_name) || cc);
      worldPaths = /** @type {HTMLElement[]} */ (
        Array.from(host.querySelectorAll("path[data-map-subdivision]"))
      );
      for (const p of worldPaths) {
        const go = () => selectSubdivision(p.dataset.mapSubdivision || "", p.dataset.mapCountry || cc);
        p.addEventListener("click", go);
        p.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            go();
          }
        });
      }
      const back = host.querySelector("[data-map-back]");
      if (back) {
        back.addEventListener("click", () => {
          renderWorld();
          // SVG <path> elements are SVGElement, not HTMLElement, so returning
          // focus to the country the user drilled from must test SVGElement
          // (as the drill-in focus below does). Testing HTMLElement here was
          // dead code that dropped keyboard focus to <body> on every Back.
          const world = host.querySelector(`path[data-map-country="${cc}"]`);
          if (world instanceof SVGElement) world.focus();
        });
      }
      syncLocationUI();
      const first = host.querySelector("path[data-map-subdivision]");
      if (first instanceof SVGElement) first.focus();
    }

    async function enterCountry(cc) {
      selectCountry(cc);
      const geo = await subdivisionGeometry(cc);
      if (locationFilter.country !== cc) return; // selection toggled back off
      const countryRow = countries.find((row) => (row.country_code || "") === cc);
      if (geo && countryRow) renderCountry(cc, geo, countryRow);
    }

    host.dataset.loaded = "true";
    renderWorld();
  })();

  // Mount the choropleth as progressive enhancement: the chip grid already
  // covers browse-by-state, so if the geometry asset can't load the map is just
  // omitted. The asset lives at the site root (web/us-states.json), reached
  // relative to /app/ rather than through the data base.
  (async function mountMap() {
    const host = mapHost;
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
    const us = countries.find((row) => row.country_code === "US");
    const subdivisionCodes = Object.fromEntries(
      (us?.subdivisions || []).map((row) => [row.subdivision_name, row.subdivision_code || ""])
    );
    host.innerHTML = buildMapSvg(mapData, byState, subdivisionCodes, portableLocations);
    host.dataset.loaded = "true";
    mapPaths = /** @type {HTMLElement[]} */ (
      Array.from(host.querySelectorAll(portableLocations ? "path[data-subdivision]" : "path[data-state]"))
    );
    for (const p of mapPaths) {
      p.addEventListener("click", () => {
        if (portableLocations) {
          selectSubdivision(p.dataset.subdivision || "", p.dataset.country || "US");
        } else {
          selectLegacyState(p.dataset.state || "all");
        }
      });
      p.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (portableLocations) {
            selectSubdivision(p.dataset.subdivision || "", p.dataset.country || "US");
          } else {
            selectLegacyState(p.dataset.state || "all");
          }
        }
      });
    }
    syncLocationUI();
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

  syncLocationUI();
  apply();
  if (featureView) {
    requestAnimationFrame(() => {
      const section = /** @type {HTMLElement | null} */ (main.querySelector("#feature-finder"));
      section?.focus({ preventScroll: true });
      section?.scrollIntoView({ block: "start" });
    });
  }
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
      const sample = Number(r.comparison_eligible ?? 0);
      const avg =
        sample > 0 && typeof r.average_score === "number" && Number.isFinite(r.average_score)
          ? `${r.average_score} avg`
          : "average unavailable";
      return `<li class="agency-card reveal">
        <div>
          <h2><a href="#/program/${escAttr(r.id)}">${esc(r.name)}</a></h2>
          <p class="meta">${r.agency_count} feed scorecards · ${avg} (${sample} comparable) · ${attention}</p>
        </div>
      </li>`;
    })
    .join("");
  main.innerHTML = `
    <a class="backlink" href="#/">&larr; All agencies</a>
    <h1 class="page-title reveal">Program rollups.</h1>
    <p class="page-lede reveal">A view for the people who support many agencies at once.
    Each rollup puts attention work first, ordered by rider impact when known, then lists
    other feed scorecards alphabetically. It also surfaces fixes shared across several feeds.</p>
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
        <span class="grade-chip ${escAttr(gradeClass(m.grade))}">${esc(m.grade)}<span class="visually-hidden"> grade</span></span>
        <div>
          <h3><a href="#/agency/${escAttr(m.id)}">${esc(m.name)}</a>${flag}</h3>
          <p class="meta">${m.score} out of 100 · checked ${formatDate(m.snapshot_date)}</p>
          ${fix}
        </div>
      </li>`;
    })
    .join("");

  const aggregate = guardedAggregateState(rollup, rollup.average_score);
  const comparableCount = aggregate.count;
  const dist = aggregate.valid
    ? gradeDistributionBar(
        aggregate.distribution,
        comparableCount,
        "Grade distribution across this program",
      )
    : "";

  const common = (aggregate.valid ? rollup.common_fixes || [] : [])
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

  const avg = aggregate.valid
    ? `${rollup.average_score} out of 100 average`
    : "average unavailable";
  const comparisonContract = comparisonContractText(rollup.comparison);
  const comparisonNote = aggregate.valid
    ? `The average and grade distribution use ${comparableCount} canonical, non-duplicate
      feed scorecards under one producer contract: ${comparisonContract}. Every member
      remains listed below.`
    : `The cross-feed average, grade distribution, and shared-fix counts are unavailable
      until this rollup has a complete guarded summary under ${comparisonContract}. Every
      member remains listed below.`;
  const shapes = rollup.shapes_readiness;
  const measured = shapes ? shapes.total - shapes.not_measured : 0;
  const shapesNote =
    shapes && measured > 0
      ? `<p class="snapshot-note">shapes.txt (NTD RY2026): ${shapes.ready} of ${measured} ready</p>`
      : "";
  // Country rollups state their denominator plainly: reviewed feed records
  // tracked in that country, never a claim of country coverage.
  const countryLabel = String(
    rollup.rollup.country_name || rollup.rollup.country_code || ""
  ).trim();
  const recordNoun = rollup.agency_count === 1 ? "reviewed feed record" : "reviewed feed records";
  const scopeNote = countryLabel
    ? `<p class="fineprint">Scope: ${rollup.agency_count} ${recordNoun} tracked in
      ${esc(countryLabel)}. This page measures those records, not operators, routes, or
      all public transport in ${esc(countryLabel)}, and it is not a claim that
      GTFS Scorecard covers ${esc(countryLabel)}.</p>`
    : "";
  main.innerHTML = `
    <a class="backlink" href="#/programs">&larr; All rollups</a>
    <div class="score-hero reveal">
      <div>
        <h1 class="page-title">${esc(rollup.rollup.name)}</h1>
        <p class="overall"><strong>${rollup.agency_count} feed scorecards</strong> ·
          ${avg} · ${rollup.needs_attention} need attention</p>
        <p class="fineprint">${comparisonNote}</p>
        ${scopeNote}
        ${shapesNote}
      </div>
    </div>
    ${routeRule()}
    ${dist ? `<section aria-labelledby="dist-h" class="reveal">
      <h2 class="section-title visually-hidden" id="dist-h">Grade distribution</h2>${dist}
    </section>` : ""}
    <section aria-labelledby="members-h" class="reveal">
      <h2 class="section-title" id="members-h">Feed scorecards: attention first, then alphabetical</h2>
      <ul class="program-list">${rows}</ul>
    </section>
    ${commonSection}`;
}

/* ---------------- my cohort (client-side) ---------------- */

/** Render the follower's personal cohort as an attention-first worklist, then
 *  alphabetically. Membership comes from a shared URL or this browser's saved list.
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
    const comparableHist = currentProducerHistory(hist);
    const prev = comparableHist.length >= 2 ? comparableHist[comparableHist.length - 2] : null;
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
  members.sort((m, n) =>
    !!m.reason === !!n.reason ? compareText(m.name, n.name) : m.reason ? -1 : 1
  );

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
        <span class="grade-chip ${escAttr(gradeClass(m.grade))}">${esc(m.grade)}<span class="visually-hidden"> grade</span></span>
        <div>
          <h3><a href="#/agency/${escAttr(m.id)}">${esc(m.name)}</a>${flag}</h3>
          <p class="meta">${m.score} out of 100 · checked ${formatDate(m.date)}</p>
          ${change}
          ${fix}
          <details class="cohort-note"${note ? " open" : ""}>
            <summary>Note${note ? " ✓" : ""}</summary>
            <label class="visually-hidden" for="note-${escAttr(m.id)}">Private note for ${esc(m.name)}</label>
            <textarea id="note-${escAttr(m.id)}" class="note-input" data-id="${escAttr(m.id)}"
              rows="2" placeholder="Call notes (saved in this browser only)">${esc(note)}</textarea>
          </details>
        </div>
        <button type="button" class="cohort-remove" data-id="${escAttr(m.id)}" aria-label="Remove ${escAttr(m.name)} from my agencies">Remove</button>
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
      <h2 class="section-title" id="cohort-h">Agencies: attention first, then alphabetical</h2>
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

const MODE_TEXT_KEYS = new Set([
  "summary", "what", "why", "fix", "effort", "description", "detail", "note",
  "title", "action", "impact", "label",
]);

/** @param {any} artifact */
function modeLanguageKind(artifact) {
  const profile = artifact?.mode_profile;
  if (!profile || profile.measured !== true) return "generic";
  if (profile.ferry_only === true) return "ferry";
  if (profile.is_multimodal !== true && profile.primary_mode === "bus") return "bus";
  return "generic";
}

/** @param {string} original @param {string} replacement */
function preserveWordCase(original, replacement) {
  if (original === original.toUpperCase()) return replacement.toUpperCase();
  if (original[0] === original[0].toUpperCase())
    return replacement[0].toUpperCase() + replacement.slice(1);
  return replacement;
}

/** @param {string} text @param {string} source @param {string} replacement */
function replaceModeWord(text, source, replacement) {
  return text.replace(new RegExp(`\\b${source}\\b`, "gi"), (word) => preserveWordCase(word, replacement));
}

/** @param {string} text @param {string} kind */
function adaptModeText(text, kind) {
  if (kind === "bus") return text;
  const singular = kind === "ferry" ? "vessel" : "transit vehicle";
  const plural = kind === "ferry" ? "vessels" : "transit vehicles";
  let result = replaceModeWord(replaceModeWord(text, "buses", plural), "bus", singular)
    .replace(/\bwrong streets\b/gi, "wrong path")
    .replace(/\bwrong corner\b/gi, kind === "ferry" ? "wrong terminal" : "wrong boarding location");
  if (kind !== "ferry") return result;
  const phrases = [
    [/\baccessible stops\b/gi, "accessible terminals"],
    [/\bflagged stops\b/gi, "flagged terminals"],
    [/\bbusiest stops\b/gi, "busiest terminals"],
    [/\bevery stop\b/gi, "every terminal"],
    [/\bSome stops exist\b/gi, "Some terminals exist"],
    [/\bRiders at the stop\b/gi, "Riders at the terminal"],
    [/\bwalk to a stop\b/gi, "go to a terminal"],
    [/(\b\d+(?:\.\d+)?%? of (?:\d+ )?)stops\b/gi, "$1terminals"],
    [/\bSome stops sit\b/gi, "Some terminals sit"],
    [/\bstops or vehicles\b/gi, "terminals or vessels"],
    [/\bstop coverage\b/gi, "terminal coverage"],
    [/\bwhether a stop is\b/gi, "whether a terminal is"],
    [/\bnearly every stop\b/gi, "nearly every terminal"],
    [/\bper flagged stop\b/gi, "per flagged terminal"],
    [/\bno trip ever stops at them\b/gi, "no trip serves them"],
    [/\bwhat the vessel displays\b/gi, "the published sailing destination"],
    [/\bwhich direction a vessel is going\b/gi, "which destination a sailing serves"],
  ];
  for (const [source, replacement] of phrases) result = result.replace(source, String(replacement));
  return result;
}

/** @param {any} value @param {string} kind */
function adaptModeContainer(value, kind) {
  if (Array.isArray(value)) return value.map((item) => adaptModeContainer(item, kind));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => {
    if (MODE_TEXT_KEYS.has(key) && typeof item === "string") return [key, adaptModeText(item, kind)];
    if (Array.isArray(item) || (item && typeof item === "object"))
      return [key, adaptModeContainer(item, kind)];
    return [key, item];
  }));
}

/** @param {any} artifact */
function adaptArtifactLanguage(artifact) {
  const result = { ...artifact };
  const kind = modeLanguageKind(result);
  if (result.categories) result.categories = adaptModeContainer(result.categories, kind);
  for (const key of ["top_fixes", "recommendations"])
    if (Array.isArray(result[key])) result[key] = adaptModeContainer(result[key], kind);
  if (result.conformance) result.conformance = adaptModeContainer(result.conformance, kind);
  if (Array.isArray(result.routability?.findings))
    result.routability = { ...result.routability, findings: adaptModeContainer(result.routability.findings, kind) };
  return result;
}

const SHORT_MODE_LABELS = {
  tram: "Tram", subway: "Metro", rail: "Rail", bus: "Bus", ferry: "Ferry",
  cable_tram: "Cable tram", aerial_lift: "Aerial lift", funicular: "Funicular",
  trolleybus: "Trolleybus", monorail: "Monorail", other: "Other",
};

/** @param {any} artifact */
function serviceModeLabel(artifact) {
  const profile = artifact?.mode_profile;
  if (!profile || profile.measured !== true || !Array.isArray(profile.modes)) return "";
  const labels = profile.modes
    .filter((mode) => mode && mode.key)
    .map((mode) => SHORT_MODE_LABELS[mode.key] || "Other");
  if (!labels.length) return "";
  if (labels.length <= 3) return labels.join(" + ");
  return `${labels.slice(0, 2).join(" + ")} + ${labels.length - 2} more`;
}

/** @param {any} artifact @param {any} history @param {any} [dirRecord] */
function renderScorecard(artifact, history, dirRecord) {
  // The directory carries the portable location contract. Enrich old artifacts
  // locally so every country-gated section uses the same effective country.
  const effectiveCountry = String(dirRecord?.country || artifact.agency?.country || "US").toUpperCase();
  artifact = { ...artifact, agency: { ...artifact.agency, country: effectiveCountry } };
  artifact = adaptArtifactLanguage(artifact);
  const name = artifact.agency.name;
  document.title = `${name} — GTFS Scorecard`;
  const overall = artifact.overall;

  const cats = CATEGORY_ORDER.map((key, i) =>
    categoryCard(key, artifact.categories[key], i, artifact),
  ).join("");
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
    ${riderImpactSection(artifact)}
    ${ferryProfileSection(artifact)}

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
    ${standardsSection(artifact, dirRecord)}

    ${routeRule()}
    ${badgeSection(artifact.agency.id)}

    ${routeRule()}
    <section aria-labelledby="feed-h" class="feed-details">
      <h2 class="section-title" id="feed-h">About this data</h2>
      <dl>
        <dt>Feed checked</dt><dd><a href="${escAttr(safeUrl(artifact.feed.static_url))}">${esc(artifact.feed.static_url)}</a></dd>
        <dt>Snapshot</dt><dd>${esc(artifact.snapshot_date)}${artifact.feed?.sha256 ? ` (<abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr> ${esc(artifact.feed.sha256.slice(0, 12))}…)` : ""}</dd>
        <dt>Validator</dt><dd>MobilityData gtfs-validator ${esc(String(artifact.validator_version ?? artifact.categories.correctness?.details?.validator_version ?? ""))}</dd>
        <dt>Rubric</dt><dd>version ${esc(String(artifact.rubric_version ?? "—"))}; <a href="https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/rubric.md">methodology and citations (docs/rubric.md)</a></dd>
      </dl>
    </section>`;

  setupFindings(findings);
}

/** A closed, presentation-only rider summary derived from existing artifact fields.
 *  Unknown values stay neutral and this never becomes a service-quality score.
 *  @param {any} artifact @returns {string} */
function riderImpactSection(artifact) {
  const categories = artifact?.categories || {};
  const freshness = categories.freshness || {};
  const freshDetails = freshness.details || {};
  const days = freshness.status === "measured" ? numericValue(freshDetails.days_until_expiry) : null;
  const horizonStatus = effectiveServiceHorizonStatus(freshDetails, artifact?.snapshot_date);
  let schedule;
  if (days === null) schedule = "Schedule visibility is not known from this scorecard.";
  else if (horizonStatus === "unusually_distant") {
    const end = freshDetails.effective_expiry_date;
    const through = end ? ` through ${esc(String(end))}` : " to an unusually distant date";
    schedule = `The feed states that service is published${through}. This may be intentional or a placeholder; confirm current service with the transit operator.`;
  }
  else if (days > 0) schedule = `The feed's last published service date is in ${plainNumber(days)} days.`;
  else if (days === 0) schedule = "The feed's last published service date is today.";
  else schedule = `The feed's last published service date was ${plainNumber(Math.abs(days))} days ago.`;

  const completeness = categories.completeness || {};
  const compDetails = completeness.status === "measured" ? completeness.details || {} : {};
  const access = compDetails.accessibility || {};
  const stops = numericValue(access.stops_stated_pct ?? compDetails.wheelchair_boarding_pct);
  const trips = numericValue(access.trips_stated_pct ?? compDetails.wheelchair_accessible_pct);
  const ferryOnly = modeLanguageKind(artifact) === "ferry";
  const places = ferryOnly ? "terminals" : "stops";
  const placeCoverage = ferryOnly ? "Terminal coverage" : "Stop coverage";
  const vehicles = ferryOnly ? "vessels" : "vehicles";
  let accessibility;
  if (stops !== null && trips !== null)
    accessibility = `Accessibility information is stated for ${plainNumber(stops)}% of ${places} and ${plainNumber(trips)}% of trips.`;
  else if (stops !== null)
    accessibility = `Accessibility information is stated for ${plainNumber(stops)}% of ${places}; trip coverage is not known.`;
  else if (trips !== null)
    accessibility = `Accessibility information is stated for ${plainNumber(trips)}% of trips; ${placeCoverage.toLowerCase()} is not known.`;
  else accessibility = "Published accessibility-data coverage is not known from this scorecard.";
  accessibility += ` This measures published data, not whether ${places} or ${vehicles} are physically usable.`;

  let fare;
  if (compDetails.fare_free === true) fare = "The feed marks this service as fare-free.";
  else if (compDetails.has_fares === true) {
    const model = compDetails.fares?.model;
    const modelLabel = { legacy: "GTFS Fares v1", v2: "GTFS Fares v2" }[model] || model;
    fare = modelLabel
      ? `Fare information is published using ${esc(String(modelLabel))}.`
      : "Fare information is published in the feed.";
  } else if (compDetails.has_fares === false && compDetails.fare_free === false)
    fare = "No fare information is published in the feed.";
  else fare = "Fare-information availability is not known from this scorecard.";

  const realtime = categories.realtime || {};
  const rtDetails = realtime.details || {};
  const coverage = realtime.status === "measured" ? numericValue(rtDetails.coverage_pct) : null;
  const reachable = numericValue(rtDetails.kinds_reachable);
  let live;
  if (coverage !== null)
    live = `Live-arrival data covered ${plainNumber(coverage)}% of scheduled trips in the sampled window.`;
  else if (realtime.status === "measured" && reachable !== null && reachable > 0)
    live = "One or more realtime feeds were reachable; live-arrival coverage is not known.";
  else if (realtime.status === "measured" && reachable === 0)
    live = "No realtime feed was reachable during sampling.";
  else live = "Realtime-feed availability and live-arrival coverage are not known from this scorecard.";

  return `<details class="rider-impact" id="rider-impact">
    <summary>Rider view: what this feed publishes</summary>
    <p class="rider-impact-intro">A quick read of rider-facing information in this feed.</p>
    <dl>
      <dt>Schedule visibility</dt><dd>${schedule}</dd>
      <dt>Published accessibility data</dt><dd>${accessibility}</dd>
      <dt>Fare information</dt><dd>${fare}</dd>
      <dt>Realtime information</dt><dd>${live}</dd>
    </dl>
    <p class="rider-impact-boundary"><strong>Important:</strong> This does not rate service
      reliability. Riders should confirm current service alerts, fares, and accessibility
      accommodations with the transit operator before traveling.</p>
  </details>`;
}

/** Explain a ferry enum while keeping blank/0 values explicitly unknown.
 * @param {any} profile @param {string} subject @param {string} field */
function ferryEnumText(profile, subject, field) {
  const total = Number(profile?.total_count || 0);
  const stated = Number(profile?.stated_count || 0);
  const allowed = Number(profile?.allowed_count || 0);
  if (!total) return `No ${subject} were available to measure in this snapshot.`;
  if (!stated) return `Unknown: none of the ${formatNumber(total)} ${subject} publish ${field}.`;
  return `${plainNumber(profile.stated_pct)}% of ${subject} publish a value; ` +
    `${plainNumber(profile.allowed_pct)}% of all ${subject} explicitly say allowed ` +
    `(${formatNumber(allowed)} of ${formatNumber(total)}). Unstated values remain unknown.`;
}

/** Descriptive ferry subset. It never changes the score.
 * @param {any} artifact @returns {string} */
function ferryProfileSection(artifact) {
  const profile = artifact?.ferry_profile;
  if (!profile || profile.measured !== true) return "";

  const hierarchy = profile.terminal_hierarchy || {};
  const boarding = Number(hierarchy.boarding_location_count || 0);
  const parented = Number(hierarchy.parented_boarding_location_count || 0);
  const stations = Number(hierarchy.referenced_station_count || 0);
  let hierarchyText;
  if (!boarding) hierarchyText = "No ferry boarding locations were available to measure.";
  else if (!parented)
    hierarchyText = `${formatNumber(boarding)} ferry boarding locations; no parent-station hierarchy is published.`;
  else
    hierarchyText = `${formatNumber(boarding)} ferry boarding locations; ${formatNumber(parented)} link to ` +
      `${formatNumber(stations)} referenced station record${stations === 1 ? "" : "s"}.`;

  const access = profile.stop_access || {};
  const eligible = Number(access.eligible_terminal_count || 0);
  const accessStated = Number(access.stated_count || 0);
  let accessText;
  if (!eligible)
    accessText = "Not applicable: no ferry boarding location is linked to a parent station, so stop_access is not permitted here.";
  else if (!accessStated)
    accessText = `Unknown: none of the ${formatNumber(eligible)} eligible child terminal locations publish stop_access.`;
  else
    accessText = `${plainNumber(access.stated_pct)}% of eligible child terminal locations publish access: ` +
      `${formatNumber(Number(access.direct_count || 0))} direct from the street network and ` +
      `${formatNumber(Number(access.through_station_count || 0))} through the station or its pathways.`;

  const accessibility = profile.accessibility || {};
  const accessibilityText =
    `${ferryEnumText(accessibility.terminals, "ferry boarding locations", "wheelchair_boarding")} ` +
    `${ferryEnumText(accessibility.trips, "ferry trips", "wheelchair_accessible")} ` +
    "This reports published values, not verified physical usability.";

  const fares = profile.fares || {};
  const model = String(fares.model || "none");
  let faresText;
  if (fares.fare_free === true) faresText = "Whole feed: the service is curated as fare-free.";
  else if (fares.applied === true) {
    const label = { legacy: "GTFS Fares v1", v2: "GTFS Fares v2" }[model] || model;
    faresText = `Whole feed: applied fare data is published using ${label}.`;
  } else if (model === "v2")
    faresText = "Whole feed: Fares v2 products are present, but no leg rules apply them to trips.";
  else
    faresText = "Whole feed: no applied fare data is published. This is not evidence that ferry service is free.";

  const kindLabels = {
    trip_updates: "Trip Updates",
    vehicle_positions: "Vehicle Positions",
    service_alerts: "Service Alerts",
  };
  const kinds = Array.isArray(profile.realtime?.configured_kinds)
    ? profile.realtime.configured_kinds
    : [];
  const realtimeText = kinds.length
    ? `Whole feed: configured GTFS-Realtime endpoints are ${kinds.map((kind) => kindLabels[kind] || String(kind).replaceAll("_", " ")).join(", ")}.`
    : "Whole feed: no GTFS-Realtime endpoints are configured in this scorecard.";

  const rows = [
    ["Ferry service", `${formatNumber(Number(profile.route_count || 0))} routes · ${formatNumber(Number(profile.trip_count || 0))} trips`],
    ["Terminal structure", hierarchyText],
    ["Terminal access", accessText],
    ["Published accessibility", accessibilityText],
    ["Bicycles", ferryEnumText(profile.bikes, "ferry trips", "bikes_allowed")],
    ["Cars", ferryEnumText(profile.cars, "ferry trips", "cars_allowed")],
    ["Fares", faresText],
    ["Realtime", realtimeText],
  ];
  return `<section class="feed-details ferry-profile reveal" aria-labelledby="ferry-profile-h">
    <p class="ferry-profile-kicker">Ungraded capability read</p>
    <h2 class="section-title" id="ferry-profile-h">Ferry data profile</h2>
    <p class="page-lede">A ferry-specific view of what this GTFS feed publishes. Schedule
      measurements use ferry routes and trips only; fare and realtime facts are labelled as
      whole-feed. Unknown values are not treated as no.</p>
    <dl class="ferry-profile-grid">${rows.map(([label, value]) =>
      `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>
    <p class="fineprint">Descriptive only. This profile does not change the grade or verify
      vessels, terminal facilities, vehicle carriage, fares, or accessibility in the real world.
      Field meanings follow the <a href="https://gtfs.org/documentation/schedule/reference/">GTFS Schedule reference</a>.</p>
  </section>`;
}

/** @param {unknown} value @returns {number|null} */
function numericValue(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Parse a strict published YYYY-MM-DD value without using the browser's locale.
 *  @param {unknown} value @returns {{year:number, month:number, day:number}|null} */
function publishedDate(value) {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const parts = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  if (parts.year < 1) return null;
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(parts.year, parts.month - 1, parts.day);
  if (
    !Number.isFinite(date.getTime()) ||
    date.getUTCFullYear() !== parts.year ||
    date.getUTCMonth() + 1 !== parts.month ||
    date.getUTCDate() !== parts.day
  )
    return null;
  return parts;
}

/** @param {{year:number, month:number, day:number}} value @param {number} days */
function publishedDateAfterDays(value, days) {
  if (!Number.isInteger(days)) return null;
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(value.year, value.month - 1, value.day + days);
  if (!Number.isFinite(date.getTime())) return null;
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
  };
}

/** @param {{year:number, month:number, day:number}} value @param {number} years */
function publishedDateAfterYears(value, years) {
  const year = value.year + years;
  const leapDay = value.month === 2 && value.day === 29;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return { year, month: value.month, day: leapDay && !leapYear ? 28 : value.day };
}

/** @param {{year:number, month:number, day:number}} value */
function publishedDateKey(value) {
  return value.year * 10000 + value.month * 100 + value.day;
}

/** Resolve schema-1.10 status, deriving it for legacy artifacts deterministically.
 *  @param {any} details @param {unknown} snapshotDate @returns {string} */
function effectiveServiceHorizonStatus(details, snapshotDate) {
  const explicit = details?.service_horizon_status;
  if (
    explicit === "within_review_threshold" ||
    explicit === "unusually_distant" ||
    explicit === "unknown"
  )
    return explicit;
  const checked =
    publishedDate(snapshotDate) || publishedDate(details?.snapshot_date) || publishedDate(details?.date);
  if (!checked) return "unknown";
  let expiry = publishedDate(details?.effective_expiry_date);
  if (!expiry) {
    const days = numericValue(details?.days_until_expiry);
    if (days === null) return "unknown";
    expiry = publishedDateAfterDays(checked, days);
  }
  if (!expiry) return "unknown";
  const boundary = publishedDateAfterYears(checked, SERVICE_HORIZON_REVIEW_YEARS);
  return publishedDateKey(expiry) > publishedDateKey(boundary)
    ? "unusually_distant"
    : "within_review_threshold";
}

/** Replace a legacy embedded countdown with the horizon trust advisory.
 *  @param {any} category @param {unknown} snapshotDate @returns {string} */
function presentedFreshnessSummary(category, snapshotDate) {
  const summary = String(category?.summary || "");
  const details = category?.details || {};
  if (effectiveServiceHorizonStatus(details, snapshotDate) !== "unusually_distant")
    return summary;
  const end = publishedDate(details.effective_expiry_date)
    ? String(details.effective_expiry_date).trim()
    : null;
  const through = end ? ` through ${end}` : " to an unusually distant date";
  return `Service is published${through}. It may be intentional, but confirm the end date before treating the feed as maintained.`;
}

/** @param {number} value @returns {string} */
function plainNumber(value) {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** Split-flap grade reel that lands on the agency's grade. @param {string} grade */
function gradeReel(grade) {
  const g = String(grade || "F").toUpperCase().slice(0, 1);
  const idx = GRADE_RANK[g] ?? 0;
  return `<div class="reel" role="img" aria-label="Overall grade ${escAttr(g)}"
      style="--flap-end: calc(var(--reel-h) * -${idx})">
    <div class="reel-strip"><span>F</span><span>D</span><span>C</span><span>B</span><span>A</span></div>
  </div>`;
}

/** Status chips from the feed's freshness, completeness, and realtime. @param {any} artifact */
function statusChips(artifact) {
  const chips = [];
  const freshDetails = artifact.categories?.freshness?.details || {};
  const days = freshDetails.days_until_expiry;
  const horizonStatus = effectiveServiceHorizonStatus(freshDetails, artifact.snapshot_date);
  if (typeof days === "number") {
    if (horizonStatus === "unusually_distant")
      chips.push('<span class="chip warn">Review service end date</span>');
    else if (days <= 0) chips.push('<span class="chip warn">Feed expired</span>');
    else if (days < 30) chips.push(`<span class="chip warn">Expires in ${days} days</span>`);
    else chips.push(`<span class="chip ok">Covers ${days} days</span>`);
  }
  const comp = artifact.categories?.completeness;
  if (comp?.status === "measured" && comp.score < 70)
    chips.push('<span class="chip warn">Accessibility gaps</span>');
  const realtime = artifact.categories?.realtime || {};
  if (realtime.status !== "measured")
    chips.push(`<span class="chip">${esc(realtimeUnmeasuredLabel(realtime))}</span>`);
  return chips.join("");
}

/** @param {any} category @returns {string} */
function realtimeUnmeasuredLabel(category) {
  const summary = String(category?.summary || "").toLowerCase();
  if (summary.includes("access key") || summary.includes("api key") || summary.includes("authentication"))
    return "Realtime access needed";
  return "Realtime not yet published";
}

/** A clean trend line for the board (no leading separator). @param {any[]} history */
function boardTrend(history) {
  const comparable = currentProducerHistory(history);
  if (comparable.length < 2)
    return history.length >= 2
      ? "Producer or measurement contract changed; trend restarts here"
      : "First scorecard for this agency";
  const prev = comparable[comparable.length - 2];
  const cur = comparable[comparable.length - 1];
  const d = Math.round((cur.score - prev.score) * 10) / 10;
  if (d > 0)
    return `<span aria-hidden="true">▲</span> up ${d} since ${formatDate(prev.date)} · ${prev.grade} → ${cur.grade}`;
  if (d < 0) return `<span aria-hidden="true">▼</span> down ${Math.abs(d)} since ${formatDate(prev.date)}`;
  return `unchanged since ${formatDate(prev.date)}`;
}

/** Full producer/measurement contract of one compact history point.
 *  @param {any} point @returns {string[] | null} */
function historyProducerContract(point) {
  const rubric = String(point?.rubric_version || "");
  const profile = String(point?.scoring_profile_id || point?.scoring_profile?.id || "");
  const profileRubric = String(
    point?.scoring_profile_rubric_version || point?.scoring_profile?.rubric_version || "",
  );
  const validator = String(point?.validator_version || "");
  const readerProfile = readerArchiveProfile(point);
  const categories = point?.categories || {};
  const measured = CATEGORY_ORDER.filter(
    (key) => typeof categories[key] === "number" && Number.isFinite(categories[key]),
  );
  if (!rubric || !profile || !profileRubric || !validator || !readerProfile || !measured.length)
    return null;
  return [rubric, profile, profileRubric, validator, readerProfile, measured.join(",")];
}

/** Contiguous suffix produced by one full producer and measurement contract.
 *  Missing provenance restarts the trend at the latest point. @param {any[]} history */
function currentProducerHistory(history) {
  if (!history.length) return [];
  const contract = historyProducerContract(history[history.length - 1]);
  if (!contract) return history.slice(-1);
  let start = history.length - 1;
  while (start > 0) {
    const previous = historyProducerContract(history[start - 1]);
    if (!previous || previous.some((value, index) => value !== contract[index])) break;
    start -= 1;
  }
  return history.slice(start);
}

/** Catalog location retained after public percentile claims were removed.
 *  @param {any} [dirRecord] */
function peerContext(dirRecord) {
  if (!dirRecord) return "";
  const place = placeLabel(dirRecord);
  return place ? `<p class="peer-context">Catalogued in <bdi>${esc(place)}</bdi>.</p>` : "";
}

/** @param {string} name @param {any} artifact @param {any[]} history @param {any} [dirRecord] */
function boardHero(name, artifact, history, dirRecord) {
  const o = artifact.overall;
  const mode = serviceModeLabel(artifact);
  return `<div class="board-hero reveal">
    <div class="board-inner">
      <p class="board-kicker"><span class="blip" aria-hidden="true"></span>Feed status · checked ${formatDate(artifact.snapshot_date)}</p>
      <h1 class="board-title"><bdi>${esc(name)}</bdi></h1>
      <p class="board-sub">Based on the feed this agency publishes</p>
      ${mode ? `<p class="board-mode"><span>Service mode</span> ${esc(mode)}</p>` : ""}
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
  const comparable = currentProducerHistory(history);
  if (comparable.length < 2)
    return history.length >= 2
      ? " · methodology changed; trend restarts here"
      : " · first scorecard for this agency";
  const prev = comparable[comparable.length - 2];
  const cur = comparable[comparable.length - 1];
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
      role="img" aria-label="Overall score across ${n} checks: ${escAttr(series)}">
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
  const comparable = currentProducerHistory(history);
  if (comparable.length < 2) {
    const message = history.length >= 2
      ? "The producer or measurement contract changed since the prior check, so the trend restarts here. No improvement or regression is claimed across that boundary."
      : 'This is the first scorecard for this agency. A trend and a "what changed" summary appear here once it has been checked more than once.';
    return `<section aria-labelledby="trend-h" class="reveal">
      <h2 class="section-title" id="trend-h">Over time</h2>
      <p class="page-lede">${message}</p>
    </section>`;
  }
  history = comparable;
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

/** One category as a departure-board "platform" row.
 *  @param {string} key @param {any} cat @param {number} index @param {any} artifact */
function categoryCard(key, cat, index, artifact) {
  const label = CATEGORY_LABELS[/** @type {keyof CATEGORY_LABELS} */ (key)] ?? key;
  const trk = String(index + 1).padStart(2, "0");
  const summary =
    key === "freshness" ? presentedFreshnessSummary(cat, artifact?.snapshot_date) : String(cat?.summary || "");
  if (!cat || cat.status !== "measured") {
    const note = summary || "Not part of the grade yet. Nothing here counts against you.";
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
           aria-valuemax="100" aria-label="${escAttr(label)} score">
        <span style="width:${w}%;background:var(--grade-${band})"></span>
      </div>
      <p class="pstat">${esc(summary)}</p>
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
          ? `<span class="aworth">worth about +${Math.round(f.points)} points in its category</span>`
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
      for (const f of cat.findings) {
        all.push({ ...f, severity: findingSeverity(f.severity).key, category: key });
      }
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
        (f) => {
          const severity = findingSeverity(f.severity);
          return `<li class="finding">
          <div class="finding-head">
            <span class="sev ${severity.className}">${esc(severity.label)}</span>
            <span class="count">${f.count === 1 ? "1 instance" : `${f.count} instances`}</span>
          </div>
          <p class="what">${esc(f.what)}</p>
          <p class="why">${esc(f.why)}</p>
          <p class="how"><strong>Fix:</strong> ${esc(f.fix)} <em>(${esc(f.effort)})</em></p>
          <p class="code">Validator rule: ${esc(f.code)} ·
            <a class="fix-guide" href="${escAttr(FIX_DOCS_BASE + encodeURIComponent(f.code))}.md"
               target="_blank" rel="noopener">Read the fix guide<span aria-hidden="true"> ↗</span><span class="visually-hidden"> (opens on GitHub)</span></a>${ruleRefLink(f.code)}</p>
        </li>`;
        }
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

// Status labels for the NTD / conformance blocks. The text label carries the
// meaning; the color class only reinforces it, never the sole cue. Mirrors the
// static page (pipeline/src/scorecard_pipeline/render_site.py) so the SPA card
// and the prerendered /agency/<id>/ page read the same.
const NTD_LABELS = { ready: "Ready", at_risk: "Needs attention", not_ready: "Not ready" };
const NTD_PILLAR_NAMES = {
  published: "Published",
  valid: "Valid",
  current: "Current",
  agency_id: "agency_id provided",
};
const NTD_ALIGN_LABELS = {
  aligned: "Equal",
  mismatch: "Different (allowed)",
  missing: "Not available",
  unknown: "Not checked yet",
};
const NTD_ALIGN_CLASSES = {
  aligned: "ntd-ready",
  mismatch: "ntd-unknown",
  missing: "ntd-unknown",
  unknown: "ntd-unknown",
};
const CONFORMANCE_NAMES = { valid: "Valid", current: "Current", accessible: "Accessible" };

/** Recompute agency_id presence from the alignment block stored in older artifacts.
 *  Presence and the P-50 crosswalk are required for RY2026; equality to the
 *  five-digit NTD ID is not.
 *  @param {any} artifact */
function ntdIdentityPillar(artifact) {
  const align = artifact.ntd_id_alignment;
  if (!align || !Array.isArray(align.feed_agency_ids)) {
    return {
      key: "agency_id",
      status: "at_risk",
      detail: "agency_id presence has not been checked for this feed yet.",
    };
  }
  const ids = align.feed_agency_ids.map((value) => String(value).trim()).filter(Boolean);
  if (!ids.length) {
    return {
      key: "agency_id",
      status: "not_ready",
      detail:
        "agency.txt has no nonblank agency_id. Every RY2026 NTD GTFS submission needs a stable value unique among the reporters represented in the feed, crosswalked to each reporter's NTD ID on the P-50 form.",
    };
  }
  return {
    key: "agency_id",
    status: "ready",
    detail:
      "agency.txt provides agency_id. For RY2026, keep one stable value for each NTD reporter represented in the feed and crosswalk each value on the P-50 form.",
  };
}

/** Current wording for the optional equality comparison, derived from stored inputs.
 *  @param {any} stored */
function currentNtdAlignment(stored) {
  if (!stored || !Array.isArray(stored.feed_agency_ids)) return stored;
  const ids = stored.feed_agency_ids.map((value) => String(value).trim()).filter(Boolean);
  const ntd = String(stored.ntd_id || "").trim();
  if (!ids.length) return { ...stored, status: "missing" };
  if (!ntd) {
    return {
      ...stored,
      status: "unknown",
      detail:
        "This feed provides agency_id. For RY2026, keep one stable value for each NTD reporter represented in the feed and crosswalk it on the P-50 form. The value does not need to equal the five-digit NTD ID; we do not have that ID on file, so the optional equality comparison is not checked yet.",
      fix: "",
    };
  }
  if (ids.includes(ntd)) {
    return {
      ...stored,
      status: "aligned",
      detail: `This feed's agency_id also equals its NTD ID (${ntd}). Equality is allowed but not required; keep the value stable and retain the P-50 crosswalk.`,
      fix: "",
    };
  }
  const found = ids.join(", ");
  return {
    ...stored,
    status: "mismatch",
    detail: `Your feed's agency_id is ${found}; your National Transit Database ID is ${ntd}. A feed that serves several agencies (a shared regional feed) can legitimately carry more than one agency_id. The values do not need to equal the five-digit NTD ID, so this difference is allowed and carries no score.`,
    fix: `Confirm that P-50 crosswalks agency_id ${found} to NTD ID ${ntd}, and keep the feed value stable. Do not change it solely to make the two values equal.`,
  };
}

/** The optional agency_id / NTD-ID equality line. Reads the stored alignment
 *  inputs, rewrites stale copy, and omits the line when agency_id is missing
 *  because the required presence check is already a readiness pillar.
 *  @param {any} artifact */
function ntdAlignmentRow(artifact) {
  const align = currentNtdAlignment(artifact.ntd_id_alignment);
  if (!align || align.status === "missing") return "";
  const status = String(align.status || "unknown");
  const label = NTD_ALIGN_LABELS[status] || status;
  const cls = NTD_ALIGN_CLASSES[status] || "ntd-unknown";
  let body = esc(String(align.detail || ""));
  if (align.fix) body += " " + esc(String(align.fix));
  return `<dl class="standards-list">
      <dt>agency_id equals your NTD ID (optional) <span class="ntd-status ${cls}">${esc(label)}</span></dt>
      <dd>${body}</dd></dl>`;
}

/** NTD GTFS readiness: four pillars (published, valid, current, agency_id) plus
 *  a neutral optional equality line. Older artifacts get the identity pillar
 *  from their stored alignment inputs at presentation time.
 *  @param {any} artifact */
function ntdSection(artifact) {
  if (String(artifact.agency?.country || "US").toUpperCase() !== "US") return "";
  const r = artifact.ntd_readiness;
  const alignRow = ntdAlignmentRow(artifact);
  if (!r && !alignRow) return "";
  let pillars = "";
  let summary = "";
  let head = '<abbr title="National Transit Database">NTD</abbr> GTFS readiness';
  if (r) {
    const sourcePillars = (r.pillars || []).filter((p) => p.key !== "agency_id");
    sourcePillars.push(ntdIdentityPillar(artifact));
    const shownPillars = sourcePillars.map((p) => {
      const distant =
        p.key === "current" &&
        effectiveServiceHorizonStatus(
          artifact.categories?.freshness?.details || {},
          artifact.snapshot_date,
        ) === "unusually_distant";
      return {
        ...p,
        detail: distant
          ? "The published window is current, but its service end date is unusually distant; confirm that date is intentional."
          : String(p.detail || ""),
      };
    });
    const rank = { ready: 0, at_risk: 1, not_ready: 2 };
    const headStatus = shownPillars.reduce(
      (worst, p) => ((rank[p.status] || 0) > (rank[worst] || 0) ? p.status : worst),
      "ready",
    );
    const overall = NTD_LABELS[headStatus] || headStatus;
    head = `<abbr title="National Transit Database">NTD</abbr> GTFS readiness <span class="ntd-status ntd-${escAttr(headStatus)}">${esc(overall)}</span>`;
    if (headStatus === "ready") {
      summary =
        "Published at a public URL, valid, current, and identified with agency_id: the four feed checks for RY2026 all hold here. Only your own D-10 and P-50 filings make that official; this is a heads-up, not a determination.";
    } else {
      const problems = shownPillars
        .filter((p) => p.status !== "ready")
        .map((p) => p.detail)
        .join(" ");
      summary =
        headStatus === "not_ready"
          ? `Resolve this before you certify on the D-10. ${problems}`
          : `This feed is close to NTD-ready. ${problems}`;
    }
    pillars = shownPillars
      .map((p) => {
        const label = NTD_LABELS[p.status] || p.status;
        const name = NTD_PILLAR_NAMES[p.key] || p.key;
        return `<dt>${esc(name)} <span class="ntd-status ntd-${escAttr(String(p.status))}">${esc(label)}</span></dt><dd>${esc(p.detail)}</dd>`;
      })
      .join("");
  }
  return `<section aria-labelledby="ntd-h" class="feed-details reveal">
    <h2 class="section-title" id="ntd-h">${head}</h2>
    ${summary ? `<p class="page-lede">${esc(summary)}</p>` : ""}
    ${pillars ? `<dl class="standards-list">${pillars}</dl>` : ""}
    ${alignRow}
    <p class="plain-summary"><strong>In plain words:</strong> if you report to the federal transit
      database, you have to publish a working, up-to-date feed, provide a stable agency_id for each
      represented reporter, and confirm the feed and P-50 crosswalk each year. This box is a
      heads-up; your filings are the official check.</p>
    <p class="fineprint">A readiness signal mapping this feed to the
      <a href="https://www.transit.dot.gov/ntd"><abbr title="Federal Transit Administration">FTA</abbr> National Transit Database</a> GTFS
      requirement (Report Year 2023 onward: a public, valid, current feed, certified annually on
      the <abbr title="FTA NTD certification form D-10">D-10</abbr>). For RY2026, each represented
      reporter needs a stable agency_id, unique within the feed and crosswalked to its five-digit
      NTD ID on P-50; the values do not need to be equal. Not an official determination; your
      filings are the official check.</p>
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
      const distant =
        c.key === "current" &&
        effectiveServiceHorizonStatus(
          artifact.categories?.freshness?.details || {},
          artifact.snapshot_date,
        ) === "unusually_distant";
      const detail = distant
        ? "The published window is current, but its service end date is unusually distant; confirm that date is intentional."
        : String(c.detail || "");
      return `<dt>${esc(name)} <span class="ntd-status ${status}">${label}</span></dt><dd>${esc(detail)}</dd>`;
    })
    .join("");
  const headStatus = mark.awarded ? "ntd-ready" : "ntd-not_ready";
  const headLabel = mark.awarded ? "Awarded" : "Not yet";
  const seal = mark.awarded
    ? `<p><img src="${escAttr(safeUrl(`/data/artifacts/${agencyId}/mark.svg`))}" alt="GTFS conformance mark for ${escAttr(agencyName)}"></p>`
    : "";
  const ferryOnly = modeLanguageKind(artifact) === "ferry";
  const place = ferryOnly ? "terminal" : "stop";
  return `<section aria-labelledby="mark-h" class="feed-details reveal">
    <h2 class="section-title" id="mark-h">Conformance mark <span class="ntd-status ${headStatus}">${headLabel}</span></h2>
    ${mark.summary ? `<p class="page-lede">${esc(String(mark.summary))}</p>` : ""}
    ${seal}
    <dl class="standards-list">${rows}</dl>
    <p class="plain-summary"><strong>In plain words:</strong> earn this mark when your feed passes
      validation, has not expired, and says whether nearly every ${place} and trip is wheelchair
      accessible.</p>
    <p class="fineprint">A pass credential for a feed that is valid, current, and states
      wheelchair access on nearly every ${place} and trip. Accessibility here measures what the
      feed publishes, not whether a ${place} is physically usable.
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

/** The safe mechanical subset of fixes a user can run locally. Renders only
 *  the precomputed artifact.autofix summary from older artifacts and deliberately
 *  ignores any legacy public-download URL. Empty when no autofix block is present
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
  const action = `<p class="autofix-cli">Run it locally on a copy of the feed you control: ` +
    `<code>scorecard autofix &lt;feed.zip&gt; --out corrected.zip</code></p>`;
  return `<section aria-labelledby="autofix-h" class="reveal">
    <h2 class="section-title" id="autofix-h">Safe fixes you can run locally</h2>
    <p class="page-lede">The local command applies only these mechanical changes to a copy you
      control. The scorecard does not publish a modified feed. Review the diff before you publish
      through your usual process.</p>
    <ul class="autofix-list">${items}</ul>${action}
  </section>`;
}

/** Jurisdiction-aware guidance overlay. The grade never changes: this only
 *  selects references that apply to the agency's country and subdivision. */
function standardsSection(artifact, dirRecord) {
  const CW = "/crosswalk/";
  const country = String(artifact.agency?.country || "US").toUpperCase();
  const state = String(dirRecord?.state || "");
  const subdivision = String(
    dirRecord?.subdivision_code || (country === "US" ? US_STATE_SUBDIVISION_CODES[state] : "") || "",
  ).toUpperCase();
  const national = country === "US" ? US_NTD_GUIDANCE : null;
  const local = JURISDICTION_GUIDANCE[subdivision] || SUPPORT_RESOURCES[subdivision];
  const rows = CATEGORY_ORDER.map((key) => {
    let note = UNIVERSAL_GUIDANCE.category_notes[key];
    if (national?.category_notes[key]) note += ` ${national.category_notes[key]}`;
    return `<dt>${esc(CATEGORY_LABELS[key])}</dt><dd>${esc(note)}</dd>`;
  })
    .join("");
  const lead = local && local.kind === "guideline"
    ? (state ? `In ${esc(state)}, the published guideline is ` : "The published guideline for this jurisdiction is ")
    : "A local transit-data support resource is ";
  const localBoundary = local?.kind === "support"
    ? " This resource supports agencies; it is not a scoring authority."
    : "";
  const stateHtml = local
    ? `<p class="page-lede">${lead}<a href="${escAttr(local.url)}">${esc(local.name)}</a>. ${esc(local.note)}${localBoundary}</p>`
    : "";
  const refs = [...UNIVERSAL_GUIDANCE.references, ...(national ? [national] : [])]
    .map((ref) => `<a href="${escAttr(ref.url)}">${esc(ref.name)}</a>`)
    .join(", ");
  return `<section aria-labelledby="standards-h" class="feed-details reveal">
    <h2 class="section-title" id="standards-h">How this maps to the standards</h2>
    <p class="page-lede">${esc(UNIVERSAL_GUIDANCE.note)} Useful references here are ${refs}.
    Read the full <a href="${CW}">standards crosswalk</a>.</p>
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
    updates after each completed scoring check and links back to this scorecard.</p>
    <p><img src="${escAttr(safeUrl(badgeUrl))}" alt="Current GTFS quality grade badge"></p>
    <label class="badge-embed-label" for="badge-embed">Markdown to embed</label>
    <input id="badge-embed" class="badge-embed" type="text" readonly
      value="${escAttr(markdown)}">
  </section>`;
}

/* ---------------- router ---------------- */

/** @param {string} message */
function renderError(message) {
  main.innerHTML = `<div class="error-box" role="alert">
    <h1 class="page-title">${esc(t("app_error_title"))}</h1>
    <p>${esc(message)}</p>
    <p><a class="backlink" href="#/">${esc(t("app_back_all_agencies"))}</a></p>
  </div>`;
}

/** @param {string} agencyId */
function renderNotFound(agencyId) {
  document.title = t("app_not_found_doc_title");
  main.innerHTML = `<div class="error-box" role="alert">
    <h1 class="page-title">${esc(t("app_not_found_title", { agency: agencyId }))}</h1>
    <p>${esc(t("app_not_found_body"))}</p>
    <p><a class="backlink" href="#/">${esc(t("app_back_all_agencies"))}</a></p>
  </div>`;
}

/** Keep U.S.-only policy navigation available on global routes and U.S. agency
 *  scorecards, but remove it from the accessibility tree on other countries'
 *  scorecards. The crawlable page shell applies the same country rule.
 *  @param {string} [country] */
function showUsPolicyToolsForCountry(country = "US") {
  const ntdLink = document.querySelector('.site-footer a[href="/ntd/"]');
  const ntdItem = ntdLink?.closest("li");
  const equityItem = document
    .querySelector('.site-footer a[href="/equity/"]')
    ?.closest("li");
  const legacySection = ntdLink?.closest("p");
  const show = String(country).toUpperCase() === "US";
  for (const element of [ntdItem?.previousElementSibling, ntdItem, equityItem, legacySection]) {
    if (element instanceof HTMLElement) element.hidden = !show;
  }
}

/** Two like-for-like scorecards side by side as an accessible comparison table, shareable via
 *  #/compare?a=<id>&b=<id>. No new dependency: a data table, not a map, so it
 *  works with a keyboard and a screen reader out of the box. When either id is
 *  missing or unknown, a picker chooses two agencies and navigates to the URL.
 *  @param {string|null} aId @param {string|null} bId */
async function renderCompare(aId, bId) {
  document.title = "Compare agencies — GTFS Scorecard";
  const dir = await loadDirectory();
  const agencies = (dir.agencies || []).slice().sort((x, y) => compareText(x.name, y.name));
  const byId = new Map(agencies.map((a) => [a.id, a]));
  const valid = (id) => !!id && byId.has(id);

  if (!valid(aId) || !valid(bId)) {
    const firstId = valid(aId) ? aId : agencies[0]?.id || "";
    const secondId =
      valid(bId) && bId !== firstId
        ? bId
        : agencies.find((agency) => agency.id !== firstId)?.id || "";
    const options = (selected) =>
      agencies
        .map((a) => `<option value="${escAttr(a.id)}"${a.id === selected ? " selected" : ""}>${esc(a.name)}</option>`)
        .join("");
    main.innerHTML = `
      <a class="backlink" href="#/">&larr; All agencies</a>
      <h1 class="page-title">Compare two agencies</h1>
      <p class="page-lede">Choose two scorecards to check whether they use the same rubric,
      scoring profile, validator, reader archive profile, and measured category set, and
      come from distinct feed bytes.
      Like-for-like results can appear side by side; otherwise this page keeps the scores
      separate and links to each full scorecard.</p>
      <form id="compare-pick" class="compare-pick">
        <p><label for="cmp-a">First agency</label>
          <select id="cmp-a" name="a">${options(firstId)}</select></p>
        <p><label for="cmp-b">Second agency</label>
          <select id="cmp-b" name="b">${options(secondId)}</select></p>
        <p><button type="submit" class="compare-go">Check comparability</button></p>
        <p id="compare-pick-status" class="form-status form-status-err" role="alert" hidden></p>
      </form>`;
    const form = /** @type {HTMLFormElement} */ (main.querySelector("#compare-pick"));
    const first = /** @type {HTMLSelectElement} */ (form.querySelector("#cmp-a"));
    const second = /** @type {HTMLSelectElement} */ (form.querySelector("#cmp-b"));
    const status = /** @type {HTMLElement} */ (form.querySelector("#compare-pick-status"));
    function clearCompareError() {
      status.hidden = true;
      status.textContent = "";
    }
    first.addEventListener("change", clearCompareError);
    second.addEventListener("change", clearCompareError);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const a = first.value;
      const b = second.value;
      if (!a || !b || a === b) {
        status.textContent = t("app_compare_pick_two");
        status.hidden = false;
        second.focus();
        return;
      }
      location.hash = `#/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`;
    });
    return;
  }

  main.innerHTML = `<p class="loading" role="status">${esc(t("app_loading"))}</p>`;
  const [aArt, bArt] = await Promise.all([
    fetchJson(`${aId}/latest.json`),
    fetchJson(`${bId}/latest.json`),
  ]);

  const comparisonContract = (art) => {
    const profile = art.scoring_profile || {};
    return {
      rubric: String(art.rubric_version || ""),
      profile: String(profile.id || ""),
      profileRubric: String(profile.rubric_version || ""),
      validator: String(art.validator_version || ""),
      readerArchive: readerArchiveProfile(art),
      feedHash: String(art.feed?.sha256 || ""),
      measured: CATEGORY_ORDER.filter((key) => art.categories?.[key]?.status === "measured"),
    };
  };
  const aContract = comparisonContract(aArt);
  const bContract = comparisonContract(bArt);
  const likeForLike =
    aContract.rubric !== "" &&
    aContract.profile !== "" &&
    aContract.validator !== "" &&
    aContract.readerArchive !== "" &&
    bContract.readerArchive !== "" &&
    aContract.feedHash !== "" &&
    bContract.feedHash !== "" &&
    aContract.feedHash !== bContract.feedHash &&
    aContract.profileRubric === aContract.rubric &&
    bContract.profileRubric === bContract.rubric &&
    aContract.rubric === bContract.rubric &&
    aContract.profile === bContract.profile &&
    aContract.validator === bContract.validator &&
    aContract.readerArchive === bContract.readerArchive &&
    JSON.stringify(aContract.measured) === JSON.stringify(bContract.measured);

  const aName = aArt.agency.name;
  const bName = bArt.agency.name;
  if (!likeForLike) {
    main.innerHTML = `
      <a class="backlink" href="#/compare">&larr; Choose different agencies</a>
      <h1 class="page-title">These scorecards are not like-for-like.</h1>
      <div class="error-box" role="status">
        <p>${esc(aName)} and ${esc(bName)} do not have distinct feed bytes under the same
        verified scoring profile, rubric, validator, reader archive profile, and measured
        category set. Showing their grades side by side could make a duplicate record,
        methodology, or realtime-coverage difference look like a feed-quality difference.</p>
        <p><a href="#/agency/${escAttr(aId)}">Open ${esc(aName)}</a> &nbsp;·&nbsp;
        <a href="#/agency/${escAttr(bId)}">Open ${esc(bName)}</a></p>
      </div>`;
    return;
  }

  const gradeCell = (art) => {
    const o = art.overall || {};
    return `<span class="grade-chip ${escAttr(gradeClass(o.grade))}">${esc(o.grade)}<span class="visually-hidden"> grade</span></span> ${esc(String(o.score ?? "—"))}<span class="outof"> / 100</span>`;
  };
  const catCell = (art, key) => {
    const c = (art.categories || {})[key];
    if (!c || c.status !== "measured") return `<span class="cmp-na">Not yet measured</span>`;
    const s = Number(c.score);
    const w = Math.max(2, Math.min(100, s));
    const band = gradeBand(s);
    return `<div class="pbar cmp-bar" role="meter" aria-valuenow="${s}" aria-valuemin="0" aria-valuemax="100" aria-label="${escAttr(`${CATEGORY_LABELS[key]} score for ${art.agency.name}`)}"><span style="width:${w}%;background:var(--grade-${band})"></span></div><span class="cmp-num">${s} / 100</span>`;
  };
  const fixesCell = (art) => {
    const fixes = (art.top_fixes || []).slice(0, 3);
    if (!fixes.length) return `<span class="cmp-na">No priority fixes</span>`;
    return `<ol class="cmp-fixes">${fixes.map((f) => `<li>${esc(f.fix)}</li>`).join("")}</ol>`;
  };

  const catRows = CATEGORY_ORDER.map(
    (key) =>
      `<tr><th scope="row">${esc(CATEGORY_LABELS[key])}</th><td>${catCell(aArt, key)}</td><td>${catCell(bArt, key)}</td></tr>`
  ).join("");

  main.innerHTML = `
    <a class="backlink" href="#/compare">&larr; Choose different agencies</a>
    <h1 class="page-title">${esc(aName)} vs ${esc(bName)}</h1>
    <p class="page-lede">These scorecards use the same verified rubric, scoring profile,
    validator, reader archive profile, and measured category set, and they come from distinct
    feed bytes. Each column links to its full page.</p>
    <div class="table-wrap"><table class="compare-table">
      <caption class="visually-hidden">Data-quality comparison of ${esc(aName)} and ${esc(bName)}</caption>
      <thead><tr>
        <td></td>
        <th scope="col"><a href="#/agency/${escAttr(aId)}">${esc(aName)}</a></th>
        <th scope="col"><a href="#/agency/${escAttr(bId)}">${esc(bName)}</a></th>
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
  setAppNav(false);
  // Every non-agency route is global. Reset first so navigating away from a
  // non-U.S. scorecard never leaves its country-specific footer state behind.
  showUsPolicyToolsForCountry();
  main.innerHTML = `<p class="loading" role="status">${esc(t("app_loading"))}</p>`;
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
        showUsPolicyToolsForCountry(dirRecord?.country || artifact.agency?.country || "US");
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

// Strings resolve before first render so a requested pseudolocale preview
// applies to the whole page; in production initStrings returns immediately.
initStrings().finally(() => {
  window.addEventListener("hashchange", route);
  route();
});
