// @ts-check
/* Offline support (ideation EXP-20): keep the shell and any page a person has
 * visited readable without a connection. A liaison's site visit and the café
 * demo share the same failure mode, weak signal; the honesty rule is that a
 * saved copy must never masquerade as current, so nav.js shows a visible
 * offline note whenever the network is gone.
 *
 * Strategy, deliberately conservative:
 * - Navigations are network first. A deploy is picked up immediately and the
 *   saved copy is served only when the network fails, so the worker can never
 *   pin a reader to an old build.
 * - Stylesheets, scripts, and artifact JSON are stale-while-revalidate: the
 *   saved copy renders at once and refreshes in the background.
 * - Only same-origin requests are considered; nothing cross-origin is touched.
 */
(function () {
  "use strict";
  var CACHE = "scorecard-offline-v2";
  var SHELL = ["/src/styles.css", "/src/theme.js", "/src/nav.js"];
  var sw = /** @type {any} */ (self);

  sw.addEventListener("install", function (/** @type {any} */ event) {
    event.waitUntil(
      caches
        .open(CACHE)
        .then(function (cache) {
          return cache.addAll(SHELL);
        })
        .then(function () {
          return sw.skipWaiting();
        })
    );
  });

  sw.addEventListener("activate", function (/** @type {any} */ event) {
    event.waitUntil(
      caches
        .keys()
        .then(function (keys) {
          return Promise.all(
            keys
              .filter(function (key) {
                return key !== CACHE;
              })
              .map(function (key) {
                return caches.delete(key);
              })
          );
        })
        .then(function () {
          return sw.clients.claim();
        })
    );
  });

  function saveCopy(request, response) {
    // Only complete 200s: a 206 range response (the map's tile archive) is
    // not storable, and an error page must never shadow a good copy.
    if (response.status !== 200) return response;
    var copy = response.clone();
    caches.open(CACHE).then(function (cache) {
      cache.put(request, copy);
    });
    return response;
  }

  /* Beyond navigations, only the shell and the data a page reads offline are
   * worth saving: stylesheets and scripts under /src/, locale catalogs, and
   * artifact JSON. Tiles and images stay network-only so the cache stays
   * small on a phone. */
  function isCacheableAsset(pathname) {
    return (
      pathname.indexOf("/src/") === 0 ||
      pathname.indexOf("/locales/") === 0 ||
      pathname.slice(-5) === ".json"
    );
  }

  sw.addEventListener("fetch", function (/** @type {any} */ event) {
    var request = event.request;
    if (request.method !== "GET") return;
    var url = new URL(request.url);
    if (url.origin !== sw.location.origin) return;

    if (request.mode === "navigate") {
      event.respondWith(
        fetch(request)
          .then(function (response) {
            return saveCopy(request, response);
          })
          .catch(function () {
            return caches.match(request).then(function (saved) {
              return (
                saved ||
                new Response(
                  "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
                    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" +
                    "<title>Offline — GTFS Scorecard</title></head><body>" +
                    "<h1>You are offline</h1><p>This page has not been saved for " +
                    "offline reading yet. Pages you visit while online stay " +
                    "available without a connection.</p></body></html>",
                  { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
                )
              );
            });
          })
      );
      return;
    }

    if (!isCacheableAsset(url.pathname)) return;
    event.respondWith(
      caches.match(request).then(function (saved) {
        var refresh = fetch(request)
          .then(function (response) {
            return saveCopy(request, response);
          })
          .catch(function () {
            return saved || Response.error();
          });
        return saved || refresh;
      })
    );
  });
})();
