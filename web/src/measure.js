// @ts-check
/* Site measurement. This file is the whole of the measurement code the site
 * serves, and it holds two blocks that share nothing, so either can be
 * switched off without touching the other.
 *
 * The first block (docs/decisions/0055-cookieless-site-measurement.md) sends
 * one pageview per page load, and one event when a checkout link on /bundle/
 * is followed, to PostHog Cloud US. It is short enough to read in full:
 *
 * - No cookie, no localStorage, no fingerprint, no SDK. A visit id is drawn at
 *   random and kept in sessionStorage, which the browser discards when the tab
 *   closes. Every event carries $process_person_profile false, so PostHog
 *   keeps no person profile for it either.
 * - Only the page path is sent, never the query string or the fragment. The
 *   post-checkout page carries a Stripe order reference in its query string,
 *   and that reference must never leave the browser.
 * - Only the referring domain, never the full referrer, for the same reason.
 * - Nothing is read from a form, an input, or the page text. There is no
 *   autocapture here because there is no SDK here.
 * - Global Privacy Control or Do Not Track switches all of it off.
 * - With no key written by the deploy, the first line of logic returns and
 *   nothing is sent. The committed copy of this file has no key.
 *
 * The second block (docs/decisions/0056-google-analytics-4.md) loads Google
 * Analytics 4, whose own script and cookies are described in that ADR. The
 * rules it keeps are written above it.
 *
 * The disclosure a reader sees is /about/#privacy. The gates that keep this
 * file, that page, and every other page in step are
 * pipeline/tests/test_measure.py, pipeline/tests/test_measure_ga4.py and the
 * measurement section of pipeline/scripts/check_site_seo.py.
 */
(function () {
  "use strict";

  // Written at deploy time from the POSTHOG_KEY secret by the render-measure
  // command (scorecard_pipeline.site_shell.render_measure_script). A PostHog
  // project key is write-only and ships in every page by design; it is a
  // secret in the repository only so that it can be set without a commit.
  var KEY = ""; // measure:key
  var HOST = "https://us.i.posthog.com";
  var VISIT_KEY = "scorecard-visit";

  if (!KEY) return;
  var nav = /** @type {any} */ (window.navigator || {});
  var win = /** @type {any} */ (window);
  var doc = /** @type {any} */ (document);
  if (nav.globalPrivacyControl === true) return;
  if (nav.doNotTrack === "1" || win.doNotTrack === "1" || nav.msDoNotTrack === "1") return;
  if (doc.prerendering) return;
  if (!win.fetch || !win.crypto || !win.crypto.getRandomValues) return;

  /** @param {Uint8Array} bytes */
  function hex(bytes) {
    var out = "";
    for (var i = 0; i < bytes.length; i++) out += (bytes[i] + 256).toString(16).slice(1);
    return out;
  }

  /** A UUID version 7: the millisecond clock in the first 48 bits, random
   *  bits after. PostHog reads $session_id in this shape. @returns {string} */
  function uuid7() {
    var b = new Uint8Array(16);
    win.crypto.getRandomValues(b);
    var t = Date.now();
    b[0] = Math.floor(t / 1099511627776) % 256;
    b[1] = Math.floor(t / 4294967296) % 256;
    b[2] = Math.floor(t / 16777216) % 256;
    b[3] = Math.floor(t / 65536) % 256;
    b[4] = Math.floor(t / 256) % 256;
    b[5] = t % 256;
    b[6] = (b[6] & 15) | 112;
    b[8] = (b[8] & 63) | 128;
    var h = hex(b);
    return (
      h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" +
      h.slice(16, 20) + "-" + h.slice(20)
    );
  }

  /** The visit id: kept for this tab only, and only until the tab closes.
   *  When session storage is unavailable, each page load draws its own.
   *  @returns {string} */
  function visitId() {
    var id = null;
    try {
      id = win.sessionStorage.getItem(VISIT_KEY);
    } catch (e) {
      id = null;
    }
    if (!id || !/^[0-9a-f-]{36}$/.test(id)) {
      id = uuid7();
      try {
        win.sessionStorage.setItem(VISIT_KEY, id);
      } catch (e) {
        // Fine: this page load has its own id and the next one draws another.
      }
    }
    return id;
  }

  /** Which family of page this is, from the path alone. The Spanish pages
   *  mirror the English ones under /es/. @param {string} path */
  function pageType(path) {
    var p = path.replace(/^\/es(?=\/)/, "");
    if (p === "/") return "home";
    var head = p.split("/")[1] || "";
    if (head === "agency") return "agency";
    if (head === "program") return "program";
    if (head === "bundle") return "bundle";
    if (head === "support") return "support";
    if (head === "fix") return "fix";
    if (head === "agencies" || head === "app") return "directory";
    return "other";
  }

  /** The referring site, as a host name only. @returns {string} */
  function referringDomain() {
    var ref = doc.referrer;
    if (!ref) return "$direct";
    try {
      return new URL(ref).hostname || "$direct";
    } catch (e) {
      return "$direct";
    }
  }

  var visit = visitId();
  var path = win.location.pathname;

  /** @param {string} event @param {Record<string, string>} props */
  function send(event, props) {
    /** @type {Record<string, unknown>} */
    var properties = {
      $process_person_profile: false,
      $lib: "gtfs-scorecard-measure",
      $lib_version: "1",
      $session_id: visit,
      $current_url: win.location.origin + path,
      $pathname: path,
      $host: win.location.host,
      $referring_domain: referringDomain(),
      page_type: pageType(path),
    };
    for (var k in props) {
      if (Object.prototype.hasOwnProperty.call(props, k)) properties[k] = props[k];
    }
    var body = JSON.stringify({
      api_key: KEY,
      event: event,
      distinct_id: visit,
      properties: properties,
    });
    try {
      win
        .fetch(HOST + "/i/v0/e/", {
          method: "POST",
          mode: "cors",
          credentials: "omit",
          keepalive: true,
          headers: { "Content-Type": "application/json" },
          body: body,
        })
        .catch(function () {
          // Measurement never surfaces an error to a reader.
        });
    } catch (e) {
      // Same rule.
    }
  }

  send("$pageview", {});

  // A control opts in by carrying data-measure with the event name; nothing
  // else a reader clicks is reported. web/src/bundle.js marks the checkout
  // links this way, with data-measure-plan naming the plan id from plan.json.
  // Both values are checked against a narrow shape before they are sent, so
  // a stray attribute cannot turn into an arbitrary string in the event.
  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!(target instanceof Element)) return;
      var control = target.closest("[data-measure]");
      if (!control) return;
      var name = control.getAttribute("data-measure") || "";
      var plan = control.getAttribute("data-measure-plan") || "";
      if (!/^[a-z][a-z0-9_]{1,40}$/.test(name)) return;
      /** @type {Record<string, string>} */
      var props = {};
      if (/^[a-z0-9_]{1,40}$/.test(plan)) props.plan = plan;
      send(name, props);
    },
    true
  );
})();

// Google Analytics 4 (docs/decisions/0056-google-analytics-4.md).
//
// - With no measurement id written by the deploy, the first line of logic
//   returns and nothing loads: no Google script, no cookie, no request. The
//   committed copy of this file has no id. The id is measurement_ga4_id in
//   site-seo.json, and render-measure writes it into the marked line below.
// - Global Privacy Control or Do Not Track returns before anything loads.
// - A page served from this machine (localhost) loads nothing, so local work
//   and the Lighthouse runs in CI are never counted.
// - Consent defaults (Consent Mode v2): ad storage, ad user data and ad
//   personalization are denied everywhere. Analytics storage is denied in the
//   European Economic Area, the United Kingdom and Switzerland, and granted
//   elsewhere. There is no banner, so no _ga cookie is ever set in those
//   regions.
// - Google signals and ad personalization signals are off.
// - The page address sent is the path only, and the referrer is the origin
//   of the linking site only, for the reason the block above gives: the
//   post-checkout page carries a Stripe order reference in its query string,
//   and the page opened after it would carry that address as its referrer.
(function () {
  "use strict";

  // Written at deploy time from measurement_ga4_id in site-seo.json by the
  // render-measure command (scorecard_pipeline.site_shell.render_measure_script).
  // A GA4 measurement id ships in every page by design; it is not a secret.
  var GA4_ID = ""; // measure:ga4-id
  var LOADER = "https://www.googletagmanager.com/gtag/js?id=";
  // Where analytics storage stays denied: the 27 EU members, Iceland,
  // Liechtenstein and Norway (the EEA), the United Kingdom and Switzerland,
  // as the ISO 3166-1 codes the consent region parameter reads.
  var CONSENT_REQUIRED = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    "IS", "LI", "NO",
    "GB",
    "CH",
  ];

  if (!GA4_ID) return;
  var nav = /** @type {any} */ (window.navigator || {});
  var win = /** @type {any} */ (window);
  var doc = /** @type {any} */ (document);
  if (nav.globalPrivacyControl === true) return;
  if (nav.doNotTrack === "1" || win.doNotTrack === "1" || nav.msDoNotTrack === "1") return;
  if (!/^G-[A-Z0-9]+$/.test(GA4_ID)) return;
  var host = win.location.hostname;
  if (!host || host === "localhost" || host === "127.0.0.1" || host === "[::1]") return;

  /** The origin of the linking site, with no path. @returns {string} */
  function referrerOrigin() {
    var ref = doc.referrer;
    if (!ref) return "";
    try {
      return new URL(ref).origin + "/";
    } catch (e) {
      return "";
    }
  }

  win.dataLayer = win.dataLayer || [];
  // gtag reads the arguments object itself, not an array made from it.
  function gtag() {
    win.dataLayer.push(arguments);
  }

  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    region: CONSENT_REQUIRED,
  });
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "granted",
  });
  gtag("js", new Date());
  gtag("config", GA4_ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: win.location.origin + win.location.pathname,
    page_referrer: referrerOrigin(),
  });

  var script = doc.createElement("script");
  script.async = true;
  script.src = LOADER + encodeURIComponent(GA4_ID);
  (doc.head || doc.documentElement).appendChild(script);
})();
