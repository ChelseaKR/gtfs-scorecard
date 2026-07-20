/* Progressive enhancement for the landing-page service desk.
 * Scores come from the published per-agency artifacts; this file never
 * calculates or compares them. The two small fallback records keep the
 * pilot switcher useful if a fetch is interrupted.
 */
(function () {
  "use strict";

  var desk = document.getElementById("live-scorecard");
  if (!(desk instanceof HTMLElement)) return;

  var CATEGORY_ORDER = ["correctness", "freshness", "completeness", "realtime"];
  var CATEGORY_LABELS = {
    correctness: "Correctness",
    freshness: "Freshness",
    completeness: "Rider experience",
    realtime: "Realtime",
  };
  var PILOT_PLACES = {
    unitrans: "Unitrans / Davis, California",
    yolobus: "Yolobus / Yolo County, California",
  };
  var PILOT_URLS = {
    unitrans: "/data/artifacts/unitrans/latest.json",
    yolobus: "/data/artifacts/yolobus/latest.json",
  };
  var ACCESSIBILITY_NOTE =
    "Accessibility values describe what the feed publishes, not verified physical conditions.";
  var FRESHNESS_CODES = new Set([
    "scorecard_feed_expired",
    "scorecard_feed_expiring_soon",
    "scorecard_intermittent_calendar_ended",
    "scorecard_missing_feed_info_dates",
    "scorecard_no_expiry_date",
    "scorecard_planned_service_boundary",
  ]);

  var FALLBACKS = {
    unitrans: {
      agency: { id: "unitrans", name: "Unitrans (ASUCD / City of Davis)" },
      snapshot_date: "2026-07-10",
      overall: { grade: "B", score: 80.8 },
      categories: {
        correctness: {
          status: "measured",
          score: 84.8,
          summary:
            "The MobilityData validator flagged 4 kinds of issue across 96 instances: 0 errors, 72 warnings, and 24 informational notices.",
        },
        freshness: {
          status: "measured",
          score: 100,
          summary: "Service data covers the next 74 days.",
        },
        completeness: {
          status: "measured",
          score: 60,
          summary:
            "0% of stops state wheelchair accessibility. This measures what the feed publishes, not whether a stop is physically usable. Fare data is published.",
        },
        realtime: {
          status: "not_yet_measured",
          summary:
            "Unitrans runs live bus tracking, but its data feed requires an access key the scorecard does not have. Realtime is excluded from this grade, with no deduction.",
        },
      },
      top_fixes: [
        {
          code: "scorecard_wheelchair_boarding_unknown",
          rank: 1,
          owner: "Likely your team",
          fix: "Set wheelchair_boarding to 1 (accessible) or 2 (not accessible) for every stop. A field survey can start with the busiest stops.",
          what: "296 of 296 stops don't say whether a wheelchair user can board there.",
          why: "Riders who use wheelchairs can't plan a trip when accessibility is marked unknown; apps show no information at all.",
          effort: "A column in stops.txt; your scheduling software likely has it.",
        },
        {
          code: "scorecard_wheelchair_accessible_unknown",
          rank: 2,
          owner: "Likely your export tool",
          fix: "Set wheelchair_accessible on every trip.",
          what: "3071 of 3071 trips don't say whether the vehicle is wheelchair accessible.",
          why: "Even with accessible stops, riders need to know the bus itself can take them.",
          effort: "Often one default setting in your export.",
        },
        {
          code: "unused_shape",
          rank: 3,
          owner: "Likely your export tool",
          fix: "Enable 'remove unused shapes' (or similar) in your export tool.",
          what: "The feed contains route shapes no trip uses.",
          why: "Harmless to riders, but it bloats the feed and suggests stale export data.",
          effort: "One setting.",
        },
      ],
    },
    yolobus: {
      agency: { id: "yolobus", name: "Yolobus (Yolo County Transportation District)" },
      snapshot_date: "2026-07-10",
      overall: { grade: "B", score: 82.2 },
      categories: {
        correctness: {
          status: "measured",
          score: 90,
          summary:
            "The MobilityData validator flagged 2 kinds of issue across 16 instances: 0 errors and 16 warnings.",
        },
        freshness: {
          status: "measured",
          score: 83.3,
          summary: "Service data covers the next 59 days; feed_info dates are missing.",
        },
        completeness: {
          status: "measured",
          score: 62.4,
          summary:
            "99% of stops state wheelchair accessibility, trips do not state vehicle accessibility, and fare data is not published.",
        },
        realtime: {
          status: "measured",
          score: 92.2,
          summary:
            "Sampled 9 times: 3 of 3 feeds were healthy; 77.8% of scheduled trips had live predictions; vehicles stayed on route; median schedule drift was 17 seconds.",
        },
      },
      top_fixes: [
        {
          code: "scorecard_wheelchair_accessible_unknown",
          rank: 1,
          owner: "Likely your export tool",
          fix: "Set wheelchair_accessible on every trip.",
          what: "721 of 721 trips don't say whether the vehicle is wheelchair accessible.",
          why: "Riders cannot confirm that the vehicle can accommodate a wheelchair.",
          effort: "Often one default setting in your export.",
        },
        {
          code: "scorecard_no_fare_data",
          rank: 2,
          owner: "Owner to confirm",
          fix: "Add fare data, or ask to have the service marked fare-free.",
          what: "The feed contains no fare information.",
          why: "Riders see fare unknown in trip planners and cannot budget their trip.",
          effort: "A small file for most flat-fare systems.",
        },
        {
          code: "scorecard_missing_feed_info_dates",
          rank: 3,
          owner: "Likely your export tool",
          fix: "Add feed_start_date and feed_end_date to feed_info.txt.",
          what: "feed_info.txt is missing its start and end dates.",
          why: "Apps and this scorecard cannot warn anyone before the feed goes stale.",
          effort: "Two fields, set once in export settings.",
        },
      ],
    },
  };

  var elements = {
    agency: document.querySelector("#scorecard-agency bdi"),
    place: document.getElementById("scorecard-place"),
    date: document.getElementById("scorecard-date"),
    grade: document.getElementById("scorecard-grade"),
    score: document.getElementById("scorecard-score"),
    categoryDetailTitle: document.getElementById("category-detail-title"),
    categoryDetailSummary: document.getElementById("category-detail-summary"),
    fixCode: document.getElementById("fix-code"),
    fixTitle: document.getElementById("fix-title"),
    fixWhat: document.getElementById("fix-what"),
    fixWhy: document.getElementById("fix-why"),
    fixOwner: document.getElementById("fix-owner"),
    fixEffort: document.getElementById("fix-effort"),
    effortLine: document.querySelector(".effort-line"),
    fixSelector: document.getElementById("fix-selector"),
    fullLink: document.getElementById("full-scorecard-link"),
    briefLink: document.getElementById("brief-link"),
    note: document.getElementById("measurement-note"),
    status: document.getElementById("scorecard-status"),
    traceSourceTitle: document.getElementById("trace-source-title"),
    traceSourceCopy: document.getElementById("trace-source-copy"),
    traceSourceFiles: document.getElementById("trace-source-files"),
    traceMethodTitle: document.getElementById("trace-method-title"),
    traceMethodCopy: document.getElementById("trace-method-copy"),
    traceCode: document.getElementById("trace-code"),
    traceRecordTitle: document.getElementById("trace-record-title"),
    traceRecordLink: document.getElementById("trace-record-link"),
    scopeScorecardLink: document.getElementById("scope-scorecard-link"),
    scopeBoardLink: document.getElementById("scope-board-link"),
    scopeBriefLink: document.getElementById("scope-brief-link"),
    scopeBadgeLink: document.getElementById("scope-badge-link"),
    scopeFeedLink: document.getElementById("scope-feed-link"),
    searchForm: document.getElementById("feed-picker"),
    searchInput: document.getElementById("feed-search"),
    searchResults: document.getElementById("feed-results"),
    pickerStatus: document.getElementById("picker-status"),
    copy: document.getElementById("copy-view"),
  };

  var state = {
    artifact: FALLBACKS.unitrans,
    category: "correctness",
    fixIndex: 0,
    request: 0,
    controller: null,
    directory: null,
    directoryPromise: null,
    visibleMatches: [],
    persistUrl: false,
    searchRequest: 0,
  };
  var cache = new Map(Object.entries(FALLBACKS));
  var searchTimer = 0;

  function text(element, value) {
    if (element) element.textContent = value == null ? "" : String(value);
  }

  function validId(value) {
    return typeof value === "string" && /^[a-z0-9][a-z0-9-]{0,99}$/.test(value);
  }

  function isNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function validArtifact(value) {
    if (!value || typeof value !== "object") return false;
    if (!value.agency || !validId(value.agency.id) || typeof value.agency.name !== "string") return false;
    if (typeof value.snapshot_date !== "string") return false;
    if (!value.overall || typeof value.overall.grade !== "string" || !isNumber(value.overall.score)) return false;
    if (!value.categories || !CATEGORY_ORDER.every(function (key) { return value.categories[key]; })) return false;
    return Array.isArray(value.top_fixes);
  }

  function formatScore(value) {
    if (!isNumber(value)) return "Not measured";
    return value === 100 ? "100" : value.toFixed(1);
  }

  function formatDate(value) {
    var date = new Date(value + "T00:00:00Z");
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  function sourceFor(code) {
    var mappings = [
      ["wheelchair_boarding", ["stops.txt"], "Wheelchair boarding in stops.txt"],
      ["wheelchair_accessible", ["trips.txt"], "Vehicle accessibility in trips.txt"],
      ["unused_shape", ["shapes.txt", "trips.txt"], "Unused route geometry"],
      ["no_fare_data", ["fare_attributes.txt", "fare_products.txt"], "Published fare files"],
      ["missing_feed_info", ["feed_info.txt"], "Feed validity dates"],
      ["feed_expired", ["calendar.txt", "calendar_dates.txt", "feed_info.txt"], "Published service horizon"],
      ["feed_expiring_soon", ["calendar.txt", "calendar_dates.txt", "feed_info.txt"], "Published service horizon"],
      ["no_expiry_date", ["calendar.txt", "calendar_dates.txt", "feed_info.txt"], "Published service horizon"],
      ["planned_service_boundary", ["calendar.txt", "calendar_dates.txt", "feed_info.txt"], "Published service horizon"],
      ["intermittent_calendar_ended", ["calendar.txt", "calendar_dates.txt", "feed_info.txt"], "Published service horizon"],
      ["mixed_case", ["stops.txt", "trips.txt"], "Rider-facing names"],
      ["stop_without_stop_time", ["stops.txt", "stop_times.txt"], "Stops without scheduled service"],
    ];
    for (var i = 0; i < mappings.length; i += 1) {
      if (code.indexOf(mappings[i][0]) >= 0) {
        return { files: mappings[i][1], title: mappings[i][2] };
      }
    }
    return { files: ["GTFS feed"], title: "Published feed records" };
  }

  function methodFor(code) {
    if (code.indexOf("scorecard_rt_") === 0) {
      return {
        title: "Realtime sampling",
        copy: "The realtime rubric uses sampled feed health, trip coverage, route position, and schedule drift.",
      };
    }
    if (FRESHNESS_CODES.has(code)) {
      return {
        title: "Feed validity check",
        copy: "The freshness rubric checks the published validity window and the last scheduled service date.",
      };
    }
    if (code.indexOf("scorecard_") === 0) {
      return {
        title: "Direct field coverage",
        copy: "The rider-experience rubric measures whether the published field states the rider information it describes.",
      };
    }
    return {
      title: "MobilityData validator",
      copy: "The correctness rubric retains the canonical validator notice code and measured instance count.",
    };
  }

  function updateUrl() {
    if (!state.persistUrl) return;
    if (!window.history || typeof window.history.replaceState !== "function") return;
    var url = new URL(window.location.href);
    url.searchParams.set("feed", state.artifact.agency.id);
    url.searchParams.set("fix", String(state.fixIndex + 1));
    url.searchParams.set("category", state.category);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function renderCategory() {
    CATEGORY_ORDER.forEach(function (key) {
      var category = state.artifact.categories[key];
      var row = document.querySelector('[data-category-row="' + key + '"]');
      if (!(row instanceof HTMLElement)) return;
      var button = row.querySelector(".category-select");
      var value = row.querySelector(".category-value");
      var meter = row.querySelector(".category-meter");
      var measured = category.status === "measured" && isNumber(category.score);
      if (button) {
        button.setAttribute("aria-pressed", String(key === state.category));
        button.setAttribute(
          "aria-label",
          CATEGORY_LABELS[key] + ": " + (measured ? formatScore(category.score) + " out of 100" : "not measured") + ". Show details."
        );
      }
      text(value, measured ? formatScore(category.score) : "Not measured");
      if (meter instanceof HTMLElement) {
        var fill = meter.querySelector("span");
        meter.classList.toggle("is-unmeasured", !measured);
        if (measured) {
          meter.removeAttribute("aria-hidden");
          meter.setAttribute("role", "meter");
          meter.setAttribute("aria-label", CATEGORY_LABELS[key] + " score");
          meter.setAttribute("aria-valuemin", "0");
          meter.setAttribute("aria-valuemax", "100");
          meter.setAttribute("aria-valuenow", String(category.score));
        } else {
          meter.removeAttribute("role");
          meter.setAttribute("aria-hidden", "true");
          meter.removeAttribute("aria-valuenow");
        }
        if (fill instanceof HTMLElement) fill.style.width = measured ? Math.max(0, Math.min(100, category.score)) + "%" : "0";
      }
    });

    var selected = state.artifact.categories[state.category];
    var selectedMeasured = selected.status === "measured" && isNumber(selected.score);
    text(
      elements.categoryDetailTitle,
      CATEGORY_LABELS[state.category] + " · " + (selectedMeasured ? formatScore(selected.score) : "Not measured")
    );
    text(elements.categoryDetailSummary, selected.summary || "No category summary was published.");
  }

  function renderSourceFiles(files) {
    if (!elements.traceSourceFiles) return;
    elements.traceSourceFiles.replaceChildren();
    files.forEach(function (filename) {
      var item = document.createElement("li");
      var code = document.createElement("code");
      code.textContent = filename;
      item.appendChild(code);
      elements.traceSourceFiles.appendChild(item);
    });
  }

  function renderFix() {
    var fixes = state.artifact.top_fixes;
    if (elements.fixSelector) elements.fixSelector.hidden = fixes.length === 0;
    if (fixes.length === 0) {
      state.fixIndex = 0;
      document.querySelectorAll("[data-fix-index]").forEach(function (button) {
        var item = button.closest("li");
        if (item instanceof HTMLElement) item.hidden = true;
      });
      if (elements.effortLine) elements.effortLine.hidden = true;
      text(elements.fixCode, "Published snapshot / no prioritized fixes");
      text(elements.fixTitle, "No prioritized fixes in this snapshot.");
      text(elements.fixWhat, "This record does not list a next action.");
      text(elements.fixWhy, "Open the full scorecard for its measured category detail.");
      text(elements.traceSourceTitle, "Published scorecard record");
      text(elements.traceSourceCopy, "This snapshot has no prioritized fix to trace.");
      renderSourceFiles(["GTFS feed"]);
      text(elements.traceMethodTitle, "Published category results");
      text(elements.traceMethodCopy, "The record keeps each measured category and its disclosed method.");
      text(elements.traceCode, "no_prioritized_fix");
      text(
        elements.traceRecordTitle,
        state.artifact.agency.name + " · " + formatDate(state.artifact.snapshot_date)
      );
      return;
    }
    if (elements.effortLine) elements.effortLine.hidden = false;
    if (state.fixIndex >= fixes.length) state.fixIndex = 0;
    var fix = fixes[state.fixIndex];
    var buttons = document.querySelectorAll("[data-fix-index]");
    buttons.forEach(function (button) {
      var index = Number(button.getAttribute("data-fix-index"));
      var item = button.closest("li");
      var available = index < fixes.length;
      if (item instanceof HTMLElement) item.hidden = !available;
      if (!available) return;
      button.setAttribute("aria-pressed", String(index === state.fixIndex));
      var label = button.querySelector(".fix-button-text");
      text(label, fixes[index].what || fixes[index].fix || "Published finding");
    });

    var source = sourceFor(fix.code || "");
    var method = methodFor(fix.code || "");
    var owner = fix.owner || "Owner to confirm";
    text(elements.fixCode, String(state.fixIndex + 1).padStart(2, "0") + " / " + (fix.code || "published_finding") + " / " + source.files.join(" + "));
    text(elements.fixTitle, fix.fix || "Review this published finding.");
    text(elements.fixWhat, fix.what || "See the full scorecard for the measured evidence.");
    text(elements.fixWhy, fix.why || "See the full scorecard for the rider consequence.");
    text(elements.fixOwner, owner);
    text(elements.fixEffort, fix.effort || "Effort varies.");

    text(elements.traceSourceTitle, source.title);
    text(elements.traceSourceCopy, "This is the published source behind the selected " + state.artifact.agency.name + " finding.");
    renderSourceFiles(source.files);
    text(elements.traceMethodTitle, method.title);
    text(elements.traceMethodCopy, method.copy);
    text(elements.traceCode, fix.code || "published_finding");
    text(
      elements.traceRecordTitle,
      state.artifact.agency.name + " · " + formatDate(state.artifact.snapshot_date)
    );
  }

  function renderArtifact(artifact, announcement) {
    state.artifact = artifact;
    var id = artifact.agency.id;
    desk.dataset.agency = id;
    text(elements.agency, artifact.agency.name);
    text(elements.place, PILOT_PLACES[id] || "Published feed scorecard");
    if (elements.date) {
      elements.date.setAttribute("datetime", artifact.snapshot_date);
      text(elements.date, formatDate(artifact.snapshot_date));
    }
    text(elements.grade, artifact.overall.grade);
    if (elements.grade) elements.grade.setAttribute("aria-label", "Overall grade " + artifact.overall.grade);
    text(elements.score, formatScore(artifact.overall.score));
    if (elements.fullLink) elements.fullLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/");
    if (elements.briefLink) elements.briefLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/brief/");
    if (elements.traceRecordLink) elements.traceRecordLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/");
    if (elements.scopeScorecardLink) elements.scopeScorecardLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/");
    if (elements.scopeBoardLink) elements.scopeBoardLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/board/");
    if (elements.scopeBriefLink) elements.scopeBriefLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/brief/");
    if (elements.scopeBadgeLink) elements.scopeBadgeLink.setAttribute("href", "/data/artifacts/" + encodeURIComponent(id) + "/badge.svg");
    if (elements.scopeFeedLink) elements.scopeFeedLink.setAttribute("href", "/agency/" + encodeURIComponent(id) + "/feed.xml");

    document.querySelectorAll(".pilot-switch [data-agency-id]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-agency-id") === id));
    });

    renderCategory();
    renderFix();
    var realtime = artifact.categories.realtime;
    text(elements.note, (realtime.summary || "Realtime is not measured for this record.") + " " + ACCESSIBILITY_NOTE);
    text(elements.status, announcement || "Showing the " + artifact.agency.name + " published snapshot.");
  }

  function artifactUrl(id) {
    return PILOT_URLS[id] || "/data/artifacts/" + encodeURIComponent(id) + "/latest.json";
  }

  async function loadAgency(id, fallbackName) {
    if (!validId(id)) return;
    state.request += 1;
    var request = state.request;
    if (state.controller) state.controller.abort();
    state.controller = typeof AbortController === "function" ? new AbortController() : null;
    desk.setAttribute("aria-busy", "true");

    var fallback = cache.get(id);
    if (fallback) {
      renderArtifact(fallback, "Refreshing the " + fallback.agency.name + " published snapshot…");
      updateUrl();
    } else {
      text(elements.status, "Loading the " + (fallbackName || id) + " published scorecard…");
    }

    try {
      var response = await fetch(artifactUrl(id), {
        signal: state.controller ? state.controller.signal : undefined,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Scorecard request failed with " + response.status);
      var artifact = await response.json();
      if (!validArtifact(artifact) || artifact.agency.id !== id) throw new Error("Scorecard response did not match the published contract");
      if (request !== state.request) return;
      cache.set(id, artifact);
      renderArtifact(artifact, "Showing the " + artifact.agency.name + " published snapshot.");
      updateUrl();
    } catch (error) {
      if (error && error.name === "AbortError") return;
      if (request !== state.request) return;
      if (fallback) {
        renderArtifact(fallback, "Showing the last embedded pilot snapshot; the published record could not be refreshed.");
      } else {
        text(elements.status, "The preview could not load. Use Browse every scorecard to open the published record.");
      }
    } finally {
      if (request === state.request) desk.setAttribute("aria-busy", "false");
    }
  }

  function hideResults() {
    state.visibleMatches = [];
    if (elements.searchResults) elements.searchResults.hidden = true;
  }

  function renderMatches(matches) {
    state.visibleMatches = matches;
    if (!elements.searchResults) return;
    elements.searchResults.replaceChildren();
    matches.forEach(function (agency) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.dataset.agencyId = agency.id;
      button.dataset.agencyName = agency.name;
      var name = document.createElement("span");
      var identifier = document.createElement("span");
      name.className = "feed-result-name";
      identifier.className = "feed-result-id";
      name.textContent = agency.name;
      identifier.textContent = "Feed ID " + agency.id;
      button.append(name, identifier);
      item.appendChild(button);
      elements.searchResults.appendChild(item);
    });
    elements.searchResults.hidden = matches.length === 0;
    text(
      elements.pickerStatus,
      matches.length ? matches.length + (matches.length === 1 ? " match. Choose it to show the scorecard." : " matches. Choose one to show its scorecard.") : "No published scorecard matches that search."
    );
  }

  async function loadDirectory() {
    if (state.directory) return state.directory;
    if (!state.directoryPromise) {
      state.directoryPromise = fetch("/api/v1/ids.json", { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("Directory request failed");
          return response.json();
        })
        .then(function (payload) {
          if (!payload || !Array.isArray(payload.agencies)) throw new Error("Directory response is invalid");
          state.directory = payload.agencies.filter(function (agency) {
            return agency && validId(agency.id) && typeof agency.name === "string";
          });
          return state.directory;
        })
        .catch(function (error) {
          state.directoryPromise = null;
          throw error;
        });
    }
    return state.directoryPromise;
  }

  async function searchDirectory(query) {
    state.searchRequest += 1;
    var request = state.searchRequest;
    var normalized = query.trim().toLowerCase();
    if (normalized.length < 2) {
      hideResults();
      state.visibleMatches = [];
      text(elements.pickerStatus, "Type at least two characters to search published scorecards.");
      return;
    }
    text(elements.pickerStatus, "Loading agency names…");
    try {
      var directory = await loadDirectory();
      if (request !== state.searchRequest) return;
      var matches = directory
        .filter(function (agency) {
          return agency.name.toLowerCase().indexOf(normalized) >= 0 || agency.id.indexOf(normalized) >= 0;
        })
        .sort(function (left, right) {
          var leftStarts = left.name.toLowerCase().startsWith(normalized) ? 0 : 1;
          var rightStarts = right.name.toLowerCase().startsWith(normalized) ? 0 : 1;
          return leftStarts - rightStarts || left.name.localeCompare(right.name);
        })
        .slice(0, 7);
      renderMatches(matches);
    } catch (error) {
      if (request !== state.searchRequest) return;
      hideResults();
      text(elements.pickerStatus, "The directory could not load. Browse every scorecard instead.");
    }
  }

  document.querySelectorAll("[data-agency-id]").forEach(function (button) {
    button.addEventListener("click", function () {
      var id = button.getAttribute("data-agency-id");
      if (!id) return;
      state.persistUrl = true;
      state.fixIndex = 0;
      loadAgency(id, button.textContent.trim());
    });
  });

  document.querySelectorAll("[data-category]").forEach(function (button) {
    button.addEventListener("click", function () {
      var key = button.getAttribute("data-category");
      if (!key || CATEGORY_ORDER.indexOf(key) < 0) return;
      state.persistUrl = true;
      state.category = key;
      renderCategory();
      updateUrl();
      text(elements.status, "Showing " + CATEGORY_LABELS[key] + " details for " + state.artifact.agency.name + ".");
    });
  });

  document.querySelectorAll("[data-fix-index]").forEach(function (button) {
    button.addEventListener("click", function () {
      var index = Number(button.getAttribute("data-fix-index"));
      if (!Number.isInteger(index) || index < 0 || index >= state.artifact.top_fixes.length) return;
      state.persistUrl = true;
      state.fixIndex = index;
      renderFix();
      updateUrl();
      text(elements.status, "Tracing fix " + (index + 1) + " of " + state.artifact.top_fixes.length + " for " + state.artifact.agency.name + ".");
    });
  });

  if (elements.searchInput) {
    elements.searchInput.addEventListener("input", function () {
      window.clearTimeout(searchTimer);
      state.searchRequest += 1;
      state.visibleMatches = [];
      hideResults();
      searchTimer = window.setTimeout(function () {
        searchTimer = 0;
        searchDirectory(elements.searchInput.value);
      }, 120);
    });
    elements.searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        window.clearTimeout(searchTimer);
        searchTimer = 0;
        state.searchRequest += 1;
        hideResults();
        text(elements.pickerStatus, "Search results closed.");
      }
      if (event.key === "ArrowDown" && elements.searchResults && !elements.searchResults.hidden) {
        var first = elements.searchResults.querySelector("button");
        if (first instanceof HTMLButtonElement) {
          event.preventDefault();
          first.focus();
        }
      }
    });
  }

  if (elements.searchResults) {
    elements.searchResults.addEventListener("click", function (event) {
      var button = event.target instanceof Element ? event.target.closest("button[data-agency-id]") : null;
      if (!(button instanceof HTMLButtonElement)) return;
      var id = button.dataset.agencyId;
      var name = button.dataset.agencyName || button.textContent.trim();
      if (!id) return;
      if (elements.searchInput) elements.searchInput.value = name;
      hideResults();
      if (elements.searchInput) elements.searchInput.focus();
      state.persistUrl = true;
      state.fixIndex = 0;
      loadAgency(id, name);
    });
  }

  if (elements.searchForm) {
    elements.searchForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var first = state.visibleMatches[0];
      if (first) {
        if (elements.searchInput) elements.searchInput.value = first.name;
        hideResults();
        if (elements.searchInput) elements.searchInput.focus();
        state.persistUrl = true;
        state.fixIndex = 0;
        loadAgency(first.id, first.name);
        return;
      }
      var query = elements.searchInput ? elements.searchInput.value.trim() : "";
      window.location.href = "/app/#/?q=" + encodeURIComponent(query);
    });
  }

  document.addEventListener("click", function (event) {
    if (event.target instanceof Node && elements.searchForm && !elements.searchForm.contains(event.target)) {
      window.clearTimeout(searchTimer);
      searchTimer = 0;
      state.searchRequest += 1;
      hideResults();
    }
  });

  async function copyView() {
    state.persistUrl = true;
    updateUrl();
    var value = window.location.href;
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(value);
      text(elements.status, "Desk view copied. It will reopen this feed, fix, and category.");
    } catch (error) {
      text(elements.status, "Copy was unavailable. The address bar now contains this desk view.");
    }
  }
  if (elements.copy) elements.copy.addEventListener("click", copyView);

  var params = new URLSearchParams(window.location.search);
  var requestedCategory = params.get("category");
  var requestedFix = Number(params.get("fix"));
  var requestedFeed = params.get("feed");
  state.persistUrl = Boolean(requestedFeed || params.get("fix") || requestedCategory);
  if (requestedCategory && CATEGORY_ORDER.indexOf(requestedCategory) >= 0) state.category = requestedCategory;
  if (Number.isInteger(requestedFix) && requestedFix >= 1 && requestedFix <= 3) state.fixIndex = requestedFix - 1;

  renderArtifact(FALLBACKS.unitrans, "Showing the Unitrans published snapshot.");
  if (requestedFeed && validId(requestedFeed)) loadAgency(requestedFeed, requestedFeed);
  else loadAgency("unitrans", "Unitrans");
})();
